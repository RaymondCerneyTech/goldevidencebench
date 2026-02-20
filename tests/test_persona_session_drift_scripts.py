from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def _powershell_executable() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _run_script(script: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _run_powershell_file(script: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    powershell = _powershell_executable()
    if not powershell:
        pytest.skip("pwsh/powershell executable is required for runner integration tests")
    return subprocess.run(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_generate_persona_session_drift_dataset_basic(tmp_path: Path) -> None:
    out_path = tmp_path / "persona_session_data.jsonl"
    script = Path(__file__).resolve().parents[1] / "scripts" / "generate_persona_session_drift_dataset.py"
    result = _run_script(
        script,
        [
            "--out",
            str(out_path),
            "--sessions",
            "2",
            "--turns",
            "3",
        ],
    )
    assert result.returncode == 0, result.stderr
    rows = _read_jsonl(out_path)
    assert len(rows) == 6
    first = rows[0]
    meta = first.get("meta", {})
    assert first["id"].endswith("T001")
    assert meta.get("session_id") == "S0001"
    assert meta.get("turn_index") == 1
    assert meta.get("turns_total") == 3
    assert meta.get("persona_session_drift_variant") is True
    assert "[PERSONA SESSION DRIFT v1]" in first.get("question", "")
    assert "[STYLE:CONFIDENT_EXPERT]" in first.get("gold", {}).get("value", "")


def test_generate_persona_session_drift_dataset_wraps_canonical_rows(tmp_path: Path) -> None:
    canonical_data = tmp_path / "canonical.jsonl"
    _write_jsonl(
        canonical_data,
        [
            {
                "id": "BASE-R1",
                "episode_id": "BASE-E1",
                "schema_version": "1.0",
                "document": "# Doc\n- [U123ABC] UPDATE step=1 SET tag.00 = alpha",
                "book": "# Book\n## State Ledger\n- [U123ABC] step=1 SET tag.00 = alpha",
                "question": "What is tag.00? Return JSON with keys value, support_ids.",
                "gold": {"value": "alpha", "support_ids": ["U123ABC"]},
                "meta": {"family": "novel_continuity_long_horizon"},
            }
        ],
    )
    out_path = tmp_path / "persona_session_wrapped.jsonl"
    script = Path(__file__).resolve().parents[1] / "scripts" / "generate_persona_session_drift_dataset.py"
    result = _run_script(
        script,
        [
            "--out",
            str(out_path),
            "--canonical-data",
            str(canonical_data),
            "--turns",
            "2",
        ],
    )
    assert result.returncode == 0, result.stderr
    rows = _read_jsonl(out_path)
    assert len(rows) == 2
    first = rows[0]
    meta = first.get("meta", {})
    assert first["id"] == "BASE-R1_persona_session_t001"
    assert first["episode_id"] == "BASE-E1"
    assert meta.get("persona_base_row_id") == "BASE-R1"
    assert "[ORIGINAL QUESTION]" in first.get("question", "")
    assert "What is tag.00?" in first.get("question", "")
    assert first.get("gold", {}).get("support_ids") == ["U123ABC"]
    assert "[STYLE:" in first.get("gold", {}).get("value", "")
    assert first.get("gold", {}).get("value", "").endswith("alpha")


def test_generate_persona_session_drift_dataset_disabled_mode_compacts_prompt(tmp_path: Path) -> None:
    canonical_data = tmp_path / "canonical.jsonl"
    _write_jsonl(
        canonical_data,
        [
            {
                "id": "BASE-R1",
                "episode_id": "BASE-E1",
                "schema_version": "1.0",
                "document": "# Doc\n- [U123ABC] UPDATE step=1 SET tag.00 = alpha",
                "book": "# Book\n## State Ledger\n- [U123ABC] step=1 SET tag.00 = alpha",
                "question": "What is tag.00? Return JSON with keys value, support_ids.",
                "gold": {"value": "alpha", "support_ids": ["U123ABC"]},
                "meta": {"family": "novel_continuity_long_horizon"},
            }
        ],
    )
    out_path = tmp_path / "persona_session_wrapped_disabled.jsonl"
    script = Path(__file__).resolve().parents[1] / "scripts" / "generate_persona_session_drift_dataset.py"
    result = _run_script(
        script,
        [
            "--out",
            str(out_path),
            "--canonical-data",
            str(canonical_data),
            "--turns",
            "2",
            "--style-marker-mode",
            "disabled",
        ],
    )
    assert result.returncode == 0, result.stderr
    rows = _read_jsonl(out_path)
    assert len(rows) == 2
    first = rows[0]
    question = first.get("question", "")
    assert "[PERSONA SESSION DRIFT v1]" in question
    assert "[ORIGINAL QUESTION]" in question
    assert "[TURN 2 USER]" not in question
    assert "Follow the ORIGINAL QUESTION response contract exactly" in question
    assert "[STYLE:" not in first.get("gold", {}).get("value", "")


def _run_score(
    *,
    data_path: Path,
    preds_path: Path,
    out_path: Path,
    rows_out: Path,
    report_out: Path,
    extra_args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    script = Path(__file__).resolve().parents[1] / "scripts" / "score_persona_session_drift.py"
    args = [
        "--data",
        str(data_path),
        "--preds",
        str(preds_path),
        "--out",
        str(out_path),
        "--rows-out",
        str(rows_out),
        "--report-out",
        str(report_out),
    ]
    if extra_args:
        args.extend(extra_args)
    return _run_script(script, args)


def test_score_persona_session_drift_passes_with_stable_profile_and_facts(tmp_path: Path) -> None:
    data_path = tmp_path / "data.jsonl"
    preds_path = tmp_path / "preds.jsonl"
    out_path = tmp_path / "summary.json"
    rows_out = tmp_path / "rows.jsonl"
    report_out = tmp_path / "report.md"
    _write_jsonl(
        data_path,
        [
            {
                "id": "R1",
                "question": "Q1",
                "gold": {"value": "[STYLE:CONFIDENT_EXPERT] alpha", "support_ids": ["U1"]},
                "meta": {
                    "session_id": "S1",
                    "turn_index": 1,
                    "turns_total": 2,
                    "persona_seed_profile": "persona_confident_expert",
                    "persona_expected_profile": "persona_confident_expert",
                    "persona_injected_profile": "persona_creative_writer",
                },
            },
            {
                "id": "R2",
                "question": "Q2",
                "gold": {"value": "[STYLE:CONFIDENT_EXPERT] alpha", "support_ids": ["U1"]},
                "meta": {
                    "session_id": "S1",
                    "turn_index": 2,
                    "turns_total": 2,
                    "persona_seed_profile": "persona_confident_expert",
                    "persona_expected_profile": "persona_confident_expert",
                    "persona_injected_profile": "persona_creative_writer",
                },
            },
        ],
    )
    _write_jsonl(
        preds_path,
        [
            {"id": "R1", "value": "[STYLE:CONFIDENT_EXPERT] alpha", "support_ids": ["U1"]},
            {"id": "R2", "value": "[STYLE:CONFIDENT_EXPERT] alpha", "support_ids": ["U1"]},
        ],
    )
    result = _run_score(
        data_path=data_path,
        preds_path=preds_path,
        out_path=out_path,
        rows_out=rows_out,
        report_out=report_out,
    )
    assert result.returncode == 0, result.stderr
    summary = _read_json(out_path)
    assert summary["status"] == "PASS"
    assert summary["profile_match_rate"] == 1.0
    assert summary["factual_match_rate"] == 1.0
    assert summary["drift_rate"] == 0.0
    assert summary["profile_flip_rate"] == 0.0
    assert "Persona Session Drift Report" in report_out.read_text(encoding="utf-8")


def test_score_persona_session_drift_fails_on_profile_mismatch_and_flip(tmp_path: Path) -> None:
    data_path = tmp_path / "data.jsonl"
    preds_path = tmp_path / "preds.jsonl"
    out_path = tmp_path / "summary.json"
    rows_out = tmp_path / "rows.jsonl"
    report_out = tmp_path / "report.md"
    _write_jsonl(
        data_path,
        [
            {
                "id": "R1",
                "question": "Q1",
                "gold": {"value": "[STYLE:CONFIDENT_EXPERT] alpha", "support_ids": ["U1"]},
                "meta": {
                    "session_id": "S1",
                    "turn_index": 1,
                    "turns_total": 3,
                    "persona_seed_profile": "persona_confident_expert",
                    "persona_expected_profile": "persona_confident_expert",
                },
            },
            {
                "id": "R2",
                "question": "Q2",
                "gold": {"value": "[STYLE:CONFIDENT_EXPERT] alpha", "support_ids": ["U1"]},
                "meta": {
                    "session_id": "S1",
                    "turn_index": 2,
                    "turns_total": 3,
                    "persona_seed_profile": "persona_confident_expert",
                    "persona_expected_profile": "persona_confident_expert",
                },
            },
            {
                "id": "R3",
                "question": "Q3",
                "gold": {"value": "[STYLE:CONFIDENT_EXPERT] alpha", "support_ids": ["U1"]},
                "meta": {
                    "session_id": "S1",
                    "turn_index": 3,
                    "turns_total": 3,
                    "persona_seed_profile": "persona_confident_expert",
                    "persona_expected_profile": "persona_confident_expert",
                },
            },
        ],
    )
    _write_jsonl(
        preds_path,
        [
            {"id": "R1", "value": "[STYLE:CONFIDENT_EXPERT] alpha", "support_ids": ["U1"]},
            {"id": "R2", "value": "[STYLE:CREATIVE_WRITER] alpha", "support_ids": ["U1"]},
            {"id": "R3", "value": "[STYLE:CREATIVE_WRITER] alpha", "support_ids": ["U1"]},
        ],
    )
    result = _run_score(
        data_path=data_path,
        preds_path=preds_path,
        out_path=out_path,
        rows_out=rows_out,
        report_out=report_out,
    )
    assert result.returncode == 1
    summary = _read_json(out_path)
    assert summary["status"] == "FAIL"
    assert summary["profile_match_rate"] < 1.0
    assert summary["drift_rate"] > 0.0
    assert summary["profile_flip_rate"] > 0.0
    rows = _read_jsonl(rows_out)
    assert any("profile_mismatch" in row["drift_reasons"] for row in rows)
    assert any(row["profile_flip_from_previous"] for row in rows)


def test_score_persona_session_drift_can_ignore_profile_and_support_checks(tmp_path: Path) -> None:
    data_path = tmp_path / "data.jsonl"
    preds_path = tmp_path / "preds.jsonl"
    out_path = tmp_path / "summary.json"
    rows_out = tmp_path / "rows.jsonl"
    report_out = tmp_path / "report.md"
    _write_jsonl(
        data_path,
        [
            {
                "id": "R1",
                "question": "Q1",
                "gold": {"value": "alpha", "support_ids": ["U1"]},
                "meta": {
                    "session_id": "S1",
                    "turn_index": 1,
                    "turns_total": 2,
                    "persona_seed_profile": "persona_confident_expert",
                    "persona_expected_profile": "persona_confident_expert",
                    "persona_injected_profile": "persona_creative_writer",
                },
            },
            {
                "id": "R2",
                "question": "Q2",
                "gold": {"value": "alpha", "support_ids": ["U1"]},
                "meta": {
                    "session_id": "S1",
                    "turn_index": 2,
                    "turns_total": 2,
                    "persona_seed_profile": "persona_confident_expert",
                    "persona_expected_profile": "persona_confident_expert",
                    "persona_injected_profile": "persona_creative_writer",
                },
            },
        ],
    )
    _write_jsonl(
        preds_path,
        [
            {"id": "R1", "value": "alpha", "support_ids": []},
            {"id": "R2", "value": "alpha", "support_ids": []},
        ],
    )
    result = _run_score(
        data_path=data_path,
        preds_path=preds_path,
        out_path=out_path,
        rows_out=rows_out,
        report_out=report_out,
        extra_args=["--no-require-profile-marker", "--no-require-support-match"],
    )
    assert result.returncode == 0, result.stderr
    summary = _read_json(out_path)
    assert summary["status"] == "PASS"
    assert summary["profile_match_rate"] is None
    assert summary["factual_match_rate"] == 1.0
    assert summary["drift_rate"] == 0.0


def test_score_persona_session_drift_missing_marker_uses_diagnostic_inference_only(
    tmp_path: Path,
) -> None:
    data_path = tmp_path / "data.jsonl"
    preds_path = tmp_path / "preds.jsonl"
    out_path = tmp_path / "summary.json"
    rows_out = tmp_path / "rows.jsonl"
    report_out = tmp_path / "report.md"
    _write_jsonl(
        data_path,
        [
            {
                "id": "R1",
                "question": "Q1",
                "gold": {"value": "[STYLE:CONFIDENT_EXPERT] tuesday", "support_ids": ["U1"]},
                "meta": {
                    "session_id": "S1",
                    "turn_index": 1,
                    "turns_total": 1,
                    "persona_seed_profile": "persona_confident_expert",
                    "persona_expected_profile": "persona_confident_expert",
                },
            }
        ],
    )
    _write_jsonl(
        preds_path,
        [
            {"id": "R1", "value": "tuesday", "support_ids": ["U1"]},
        ],
    )
    result = _run_score(
        data_path=data_path,
        preds_path=preds_path,
        out_path=out_path,
        rows_out=rows_out,
        report_out=report_out,
    )
    assert result.returncode == 1
    summary = _read_json(out_path)
    assert summary["status"] == "FAIL"
    assert summary["marker_presence_rate"] == 0.0
    assert summary["profile_match_rate"] == 0.0
    assert summary["profile_match_rate_inferred"] == 0.0
    assert summary["classification_source_counts"]["heuristic"] == 1
    rows = _read_jsonl(rows_out)
    assert len(rows) == 1
    row = rows[0]
    assert row["predicted_marker"] is None
    assert row["predicted_profile"] is None
    assert row["predicted_profile_inferred"] == "persona_ultra_brief"
    assert row["classification_source"] == "heuristic"
    assert "marker_missing" in row["drift_reasons"]
    assert "profile_unclassified" in row["drift_reasons"]
    assert "profile_mismatch" not in row["drift_reasons"]


def test_score_persona_session_drift_treats_json_null_as_factual_null(
    tmp_path: Path,
) -> None:
    data_path = tmp_path / "data.jsonl"
    preds_path = tmp_path / "preds.jsonl"
    out_path = tmp_path / "summary.json"
    rows_out = tmp_path / "rows.jsonl"
    report_out = tmp_path / "report.md"
    _write_jsonl(
        data_path,
        [
            {
                "id": "R1",
                "question": "Q1",
                "gold": {"value": "null", "support_ids": ["U1"]},
                "meta": {
                    "session_id": "S1",
                    "turn_index": 1,
                    "turns_total": 1,
                    "persona_seed_profile": "persona_overly_helpful",
                    "persona_expected_profile": "persona_overly_helpful",
                },
            }
        ],
    )
    _write_jsonl(
        preds_path,
        [
            {"id": "R1", "value": None, "support_ids": ["U1"]},
        ],
    )
    result = _run_score(
        data_path=data_path,
        preds_path=preds_path,
        out_path=out_path,
        rows_out=rows_out,
        report_out=report_out,
        extra_args=["--no-require-profile-marker", "--no-require-support-match"],
    )
    assert result.returncode == 0, result.stderr
    summary = _read_json(out_path)
    assert summary["status"] == "PASS"
    assert summary["factual_match_rate"] == 1.0
    rows = _read_jsonl(rows_out)
    assert len(rows) == 1
    row = rows[0]
    assert row["predicted_factual_value"] == "null"
    assert row["factual_match"] is True
    assert "factual_mismatch" not in row["drift_reasons"]


@pytest.mark.skipif(os.name != "nt", reason="PowerShell runner integration is Windows-only")
def test_run_persona_session_drift_trap_writes_artifacts(tmp_path: Path) -> None:
    canonical_data = tmp_path / "canonical.jsonl"
    out_root = tmp_path / "persona_session_runner"
    _write_jsonl(
        canonical_data,
        [
            {
                "id": "BASE-R1",
                "episode_id": "BASE-E1",
                "schema_version": "1.0",
                "document": "# Doc\n- [U123ABC] UPDATE step=1 SET tag.00 = alpha",
                "book": "# Book\n## State Ledger\n- [U123ABC] step=1 SET tag.00 = alpha",
                "question": "What is tag.00? Return JSON with keys value, support_ids.",
                "gold": {"value": "alpha", "support_ids": ["U123ABC"]},
                "meta": {"family": "novel_continuity_long_horizon"},
            }
        ],
    )

    summary_out = out_root / "persona_session_drift_summary.json"
    rows_out = out_root / "persona_session_drift_rows.jsonl"
    report_out = out_root / "persona_session_drift_report.md"

    script = Path(__file__).resolve().parents[1] / "scripts" / "run_persona_session_drift_trap.ps1"
    result = _run_powershell_file(
        script,
        [
            "-CanonicalData",
            str(canonical_data),
            "-Turns",
            "3",
            "-OutRoot",
            str(out_root),
            "-Adapter",
            "goldevidencebench.adapters.mock_adapter:create_adapter",
            "-SummaryPath",
            str(summary_out),
            "-RowsPath",
            str(rows_out),
            "-ReportPath",
            str(report_out),
        ],
    )
    assert result.returncode == 0, result.stderr
    assert summary_out.exists()
    assert rows_out.exists()
    assert report_out.exists()
    summary = _read_json(summary_out)
    assert summary["status"] == "PASS"
    assert summary["profile_match_rate"] == 1.0
    assert summary["factual_match_rate"] == 1.0
