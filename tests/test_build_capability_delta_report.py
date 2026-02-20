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


def _write_release_snapshot_and_matrix(
    release_dir: Path,
    *,
    metrics: dict,
    families: list[dict] | None = None,
) -> None:
    snapshot_payload = {
        "benchmark": "release_quality_snapshot",
        "status": "PASS",
        "metrics": metrics,
        "gates": {},
        "integrity": {},
    }
    matrix_payload = {
        "status": "PASS",
        "coverage": {
            "required_total": 1,
            "produced_total": 1,
            "missing_families": [],
        },
        "failing_families": [],
        "families": families or [],
    }
    _write_json(release_dir / "release_quality_snapshot.json", snapshot_payload)
    _write_json(release_dir / "release_reliability_matrix.json", matrix_payload)


def _run_capability_delta_script(args: list[str]) -> subprocess.CompletedProcess[str]:
    script = _repo_root() / "scripts" / "build_capability_delta_report.py"
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(_repo_root()),
    )


def test_capability_delta_report_no_baseline_classifies_no_baseline(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    after_release = runs_root / "release_check_20260218_120654"
    _write_release_snapshot_and_matrix(
        after_release,
        metrics={"derived_reasoning_score": 0.99},
        families=[{"id": "epistemic_calibration_suite", "status": "PASS"}],
    )

    jobs_config = tmp_path / "jobs.json"
    _write_json(
        jobs_config,
        {
            "policy": {"risk_penalty_lambda": 1.0},
            "jobs": [
                {
                    "id": "epistemic_combo",
                    "value_weight": 1.0,
                    "pass_threshold": 1.0,
                    "rules": [
                        {"path": "matrix.status", "op": "eq", "value": "PASS", "critical": True},
                        {"path": "family.epistemic_calibration_suite.is_pass", "op": "ge", "value": 1, "critical": True},
                    ],
                }
            ],
        },
    )

    out_json = tmp_path / "capability_delta.json"
    out_md = tmp_path / "capability_delta.md"
    result = _run_capability_delta_script(
        [
            "--jobs-config",
            str(jobs_config),
            "--runs-root",
            str(runs_root),
            "--after-release-dir",
            str(after_release),
            "--out",
            str(out_json),
            "--markdown-out",
            str(out_md),
        ]
    )
    assert result.returncode == 0, result.stderr
    payload = _read_json(out_json)
    assert payload["status"] == "NO_BASELINE"
    assert payload["summary"]["has_before_release"] is False
    assert payload["jobs"][0]["classification"] == "NoBaseline"
    assert payload["jobs"][0]["after"]["status"] == "PASS"
    assert "Capability Delta Report" in out_md.read_text(encoding="utf-8")


def test_capability_delta_report_flags_regression_and_returns_nonzero_with_fail_flag(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    before_release = runs_root / "release_check_20260217_120000"
    after_release = runs_root / "release_check_20260218_120000"

    _write_release_snapshot_and_matrix(
        before_release,
        metrics={"unlock_metric": 0.2, "regress_metric": 1.0},
    )
    _write_release_snapshot_and_matrix(
        after_release,
        metrics={"unlock_metric": 1.0, "regress_metric": 0.0},
    )

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
                    "id": "unlock_job",
                    "value_weight": 1.0,
                    "pass_threshold": 1.0,
                    "rules": [{"path": "metrics.unlock_metric", "op": "ge", "value": 0.9, "critical": True}],
                },
                {
                    "id": "regress_job",
                    "value_weight": 1.0,
                    "pass_threshold": 1.0,
                    "rules": [{"path": "metrics.regress_metric", "op": "ge", "value": 0.9, "critical": True}],
                },
            ],
        },
    )

    out_json = tmp_path / "capability_delta.json"
    out_md = tmp_path / "capability_delta.md"
    result = _run_capability_delta_script(
        [
            "--jobs-config",
            str(jobs_config),
            "--runs-root",
            str(runs_root),
            "--before-release-dir",
            str(before_release),
            "--after-release-dir",
            str(after_release),
            "--out",
            str(out_json),
            "--markdown-out",
            str(out_md),
            "--fail-on-regression",
        ]
    )
    assert result.returncode == 1
    payload = _read_json(out_json)
    assert payload["status"] == "FAIL"
    assert payload["summary"]["classification_counts"]["Unlocked"] == 1
    assert payload["summary"]["classification_counts"]["Regressed"] == 1
    assert "unlock_job" in payload["summary"]["unlocked_jobs"]
    assert "regress_job" in payload["summary"]["regressed_jobs"]


def test_capability_delta_report_missing_after_matrix_fails_without_override(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    after_release = runs_root / "release_check_20260218_120654"
    _write_json(
        after_release / "release_quality_snapshot.json",
        {
            "benchmark": "release_quality_snapshot",
            "status": "PASS",
            "metrics": {"derived_reasoning_score": 0.99},
            "gates": {},
            "integrity": {},
        },
    )

    jobs_config = tmp_path / "jobs.json"
    _write_json(
        jobs_config,
        {
            "policy": {"risk_penalty_lambda": 1.0},
            "jobs": [
                {
                    "id": "strict_release_core",
                    "value_weight": 1.0,
                    "pass_threshold": 1.0,
                    "rules": [{"path": "matrix.status", "op": "eq", "value": "PASS", "critical": True}],
                }
            ],
        },
    )

    out_json = tmp_path / "capability_delta.json"
    out_md = tmp_path / "capability_delta.md"
    result = _run_capability_delta_script(
        [
            "--jobs-config",
            str(jobs_config),
            "--runs-root",
            str(runs_root),
            "--after-release-dir",
            str(after_release),
            "--out",
            str(out_json),
            "--markdown-out",
            str(out_md),
        ]
    )
    assert result.returncode != 0
    assert "After release artifacts missing" in f"{result.stdout}\n{result.stderr}"


def test_capability_delta_report_missing_after_matrix_degrades_to_no_baseline(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    after_release = runs_root / "release_check_20260218_120654"
    _write_json(
        after_release / "release_quality_snapshot.json",
        {
            "benchmark": "release_quality_snapshot",
            "status": "PASS",
            "metrics": {"derived_reasoning_score": 0.99},
            "gates": {},
            "integrity": {},
        },
    )

    jobs_config = tmp_path / "jobs.json"
    _write_json(
        jobs_config,
        {
            "policy": {"risk_penalty_lambda": 1.0},
            "jobs": [
                {
                    "id": "strict_release_core",
                    "value_weight": 1.0,
                    "pass_threshold": 1.0,
                    "rules": [{"path": "matrix.status", "op": "eq", "value": "PASS", "critical": True}],
                }
            ],
        },
    )

    out_json = tmp_path / "capability_delta.json"
    out_md = tmp_path / "capability_delta.md"
    result = _run_capability_delta_script(
        [
            "--jobs-config",
            str(jobs_config),
            "--runs-root",
            str(runs_root),
            "--after-release-dir",
            str(after_release),
            "--allow-missing-after-matrix",
            "--out",
            str(out_json),
            "--markdown-out",
            str(out_md),
        ]
    )
    assert result.returncode == 0, result.stderr
    payload = _read_json(out_json)
    assert payload["status"] == "NO_BASELINE"
    assert payload["summary"]["has_before_release"] is False
    assert payload["summary"]["degraded_missing_after_matrix"] is True
