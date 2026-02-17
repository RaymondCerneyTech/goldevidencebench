from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_noop_powershell(path: Path, marker_path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'Set-Content -Path "{marker_path}" -Value "ran"\nexit 0\n',
        encoding="utf-8",
    )


def _write_config(path: Path, script_path: Path) -> None:
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


def _run_demo(
    *,
    config_path: Path,
    snapshot_path: Path,
) -> subprocess.CompletedProcess[str]:
    powershell = shutil.which("powershell")
    if not powershell:
        pytest.skip("powershell executable is required for run_demo integration tests")
    script = Path(__file__).resolve().parents[1] / "scripts" / "run_demo.ps1"
    return subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-ModelPath",
            "dummy-model-path",
            "-Preset",
            "test_preset",
            "-ConfigPath",
            str(config_path),
            "-UseRpaController",
            "-ControlSnapshotPath",
            str(snapshot_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_run_demo_controller_blocks_with_reason_and_nonzero_exit(tmp_path: Path) -> None:
    marker = tmp_path / "marker.txt"
    preset_script = tmp_path / "preset.ps1"
    _write_noop_powershell(preset_script, marker)
    config = tmp_path / "demo_config.json"
    _write_config(config, preset_script)

    snapshot = tmp_path / "snapshot.json"
    _write_json(
        snapshot,
        {
            "control_contract_version": "0.2",
            "mode": "reason",
            "decision": "ask",
            "control_v2": {
                "policy": {
                    "blocked": True,
                    "reasons": [{"code": "MISSING_NEEDED_INFO"}],
                }
            },
        },
    )

    result = _run_demo(config_path=config, snapshot_path=snapshot)
    assert result.returncode != 0
    combined = f"{result.stdout}\n{result.stderr}"
    assert "Runtime policy blocked demo execution" in combined
    assert "Next action: ask" in combined
    assert not marker.exists()


def test_run_demo_controller_allows_answer_path(tmp_path: Path) -> None:
    marker = tmp_path / "marker.txt"
    preset_script = tmp_path / "preset.ps1"
    _write_noop_powershell(preset_script, marker)
    config = tmp_path / "demo_config.json"
    _write_config(config, preset_script)

    snapshot = tmp_path / "snapshot.json"
    _write_json(
        snapshot,
        {
            "control_contract_version": "0.2",
            "mode": "act",
            "decision": "answer",
            "control_v2": {
                "policy": {
                    "blocked": False,
                    "reasons": [],
                }
            },
        },
    )

    result = _run_demo(config_path=config, snapshot_path=snapshot)
    assert result.returncode == 0, result.stderr
    assert marker.exists()
