from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _run_check_report_script(args: list[str]) -> subprocess.CompletedProcess[str]:
    script = _repo_root() / "scripts" / "build_capability_check_report.py"
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(_repo_root()),
    )


def _snapshot_with_metric(status: str, metric_key: str, metric_value: float) -> dict:
    return {
        "benchmark": "capability_snapshot",
        "status": status,
        "failure_reasons": [],
        "warning_reasons": [],
        "metrics": {
            metric_key: metric_value,
        },
        "sources": {},
    }


def test_capability_check_report_flags_regression_when_before_is_better(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    archive = runs_root / "capability_snapshots"
    before = archive / "capability_snapshot_20260217_120000.json"
    after = runs_root / "capability_snapshot_latest.json"
    _write_json(before, _snapshot_with_metric("PASS", "x.metric", 1.0))
    _write_json(after, _snapshot_with_metric("PASS", "x.metric", 0.0))

    jobs_config = tmp_path / "jobs.json"
    _write_json(
        jobs_config,
        {
            "policy": {
                "unlock": {"before_max_success": 0.6, "after_min_success": 0.9, "max_after_critical_fail_rate": 0.02},
                "harden": {"before_min_success": 0.9, "after_min_success": 0.95, "min_delta": 0.03, "max_after_critical_fail_rate": 0.02},
                "regress": {"epsilon": 0.02},
                "risk_penalty_lambda": 1.0,
            },
            "jobs": [
                {
                    "id": "job_regress",
                    "value_weight": 1.0,
                    "pass_threshold": 1.0,
                    "rules": [
                        {"path": "metrics.x.metric", "op": "ge", "value": 0.9, "critical": True}
                    ],
                }
            ],
        },
    )

    out_json = tmp_path / "capability_check.json"
    out_md = tmp_path / "capability_check.md"
    result = _run_check_report_script(
        [
            "--jobs-config",
            str(jobs_config),
            "--runs-root",
            str(runs_root),
            "--snapshot-archive-dir",
            str(archive),
            "--after-snapshot",
            str(after),
            "--before-snapshot",
            str(before),
            "--out",
            str(out_json),
            "--markdown-out",
            str(out_md),
        ]
    )
    assert result.returncode == 0, result.stderr
    payload = _read_json(out_json)
    assert payload["status"] == "FAIL"
    assert payload["summary"]["classification_counts"]["Regressed"] == 1
    assert payload["summary"]["regressed_jobs"] == ["job_regress"]
    assert "Capability Check Report" in out_md.read_text(encoding="utf-8")


def test_capability_check_report_no_baseline_when_previous_snapshot_missing(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    archive = runs_root / "capability_snapshots"
    after = runs_root / "capability_snapshot_latest.json"
    _write_json(after, _snapshot_with_metric("PASS", "x.metric", 1.0))

    jobs_config = tmp_path / "jobs.json"
    _write_json(
        jobs_config,
        {
            "policy": {"risk_penalty_lambda": 1.0},
            "jobs": [
                {
                    "id": "job_baseline",
                    "value_weight": 1.0,
                    "pass_threshold": 1.0,
                    "rules": [
                        {"path": "metrics.x.metric", "op": "ge", "value": 0.9, "critical": True}
                    ],
                }
            ],
        },
    )

    out_json = tmp_path / "capability_check.json"
    out_md = tmp_path / "capability_check.md"
    result = _run_check_report_script(
        [
            "--jobs-config",
            str(jobs_config),
            "--runs-root",
            str(runs_root),
            "--snapshot-archive-dir",
            str(archive),
            "--after-snapshot",
            str(after),
            "--out",
            str(out_json),
            "--markdown-out",
            str(out_md),
        ]
    )
    assert result.returncode == 0, result.stderr
    payload = _read_json(out_json)
    assert payload["status"] == "NO_BASELINE"
    assert payload["summary"]["has_before_snapshot"] is False
    assert payload["jobs"][0]["classification"] == "NoBaseline"
