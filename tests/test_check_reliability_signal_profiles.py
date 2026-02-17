from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _base_strict_summary(tmp_path: Path) -> tuple[Path, Path]:
    strict_run = tmp_path / "rag_benchmark_001"
    strict_run.mkdir(parents=True)
    _write_json(
        strict_run / "summary_compact.json",
        {
            "benchmark": "rag_benchmark_strict",
            "status": "PASS",
            "means": {
                "value_acc": 0.99,
                "exact_acc": 0.99,
                "cite_f1": 0.99,
                "instruction_acc": 0.99,
                "state_integrity_rate": 0.99,
            },
            "datasets": [
                {"id": "domain_stale", "exact_acc": 1.0},
                {"id": "domain_authority", "exact_acc": 1.0},
                {"id": "domain_exception", "exact_acc": 1.0},
            ],
        },
    )
    strict_ptr = tmp_path / "latest_rag_strict"
    strict_ptr.write_text(str(strict_run), encoding="utf-8")
    return strict_run, strict_ptr


def test_check_reliability_signal_fastlocal_mock_canary_soft_fail(tmp_path: Path) -> None:
    _, strict_ptr = _base_strict_summary(tmp_path)
    compression = tmp_path / "compression_reliability_latest.json"
    novel = tmp_path / "novel_continuity_reliability_latest.json"
    authority = tmp_path / "authority_under_interference_reliability_latest.json"
    rpa_reliability = tmp_path / "rpa_mode_switch_reliability_latest.json"
    rpa_run = tmp_path / "runs" / "rpa_mode_switch_001"

    _write_json(compression, {"status": "PASS"})
    _write_json(novel, {"status": "PASS"})
    _write_json(authority, {"status": "PASS"})
    _write_json(
        rpa_reliability,
        {
            "benchmark": "rpa_mode_switch_reliability",
            "status": "FAIL",
            "runs": [str(rpa_run)],
            "failures": [f"{rpa_run}: canary.exact_rate > 0.9"],
        },
    )
    _write_json(
        rpa_run / "rpa_mode_switch_summary.json",
        {
            "hard_gate_status": "PASS",
            "canary_status": "WARN",
            "anchors": {"status": "PASS", "means": {"value_acc": 1.0}},
            "holdout": {"status": "PASS", "means": {"value_acc": 1.0}},
        },
    )

    script = Path(__file__).resolve().parents[1] / "scripts" / "check_reliability_signal.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--strict",
            str(strict_ptr),
            "--compression-reliability",
            str(compression),
            "--novel-reliability",
            str(novel),
            "--authority-interference-reliability",
            str(authority),
            "--rpa-mode-switch-reliability",
            str(rpa_reliability),
            "--require-rpa-mode-switch",
            "--profile",
            "fastlocal",
            "--allow-mock-canary-soft-fail",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "canary-only soft-fail in fastlocal profile" in result.stdout
    assert "RESULT: PASS" in result.stdout


def test_check_reliability_signal_release_profile_fails_canary_only_status(tmp_path: Path) -> None:
    _, strict_ptr = _base_strict_summary(tmp_path)
    compression = tmp_path / "compression_reliability_latest.json"
    novel = tmp_path / "novel_continuity_reliability_latest.json"
    authority = tmp_path / "authority_under_interference_reliability_latest.json"
    rpa_reliability = tmp_path / "rpa_mode_switch_reliability_latest.json"
    rpa_run = tmp_path / "runs" / "rpa_mode_switch_001"

    _write_json(compression, {"status": "PASS"})
    _write_json(novel, {"status": "PASS"})
    _write_json(authority, {"status": "PASS"})
    _write_json(
        rpa_reliability,
        {
            "benchmark": "rpa_mode_switch_reliability",
            "status": "FAIL",
            "runs": [str(rpa_run)],
            "failures": [f"{rpa_run}: canary.exact_rate > 0.9"],
        },
    )
    _write_json(
        rpa_run / "rpa_mode_switch_summary.json",
        {
            "hard_gate_status": "FAIL",
            "canary_status": "WARN",
            "anchors": {"status": "PASS", "means": {"value_acc": 1.0}},
            "holdout": {"status": "PASS", "means": {"value_acc": 1.0}},
        },
    )

    script = Path(__file__).resolve().parents[1] / "scripts" / "check_reliability_signal.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--strict",
            str(strict_ptr),
            "--compression-reliability",
            str(compression),
            "--novel-reliability",
            str(novel),
            "--authority-interference-reliability",
            str(authority),
            "--rpa-mode-switch-reliability",
            str(rpa_reliability),
            "--require-rpa-mode-switch",
            "--profile",
            "release",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "RESULT: FAIL" in result.stdout
