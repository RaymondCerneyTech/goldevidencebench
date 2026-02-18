from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


def _powershell_executable() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell")


def test_cross_app_pack_runner_writes_expected_artifacts(tmp_path: Path) -> None:
    powershell = _powershell_executable()
    if not powershell:
        pytest.skip("pwsh/powershell executable is required for runner integration tests")

    out_root = tmp_path / "cross_app_pack_run"
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_cross_app_intent_preservation_pack.ps1"
    )
    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-OutRoot",
            str(out_root),
            "-Adapter",
            "goldevidencebench.adapters.mock_adapter:create_adapter",
            "-Stage",
            "target",
            "-DataMode",
            "fixture",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    summary_path = out_root / "cross_app_intent_preservation_pack_summary.json"
    rows_path = out_root / "cross_app_intent_preservation_pack_rows.jsonl"
    live_smoke_summary_path = out_root / "live_smoke_summary.json"
    assert summary_path.exists()
    assert rows_path.exists()
    assert live_smoke_summary_path.exists()

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["benchmark"] == "cross_app_intent_preservation_pack"
    assert summary["hard_gate_status"] == "PASS"
    assert summary["holdout"]["status"] == "PASS"
