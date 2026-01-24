import json
from pathlib import Path

from goldevidencebench import compaction
from goldevidencebench import diagnosis
from goldevidencebench import reporting
from goldevidencebench import thread_log


def test_thread_log_append(tmp_path: Path) -> None:
    log_path = tmp_path / "thread.jsonl"
    event = thread_log.build_event(run_id="run1", step=1, event_type="summary", notes="ok")
    thread_log.append_event(log_path, event)

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["schema_version"] == thread_log.SCHEMA_VERSION
    assert data["run_id"] == "run1"
    assert data["type"] == "summary"


def test_compact_state_write_no_bom(tmp_path: Path) -> None:
    summary = {"drift": {"step_rate": 0.1}}
    diag = {"status": "PASS", "primary_bottleneck": "answering", "required_inputs_next_run": []}
    state = compaction.build_compact_state(
        run_dir=tmp_path,
        summary=summary,
        diagnosis=diag,
        context_keys={"tag.00"},
        thresholds=diagnosis.DEFAULT_THRESHOLDS,
        report_path=tmp_path / "report.md",
        run_config={"seed": 0},
        gates_enabled={"retrieval_authority_filter": False},
        rerank_mode="none",
        authority_mode="filter_off",
    )
    out_path = tmp_path / "compact_state.json"
    compaction.write_compact_state(out_path, state)

    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == compaction.SCHEMA_VERSION
    assert data["artifact_version"] == compaction.ARTIFACT_VERSION
    assert "tag.00" in data["current_context_keys"]
    assert not out_path.read_bytes().startswith(b"\xef\xbb\xbf")


def test_report_generation(tmp_path: Path) -> None:
    summary_path = tmp_path / "summary.json"
    diagnosis_path = tmp_path / "diagnosis.json"
    compact_path = tmp_path / "compact_state.json"
    report_path = tmp_path / "report.md"

    summary = {"retrieval": {"gold_present_rate": 1.0}}
    diag = {
        "status": "PASS",
        "primary_bottleneck": "answering",
        "supporting_metrics": {
            "unsafe_commit_rate": 0.0,
            "flip_rate": 0.0,
            "gold_present_rate": 1.0,
            "selection_rate_given_present": 1.0,
            "authority_violation_rate": 0.0,
            "answer_correct_given_selected": 1.0,
            "drift_step_rate": 0.0,
        },
        "required_inputs_next_run": [],
    }
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    diagnosis_path.write_text(json.dumps(diag), encoding="utf-8")
    compaction.write_compact_state(
        compact_path,
        compaction.build_compact_state(
            run_dir=tmp_path,
            summary=summary,
            diagnosis=diag,
            context_keys=set(),
            thresholds=diagnosis.DEFAULT_THRESHOLDS,
            report_path=report_path,
        ),
    )

    reporting.generate_report(
        summary_path=summary_path,
        diagnosis_path=diagnosis_path,
        compact_state_path=compact_path,
        out_path=report_path,
        thresholds_path=None,
    )

    report_text = report_path.read_text(encoding="utf-8")
    assert "Overall: PASS" in report_text
    assert "Key metrics vs thresholds" in report_text


def test_compaction_invariants(tmp_path: Path) -> None:
    summary = {"drift": {"step_rate": 0.0}}
    diag = {"status": "PASS", "primary_bottleneck": "answering", "required_inputs_next_run": []}
    report_path = tmp_path / "report.md"
    compact_path = tmp_path / "compact_state.json"
    thread_path = tmp_path / "thread.jsonl"

    compact_state = compaction.build_compact_state(
        run_dir=tmp_path,
        summary=summary,
        diagnosis=diag,
        context_keys={"k1"},
        thresholds=diagnosis.DEFAULT_THRESHOLDS,
        report_path=report_path,
        run_config={"seed": 1},
        gates_enabled={"retrieval_authority_filter": True},
        rerank_mode="latest_step",
        authority_mode="filter_on",
    )
    compaction.write_compact_state(compact_path, compact_state)

    thread_log.append_event(
        thread_path,
        thread_log.build_event(run_id="run", step=0, event_type="plan", notes="start_marker"),
    )
    thread_log.append_event(
        thread_path,
        thread_log.build_event(run_id="run", step=1, event_type="observation", notes="summary"),
    )
    thread_log.append_event(
        thread_path,
        thread_log.build_event(run_id="run", step=2, event_type="tool", notes="diagnosis"),
    )
    thread_log.append_event(
        thread_path,
        thread_log.build_event(run_id="run", step=3, event_type="summary", notes="end_marker"),
    )

    report_path.write_text(
        "\n".join(
            [
                "# Run Report",
                "",
                "Overall: PASS",
                "",
                "## Artifacts",
                "- summary.json",
                "- diagnosis.json",
                "- compact_state.json",
                "- thread.jsonl",
                "- report.md",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    errors = compaction.validate_compaction_artifacts(
        run_dir=tmp_path,
        compact_state=compact_state,
        thread_path=thread_path,
        report_path=report_path,
    )
    assert errors == []
