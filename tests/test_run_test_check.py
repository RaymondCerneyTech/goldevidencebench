from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _run_powershell_file(script: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if not powershell:
        pytest.skip("pwsh/powershell executable is required for run_test_check integration tests")
    return subprocess.run(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(_repo_root()),
    )


def _make_contract(path: Path, *, artifact_path: Path) -> None:
    _write_json(
        path,
        {
            "contract_id": "release_gate_contract",
            "version": "test",
            "strict_release": {
                "freshness_policy": "allow_latest",
                "canary_policy": "strict",
                "required_reliability_families": [
                    {
                        "id": "novel_continuity",
                        "artifact_path": str(artifact_path),
                        "stage": "target",
                        "allowed_statuses": ["PASS"],
                    }
                ],
                "utility_gate": {
                    "required": False,
                    "producer_mode": "deferred",
                    "producer_script": "scripts/run_real_world_utility_eval.ps1",
                    "artifact_path": "runs/real_world_utility_eval_latest.json",
                },
            },
        },
    )


def _make_strict_freshness_contract(path: Path, *, artifact_path: Path) -> None:
    _write_json(
        path,
        {
            "contract_id": "release_gate_contract",
            "version": "test",
            "strict_release": {
                "freshness_policy": "must_regenerate_this_run",
                "canary_policy": "strict",
                "required_reliability_families": [
                    {
                        "id": "novel_continuity",
                        "artifact_path": str(artifact_path),
                        "stage": "target",
                        "allowed_statuses": ["PASS"],
                    }
                ],
                "utility_gate": {
                    "required": False,
                    "producer_mode": "deferred",
                    "producer_script": "scripts/run_real_world_utility_eval.ps1",
                    "artifact_path": "runs/real_world_utility_eval_latest.json",
                },
            },
        },
    )


def test_run_test_check_use_existing_only_passes_with_clean_matrix(tmp_path: Path) -> None:
    repo_root = _repo_root()
    script = repo_root / "scripts" / "run_test_check.ps1"
    contract = tmp_path / "contract.json"
    summary_artifact = tmp_path / "novel_continuity_reliability_latest.json"
    out_dir = tmp_path / "out_pass"

    _write_json(summary_artifact, {"status": "PASS", "failures": [], "generated_at_utc": "2026-02-18T00:00:00Z"})
    _make_contract(contract, artifact_path=summary_artifact)

    result = _run_powershell_file(
        script,
        [
            "-Adapter",
            "goldevidencebench.adapters.mock_adapter:create_adapter",
            "-ContractPath",
            str(contract),
            "-ContractSchemaPath",
            "schemas/release_gate_contract.schema.json",
            "-UseExistingArtifactsOnly",
            "-SkipReliabilitySignal",
            "-MaxRounds",
            "1",
            "-OutDir",
            str(out_dir),
        ],
    )
    assert result.returncode == 0, result.stderr
    summary = _read_json(out_dir / "test_check_summary.json")
    assert summary["status"] == "PASS"
    assert summary["final_matrix_status"] == "PASS"


def test_run_test_check_ignores_freshness_in_iteration_by_default(tmp_path: Path) -> None:
    repo_root = _repo_root()
    script = repo_root / "scripts" / "run_test_check.ps1"
    contract = tmp_path / "contract_strict_freshness.json"
    summary_artifact = tmp_path / "novel_continuity_reliability_latest.json"
    out_dir = tmp_path / "out_strict_freshness"

    _write_json(summary_artifact, {"status": "PASS", "failures": [], "generated_at_utc": "2026-02-18T00:00:00Z"})
    _make_strict_freshness_contract(contract, artifact_path=summary_artifact)

    result = _run_powershell_file(
        script,
        [
            "-Adapter",
            "goldevidencebench.adapters.mock_adapter:create_adapter",
            "-ContractPath",
            str(contract),
            "-ContractSchemaPath",
            "schemas/release_gate_contract.schema.json",
            "-UseExistingArtifactsOnly",
            "-SkipReliabilitySignal",
            "-MaxRounds",
            "1",
            "-OutDir",
            str(out_dir),
        ],
    )
    assert result.returncode == 0, result.stderr
    summary = _read_json(out_dir / "test_check_summary.json")
    assert summary["status"] == "PASS"
    assert summary["final_matrix_status"] == "PASS"
    assert str(summary["iteration_contract_path"]).endswith("release_gate_contract_iteration.json")


def test_run_test_check_use_existing_only_fails_on_matrix_failure(tmp_path: Path) -> None:
    repo_root = _repo_root()
    script = repo_root / "scripts" / "run_test_check.ps1"
    contract = tmp_path / "contract.json"
    summary_artifact = tmp_path / "novel_continuity_reliability_latest.json"
    out_dir = tmp_path / "out_fail"

    _write_json(summary_artifact, {"status": "FAIL", "failures": ["holdout.status=FAIL"], "generated_at_utc": "2026-02-18T00:00:00Z"})
    _make_contract(contract, artifact_path=summary_artifact)

    result = _run_powershell_file(
        script,
        [
            "-Adapter",
            "goldevidencebench.adapters.mock_adapter:create_adapter",
            "-ContractPath",
            str(contract),
            "-ContractSchemaPath",
            "schemas/release_gate_contract.schema.json",
            "-UseExistingArtifactsOnly",
            "-SkipReliabilitySignal",
            "-MaxRounds",
            "1",
            "-OutDir",
            str(out_dir),
        ],
    )
    assert result.returncode != 0
    summary = _read_json(out_dir / "test_check_summary.json")
    assert summary["status"] == "FAIL"
    assert summary["final_matrix_status"] == "FAIL"


def test_run_test_check_artifact_audit_covers_full_release_reliability_set(tmp_path: Path) -> None:
    repo_root = _repo_root()
    script = repo_root / "scripts" / "run_test_check.ps1"
    contract = tmp_path / "contract.json"
    summary_artifact = tmp_path / "novel_continuity_reliability_latest.json"
    out_dir = tmp_path / "out_artifact_audit"

    _write_json(summary_artifact, {"status": "PASS", "failures": [], "generated_at_utc": "2026-02-18T00:00:00Z"})
    _make_contract(contract, artifact_path=summary_artifact)

    result = _run_powershell_file(
        script,
        [
            "-Adapter",
            "goldevidencebench.adapters.mock_adapter:create_adapter",
            "-ContractPath",
            str(contract),
            "-ContractSchemaPath",
            "schemas/release_gate_contract.schema.json",
            "-UseExistingArtifactsOnly",
            "-SkipReliabilitySignal",
            "-MaxRounds",
            "1",
            "-OutDir",
            str(out_dir),
        ],
    )
    assert result.returncode == 0, result.stderr
    audit = _read_json(out_dir / "artifact_audit.json")
    by_key = {row["key"]: row for row in audit}
    assert "compression_roundtrip_generalization_reliability" in by_key
    assert "novel_continuity_long_horizon_reliability" in by_key
    assert "myopic_planning_traps_reliability" in by_key
    assert "referential_indexing_suite_reliability" in by_key
    assert "epistemic_calibration_suite_reliability" in by_key
    assert "authority_under_interference_hardening_reliability" in by_key
    assert by_key["drift_holdout_gate"]["status_enforced"] is False
