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


def _run_builder(args: list[str]) -> subprocess.CompletedProcess[str]:
    script = _repo_root() / "scripts" / "build_trap_contract_audit.py"
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(_repo_root()),
    )


def test_trap_contract_audit_passes_for_strong_on_off_contrast(tmp_path: Path) -> None:
    root = tmp_path
    runs = root / "runs"
    _write_json(
        runs / "drift_holdout_compare_001" / "fix_prefer_set_latest" / "summary.json",
        {"drift": {"step_rate": 0.0}, "overall": {"exact_acc_mean": 1.0}},
    )
    _write_json(
        runs / "drift_holdout_compare_002" / "fix_prefer_set_latest" / "summary.json",
        {"drift": {"step_rate": 0.1}, "overall": {"exact_acc_mean": 1.0}},
    )
    _write_json(
        runs / "drift_holdout_compare_001" / "baseline_latest_step" / "summary.json",
        {"drift": {"step_rate": 0.9}, "overall": {"exact_acc_mean": 0.0}},
    )
    _write_json(
        runs / "drift_holdout_compare_002" / "baseline_latest_step" / "summary.json",
        {"drift": {"step_rate": 0.8}, "overall": {"exact_acc_mean": 0.0}},
    )

    config = root / "trap_jobs.json"
    _write_json(
        config,
        {
            "version": "1.0",
            "defaults": {
                "min_on_expected_rate": 0.9,
                "min_off_expected_rate": 0.9,
                "min_runs_per_condition": 2,
                "max_on_score_stddev": 0.2,
                "max_off_score_stddev": 0.2,
                "min_adapter_pass_count": 1,
            },
            "traps": [
                {
                    "id": "stale_tab_state_drift",
                    "cells": [
                        {
                            "condition": "on",
                            "adapter": "retrieval_llama_cpp_adapter",
                            "path_glob": "runs/drift_holdout_compare_*/fix_prefer_set_latest/summary.json",
                            "expect": {"path": "drift.step_rate", "max": 0.25},
                            "metric_path": "drift.step_rate",
                            "latest": 10,
                        },
                        {
                            "condition": "off",
                            "adapter": "retrieval_llama_cpp_adapter",
                            "path_glob": "runs/drift_holdout_compare_*/baseline_latest_step/summary.json",
                            "expect": {"path": "drift.step_rate", "min": 0.5},
                            "metric_path": "drift.step_rate",
                            "latest": 10,
                        },
                    ],
                    "effect_check": {
                        "on_metric_path": "drift.step_rate",
                        "off_metric_path": "drift.step_rate",
                        "direction": "off_minus_on",
                        "min_delta": 0.2,
                        "aggregate": "mean",
                    },
                    "collateral_checks": [
                        {
                            "id": "on_exact_acc_floor",
                            "condition": "on",
                            "path": "overall.exact_acc_mean",
                            "aggregate": "mean",
                            "min": 0.95,
                        }
                    ],
                }
            ],
        },
    )

    out_json = root / "trap_contract_audit.json"
    out_md = root / "trap_contract_audit.md"
    result = _run_builder(
        [
            "--config",
            str(config),
            "--root",
            str(root),
            "--out",
            str(out_json),
            "--markdown-out",
            str(out_md),
        ]
    )
    assert result.returncode == 0, result.stderr
    payload = _read_json(out_json)
    assert payload["status"] == "PASS"
    assert payload["summary"]["pass_count"] == 1
    trap = payload["traps"][0]
    assert trap["status"] == "PASS"
    assert trap["checks"]["off_fails_on_passes"] == "PASS"
    assert trap["checks"]["effect_size"] == "PASS"
    assert trap["checks"]["run_stability"] == "PASS"
    assert trap["checks"]["adapter_coverage"] == "PASS"
    assert trap["checks"]["collateral_regression"] == "PASS"
    assert "Trap Contract Audit" in out_md.read_text(encoding="utf-8")


def test_trap_contract_audit_fails_when_effect_size_is_too_small(tmp_path: Path) -> None:
    root = tmp_path
    runs = root / "runs"
    _write_json(
        runs / "drift_holdout_compare_001" / "fix_prefer_set_latest" / "summary.json",
        {"drift": {"step_rate": 0.45}, "overall": {"exact_acc_mean": 1.0}},
    )
    _write_json(
        runs / "drift_holdout_compare_001" / "baseline_latest_step" / "summary.json",
        {"drift": {"step_rate": 0.55}, "overall": {"exact_acc_mean": 0.0}},
    )

    config = root / "trap_jobs.json"
    _write_json(
        config,
        {
            "version": "1.0",
            "defaults": {"min_runs_per_condition": 1},
            "traps": [
                {
                    "id": "stale_tab_state_drift",
                    "cells": [
                        {
                            "condition": "on",
                            "adapter": "retrieval_llama_cpp_adapter",
                            "path_glob": "runs/drift_holdout_compare_*/fix_prefer_set_latest/summary.json",
                            "expect": {"path": "drift.step_rate", "max": 0.5},
                            "metric_path": "drift.step_rate",
                            "latest": 10,
                        },
                        {
                            "condition": "off",
                            "adapter": "retrieval_llama_cpp_adapter",
                            "path_glob": "runs/drift_holdout_compare_*/baseline_latest_step/summary.json",
                            "expect": {"path": "drift.step_rate", "min": 0.5},
                            "metric_path": "drift.step_rate",
                            "latest": 10,
                        },
                    ],
                    "effect_check": {
                        "on_metric_path": "drift.step_rate",
                        "off_metric_path": "drift.step_rate",
                        "direction": "off_minus_on",
                        "min_delta": 0.2,
                        "aggregate": "mean",
                    },
                }
            ],
        },
    )

    out_json = root / "trap_contract_audit.json"
    out_md = root / "trap_contract_audit.md"
    result = _run_builder(
        [
            "--config",
            str(config),
            "--root",
            str(root),
            "--out",
            str(out_json),
            "--markdown-out",
            str(out_md),
        ]
    )
    assert result.returncode == 1
    payload = _read_json(out_json)
    assert payload["status"] == "FAIL"
    trap = payload["traps"][0]
    assert trap["status"] == "FAIL"
    assert trap["checks"]["effect_size"] == "FAIL"


def test_trap_contract_audit_includes_release_family_placeholders_as_no_data(tmp_path: Path) -> None:
    root = tmp_path
    contract = root / "release_gate_contract.json"
    _write_json(
        contract,
        {
            "strict_release": {
                "required_reliability_families": [
                    {"id": "alpha_family"},
                    {"id": "beta_family"},
                ]
            }
        },
    )
    config = root / "trap_jobs.json"
    _write_json(
        config,
        {
            "version": "1.0",
            "include_release_families": {
                "enabled": True,
                "contract_path": str(contract),
            },
            "traps": [],
        },
    )

    out_json = root / "trap_contract_audit.json"
    out_md = root / "trap_contract_audit.md"
    result = _run_builder(
        [
            "--config",
            str(config),
            "--root",
            str(root),
            "--out",
            str(out_json),
            "--markdown-out",
            str(out_md),
        ]
    )
    assert result.returncode == 0, result.stderr
    payload = _read_json(out_json)
    assert payload["status"] == "NO_DATA"
    assert payload["summary"]["no_data_count"] == 2

    strict_result = _run_builder(
        [
            "--config",
            str(config),
            "--root",
            str(root),
            "--out",
            str(out_json),
            "--markdown-out",
            str(out_md),
            "--fail-on-no-data",
        ]
    )
    assert strict_result.returncode == 1

