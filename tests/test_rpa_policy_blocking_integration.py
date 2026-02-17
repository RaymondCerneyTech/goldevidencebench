from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _write_noop_powershell(path: Path, marker_path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'Set-Content -Path "{marker_path}" -Value "ran"\nexit 0\n',
        encoding="utf-8",
    )


def _write_demo_config(path: Path, script_path: Path) -> None:
    payload = {
        "defaults": {},
        "presets": [
            {
                "name": "test_preset",
                "mode": "fixture",
                "description": "test preset",
                "script": str(script_path),
                "args": [],
            }
        ],
    }
    _write_json(path, payload)


def _planner_fixture_row() -> dict:
    return {
        "id": "row_1",
        "task_id": "task_1",
        "step_index": 1,
        "instruction": "Click continue",
        "allow_overlay": False,
        "candidates": [
            {
                "candidate_id": "cand_continue",
                "action_type": "click",
                "label": "Continue",
                "visible": True,
                "enabled": True,
                "modal_scope": "main",
                "next_state": {"screen": "done"},
            }
        ],
    }


def test_router_and_planner_blocking_from_fixture_snapshots(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]

    # Router: run_demo should block with deterministic unauthorized substitution code.
    powershell = shutil.which("powershell")
    if not powershell:
        pytest.skip("powershell executable is required for run_demo integration tests")
    marker = tmp_path / "marker.txt"
    preset_script = tmp_path / "preset.ps1"
    _write_noop_powershell(preset_script, marker)
    demo_config = tmp_path / "demo_config.json"
    _write_demo_config(demo_config, preset_script)

    router_snapshot = (
        repo_root
        / "tests"
        / "fixtures"
        / "control_snapshots"
        / "router_block_unauthorized_substitution.json"
    )
    run_demo_script = repo_root / "scripts" / "run_demo.ps1"
    demo_result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(run_demo_script),
            "-ModelPath",
            "dummy-model-path",
            "-Preset",
            "test_preset",
            "-ConfigPath",
            str(demo_config),
            "-UseRpaController",
            "-ControlSnapshotPath",
            str(router_snapshot),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert demo_result.returncode != 0
    demo_text = f"{demo_result.stdout}\n{demo_result.stderr}"
    assert "Runtime policy blocked demo execution" in demo_text
    assert "reason=UNAUTHORIZED_SUBSTITUTION" in demo_text
    assert not marker.exists()

    # Planner: select_ui_plan should block with deterministic IC reason code.
    planner_fixture = tmp_path / "planner_fixture.jsonl"
    _write_jsonl(planner_fixture, [_planner_fixture_row()])
    planner_snapshot = (
        repo_root
        / "tests"
        / "fixtures"
        / "control_snapshots"
        / "planner_block_ic_snapshot.json"
    )
    planner_out = tmp_path / "planner_out.json"
    select_script = repo_root / "scripts" / "select_ui_plan.py"
    planner_result = subprocess.run(
        [
            sys.executable,
            str(select_script),
            "--fixture",
            str(planner_fixture),
            "--task-id",
            "task_1",
            "--planner",
            "policy",
            "--out",
            str(planner_out),
            "--use-rpa-controller",
            "--control-snapshot",
            str(planner_snapshot),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert planner_result.returncode == 0, planner_result.stderr
    planner_payload = json.loads(planner_out.read_text(encoding="utf-8"))
    step = planner_payload["steps"][0]
    assert step["selected_id"] is None
    assert step["policy_mode"] == "reason"
    assert step["policy_decision"] == "retrieve"
    assert step["policy_block_reason"] == "LOW_IC"
