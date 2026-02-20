from __future__ import annotations

import json
import os
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


def _run_powershell_file(
    script: Path,
    args: list[str],
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if not powershell:
        pytest.skip("pwsh/powershell executable is required for run_capability_check integration tests")
    return subprocess.run(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(_repo_root()),
        env=env,
    )


def test_run_capability_check_writes_snapshot_and_report(tmp_path: Path) -> None:
    repo_root = _repo_root()
    script = repo_root / "scripts" / "run_capability_check.ps1"
    runs_root = tmp_path / "runs"

    _write_json(
        runs_root / "real_world_utility_eval_latest.json",
        {
            "status": "PASS",
            "task_count": 40,
            "comparison": {"first_pass_usable_delta": 0.5, "clarification_burden_delta": 0.4},
            "pass_inputs": {"false_commit_improvement": 0.08, "correction_improvement": 0.6},
            "pass_checks": {"base_requirements": True, "burden_tradeoff_requirements": True},
        },
    )
    _write_json(
        runs_root / "ui_minipilot_notepad_gate.json",
        {
            "rows": 8,
            "metrics": {"wrong_action_rate": 0.0, "post_action_verify_rate": 1.0},
            "sequence_metrics": {"task_pass_rate": 1.0},
        },
    )
    _write_json(
        runs_root / "codex_next_step_report.json",
        {
            "status": "PASS",
            "blockers": [],
            "next_actions": ["a"],
            "foundation_statuses": {"fam": {"status": "PASS"}},
        },
    )
    _write_json(
        runs_root / "rpa_control_latest.json",
        {"mode": "act", "decision": "answer", "confidence": 0.8, "risk": 0.2},
    )

    jobs_config = tmp_path / "jobs.json"
    _write_json(
        jobs_config,
        {
            "policy": {"risk_penalty_lambda": 1.0},
            "jobs": [
                {
                    "id": "utility_present",
                    "pass_threshold": 1.0,
                    "rules": [
                        {"path": "metrics.utility.status", "op": "eq", "value": "PASS", "critical": True}
                    ],
                }
            ],
        },
    )

    result = _run_powershell_file(
        script,
        [
            "-RunsRoot",
            str(runs_root),
            "-JobsConfigPath",
            str(jobs_config),
        ],
    )
    assert result.returncode == 0, result.stderr

    snapshot = _read_json(runs_root / "capability_snapshot_latest.json")
    report = _read_json(runs_root / "capability_check_latest.json")
    assert snapshot["status"] == "WARN" or snapshot["status"] == "PASS"
    assert report["status"] == "NO_BASELINE"
    assert (runs_root / "latest_capability_snapshot").exists()
    assert (runs_root / "latest_capability_check").exists()
    assert (runs_root / "latest_capability_check_md").exists()


def test_run_capability_check_rejects_liveeval_plus_existing_snapshot(tmp_path: Path) -> None:
    repo_root = _repo_root()
    script = repo_root / "scripts" / "run_capability_check.ps1"
    runs_root = tmp_path / "runs"
    jobs_config = tmp_path / "jobs.json"

    _write_json(
        jobs_config,
        {
            "policy": {"risk_penalty_lambda": 1.0},
            "jobs": [
                {
                    "id": "utility_present",
                    "pass_threshold": 1.0,
                    "rules": [
                        {"path": "metrics.utility.status", "op": "eq", "value": "PASS", "critical": True}
                    ],
                }
            ],
        },
    )

    result = _run_powershell_file(
        script,
        [
            "-RunsRoot",
            str(runs_root),
            "-JobsConfigPath",
            str(jobs_config),
            "-RunLiveEvals",
            "-UseExistingSnapshot",
        ],
    )
    assert result.returncode != 0
    combined = f"{result.stdout}\n{result.stderr}"
    assert "RunLiveEvals and UseExistingSnapshot" in combined


def test_run_capability_check_rejects_placeholder_modelpath_without_env_for_llama_cpp_adapter(tmp_path: Path) -> None:
    repo_root = _repo_root()
    script = repo_root / "scripts" / "run_capability_check.ps1"
    runs_root = tmp_path / "runs"
    jobs_config = tmp_path / "jobs.json"

    _write_json(
        jobs_config,
        {
            "policy": {"risk_penalty_lambda": 1.0},
            "jobs": [
                {
                    "id": "utility_present",
                    "pass_threshold": 1.0,
                    "rules": [
                        {"path": "metrics.utility.status", "op": "eq", "value": "PASS", "critical": True}
                    ],
                }
            ],
        },
    )

    env = os.environ.copy()
    env["GOLDEVIDENCEBENCH_MODEL"] = ""
    result = _run_powershell_file(
        script,
        [
            "-RunsRoot",
            str(runs_root),
            "-JobsConfigPath",
            str(jobs_config),
            "-RunLiveEvals",
            "-Adapter",
            "goldevidencebench.adapters.retrieval_llama_cpp_adapter:create_adapter",
            "-ModelPath",
            "<MODEL_PATH>",
            "-SkipLiveUtilityEval",
            "-SkipLiveCasePack",
            "-SkipLiveTrustDemo",
        ],
        env=env,
    )
    assert result.returncode != 0
    combined = f"{result.stdout}\n{result.stderr}"
    assert "RunLiveEvals requires a real -ModelPath" in combined


def test_run_capability_check_accepts_placeholder_modelpath_with_env_when_live_steps_skipped(tmp_path: Path) -> None:
    repo_root = _repo_root()
    script = repo_root / "scripts" / "run_capability_check.ps1"
    runs_root = tmp_path / "runs"

    _write_json(
        runs_root / "real_world_utility_eval_latest.json",
        {
            "status": "PASS",
            "task_count": 40,
            "comparison": {"first_pass_usable_delta": 0.5, "clarification_burden_delta": 0.4},
            "pass_inputs": {"false_commit_improvement": 0.08, "correction_improvement": 0.6},
            "pass_checks": {"base_requirements": True, "burden_tradeoff_requirements": True},
        },
    )
    _write_json(
        runs_root / "ui_minipilot_notepad_gate.json",
        {
            "rows": 8,
            "metrics": {"wrong_action_rate": 0.0, "post_action_verify_rate": 1.0},
            "sequence_metrics": {"task_pass_rate": 1.0},
        },
    )
    _write_json(
        runs_root / "codex_next_step_report.json",
        {
            "status": "PASS",
            "blockers": [],
            "next_actions": ["a"],
            "foundation_statuses": {"fam": {"status": "PASS"}},
        },
    )
    _write_json(
        runs_root / "rpa_control_latest.json",
        {"mode": "act", "decision": "answer", "confidence": 0.8, "risk": 0.2},
    )

    jobs_config = tmp_path / "jobs.json"
    _write_json(
        jobs_config,
        {
            "policy": {"risk_penalty_lambda": 1.0},
            "jobs": [
                {
                    "id": "utility_present",
                    "pass_threshold": 1.0,
                    "rules": [
                        {"path": "metrics.utility.status", "op": "eq", "value": "PASS", "critical": True}
                    ],
                }
            ],
        },
    )

    env = os.environ.copy()
    env["GOLDEVIDENCEBENCH_MODEL"] = "dummy_model.gguf"
    result = _run_powershell_file(
        script,
        [
            "-RunsRoot",
            str(runs_root),
            "-JobsConfigPath",
            str(jobs_config),
            "-RunLiveEvals",
            "-ModelPath",
            "<MODEL_PATH>",
            "-SkipLiveUtilityEval",
            "-SkipLiveCasePack",
            "-SkipLiveTrustDemo",
        ],
        env=env,
    )
    assert result.returncode == 0, result.stderr


def test_run_capability_check_accepts_placeholder_modelpath_without_env_for_server_adapter_when_live_steps_skipped(
    tmp_path: Path,
) -> None:
    repo_root = _repo_root()
    script = repo_root / "scripts" / "run_capability_check.ps1"
    runs_root = tmp_path / "runs"

    _write_json(
        runs_root / "real_world_utility_eval_latest.json",
        {
            "status": "PASS",
            "task_count": 40,
            "comparison": {"first_pass_usable_delta": 0.5, "clarification_burden_delta": 0.4},
            "pass_inputs": {"false_commit_improvement": 0.08, "correction_improvement": 0.6},
            "pass_checks": {"base_requirements": True, "burden_tradeoff_requirements": True},
        },
    )
    _write_json(
        runs_root / "ui_minipilot_notepad_gate.json",
        {
            "rows": 8,
            "metrics": {"wrong_action_rate": 0.0, "post_action_verify_rate": 1.0},
            "sequence_metrics": {"task_pass_rate": 1.0},
        },
    )
    _write_json(
        runs_root / "codex_next_step_report.json",
        {
            "status": "PASS",
            "blockers": [],
            "next_actions": ["a"],
            "foundation_statuses": {"fam": {"status": "PASS"}},
        },
    )
    _write_json(
        runs_root / "rpa_control_latest.json",
        {"mode": "act", "decision": "answer", "confidence": 0.8, "risk": 0.2},
    )

    jobs_config = tmp_path / "jobs.json"
    _write_json(
        jobs_config,
        {
            "policy": {"risk_penalty_lambda": 1.0},
            "jobs": [
                {
                    "id": "utility_present",
                    "pass_threshold": 1.0,
                    "rules": [
                        {"path": "metrics.utility.status", "op": "eq", "value": "PASS", "critical": True}
                    ],
                }
            ],
        },
    )

    env = os.environ.copy()
    env["GOLDEVIDENCEBENCH_MODEL"] = ""
    result = _run_powershell_file(
        script,
        [
            "-RunsRoot",
            str(runs_root),
            "-JobsConfigPath",
            str(jobs_config),
            "-RunLiveEvals",
            "-Adapter",
            "goldevidencebench.adapters.llama_server_adapter:create_adapter",
            "-ModelPath",
            "<MODEL_PATH>",
            "-SkipLiveUtilityEval",
            "-SkipLiveCasePack",
            "-SkipLiveTrustDemo",
        ],
        env=env,
    )
    assert result.returncode == 0, result.stderr


def test_run_capability_check_rejects_live_drift_baseline_for_nonretrieval_adapter(tmp_path: Path) -> None:
    repo_root = _repo_root()
    script = repo_root / "scripts" / "run_capability_check.ps1"
    runs_root = tmp_path / "runs"
    jobs_config = tmp_path / "jobs.json"

    _write_json(
        jobs_config,
        {
            "policy": {"risk_penalty_lambda": 1.0},
            "jobs": [
                {
                    "id": "utility_present",
                    "pass_threshold": 1.0,
                    "rules": [
                        {"path": "metrics.utility.status", "op": "eq", "value": "PASS", "critical": True}
                    ],
                }
            ],
        },
    )

    result = _run_powershell_file(
        script,
        [
            "-RunsRoot",
            str(runs_root),
            "-JobsConfigPath",
            str(jobs_config),
            "-RunLiveEvals",
            "-Adapter",
            "goldevidencebench.adapters.llama_server_adapter:create_adapter",
            "-RunLiveDriftBaseline",
            "-SkipLiveUtilityEval",
            "-SkipLiveCasePack",
            "-SkipLiveTrustDemo",
        ],
    )
    assert result.returncode != 0
    combined = f"{result.stdout}\n{result.stderr}"
    assert "RunLiveDriftBaseline requires" in combined
    assert "retrieval_llama_cpp_adapter" in combined
