from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def test_render_release_matrix_failure_report_outputs_family_details(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "render_release_matrix_failure_report.py"

    run_dir = tmp_path / "epi_target_r1"
    reliability_path = tmp_path / "epistemic_calibration_suite_reliability_latest.json"
    matrix_path = tmp_path / "release_reliability_matrix.json"
    out_path = tmp_path / "release_reliability_failure_report.txt"
    rows_out_dir = tmp_path / "release_reliability_failed_rows"

    _write_json(
        reliability_path,
        {
            "benchmark": "epistemic_calibration_suite_reliability",
            "status": "FAIL",
            "failures": [
                "runs\\epi_target_r1: hard_gate_status != PASS",
                "runs\\epi_target_r1: holdout.parse_rate >= 1.0",
            ],
            "runs": [str(run_dir)],
        },
    )
    _write_json(
        run_dir / "holdout_summary.json",
        {
            "status": "FAIL",
            "failures": [
                "parse_rate < 1.0",
                "confidence_provided_rate < 1.0",
            ],
        },
    )
    _write_json(
        run_dir / "persona_invariance_summary.json",
        {
            "status": "FAIL",
            "row_invariance_rate": 0.4131944444444444,
            "rows_total": 288,
            "rows_changed": 169,
        },
    )
    _write_jsonl(
        run_dir / "holdout_rows.jsonl",
        [
            {
                "id": "EPI-HOLDOUT-0001-Q001",
                "family_id": "missing_key_dependency",
                "expected_decision": "retrieve",
                "pred_decision": "retrieve",
                "parsed_json": False,
                "confidence_provided": False,
                "confidence_proxy_used": True,
            }
        ],
    )
    _write_jsonl(
        run_dir / "persona_invariance_rows.jsonl",
        [
            {
                "id": "EPI-HOLDOUT-0001-Q001_persona_persona_confident_expert",
                "persona_base_row_id": "EPI-HOLDOUT-0001-Q001",
                "persona_profile": "persona_confident_expert",
                "invariant": False,
                "change_reasons": ["value_changed", "null_flip"],
                "canonical_value": None,
                "perturbed_value": {"decision": "abstain"},
            }
        ],
    )
    _write_json(
        matrix_path,
        {
            "benchmark": "release_reliability_matrix",
            "status": "FAIL",
            "generated_at_utc": "2026-02-18T00:00:00Z",
            "coverage": {"required_total": 14, "produced_total": 14, "coverage_rate": 1.0},
            "freshness_violations": ["epistemic_calibration_suite:producer_failed_or_nonzero_exit"],
            "families": [
                {
                    "id": "epistemic_calibration_suite",
                    "artifact_path": str(reliability_path),
                    "stage": "target",
                    "producer_attempted": True,
                    "producer_succeeded": False,
                    "produced_in_this_run": False,
                    "freshness_ok": False,
                    "freshness_reason": "producer_failed_or_nonzero_exit",
                }
            ],
            "failing_families": [
                {
                    "id": "epistemic_calibration_suite",
                    "status": "FAIL",
                    "first_failure_reason": "runs\\epi_target_r1: hard_gate_status != PASS",
                }
            ],
        },
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--matrix",
            str(matrix_path),
            "--out",
            str(out_path),
            "--sample-limit",
            "2",
            "--rows-out-dir",
            str(rows_out_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert out_path.exists()

    report = out_path.read_text(encoding="utf-8")
    assert "Release Reliability Matrix Failure Report" in report
    assert "[epistemic_calibration_suite]" in report
    assert "hard_gate_status != PASS" in report
    assert "holdout.parse_rate >= 1.0" in report
    assert "parse_rate < 1.0" in report
    assert "row_invariance_rate=0.4131944444444444" in report
    assert "EPI-HOLDOUT-0001-Q001" in report
    assert "value_changed" in report

    all_failed = rows_out_dir / "failed_row_ids.txt"
    holdout_failed = rows_out_dir / "failed_holdout_row_ids.txt"
    persona_failed = rows_out_dir / "persona_drift_base_row_ids.txt"
    family_holdout = rows_out_dir / "epistemic_calibration_suite_holdout_failed_ids.txt"
    family_persona = rows_out_dir / "epistemic_calibration_suite_persona_failed_base_ids.txt"

    assert all_failed.exists()
    assert holdout_failed.exists()
    assert persona_failed.exists()
    assert family_holdout.exists()
    assert family_persona.exists()

    assert all_failed.read_text(encoding="utf-8").strip() == "EPI-HOLDOUT-0001-Q001"
    assert holdout_failed.read_text(encoding="utf-8").strip() == "EPI-HOLDOUT-0001-Q001"
    assert persona_failed.read_text(encoding="utf-8").strip() == "EPI-HOLDOUT-0001-Q001"
