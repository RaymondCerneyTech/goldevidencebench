from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_cross_app_pack_usecase_check_is_warn_only() -> None:
    config_path = _repo_root() / "configs" / "usecase_checks.json"
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    checks = payload.get("checks")
    assert isinstance(checks, list)

    entry = None
    for check in checks:
        if isinstance(check, dict) and check.get("id") == "cross_app_intent_preservation_pack":
            entry = check
            break
    assert entry is not None
    assert entry.get("severity") == "warn"
    assert entry.get("summary_path") == "runs/release_gates/cross_app_intent_preservation_pack/summary.json"


def test_cross_app_pack_warn_only_threshold_failure_does_not_fail_process(tmp_path: Path) -> None:
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "holdout": {
                    "means": {
                        "unauthorized_substitution_rate": 0.1,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    config_path = tmp_path / "checks.json"
    config_path.write_text(
        json.dumps(
            {
                "checks": [
                    {
                        "id": "cross_app_intent_preservation_pack",
                        "summary_path": str(summary_path),
                        "severity": "warn",
                        "metrics": [
                            {
                                "path": "holdout.means.unauthorized_substitution_rate",
                                "max": 0.0,
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    script_path = _repo_root() / "scripts" / "check_thresholds.py"
    result = subprocess.run(
        [sys.executable, str(script_path), "--config", str(config_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "FAIL(warn)" in result.stdout
