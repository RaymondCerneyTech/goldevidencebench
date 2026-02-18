from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def _powershell_executable() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell")


def test_preflight_output_json_schema(tmp_path: Path) -> None:
    if not _powershell_executable():
        pytest.skip("pwsh/powershell executable is required for preflight CLI integration tests")

    out_path = tmp_path / "preflight_latest.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goldevidencebench",
            "preflight",
            "--profile",
            "cross_app_test",
            "--stage",
            "dev",
            "--data",
            "fixture",
            "--adapter",
            "goldevidencebench.adapters.mock_adapter:create_adapter",
            "--out",
            str(out_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["status"] in {"PASS", "FAIL"}
    assert isinstance(payload["blocked_gates"], list)
    assert isinstance(payload["top_fixes"], list)
    assert isinstance(payload["next_command"], str)
    assert payload["profile"] == "cross_app_test"


def test_geb_alias_registered_in_pyproject() -> None:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    assert 'geb = "goldevidencebench.cli:main"' in text
