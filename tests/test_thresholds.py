import json
import subprocess
import sys
from pathlib import Path

from goldevidencebench import thresholds


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_evaluate_checks_pass(tmp_path: Path) -> None:
    summary_path = tmp_path / "summary.json"
    _write_json(
        summary_path,
        {"overall": {"value_acc_mean": 0.9}, "retrieval": {"selected_note_rate": 0.0}},
    )
    config = {
        "checks": [
            {
                "id": "pass",
                "summary_path": str(summary_path),
                "metrics": [
                    {"path": "overall.value_acc_mean", "min": 0.5},
                    {"path": "retrieval.selected_note_rate", "max": 0.1},
                ],
            }
        ]
    }
    issues, errors = thresholds.evaluate_checks(config, root=Path("."))
    assert errors == 0
    assert any(issue.status == "pass" for issue in issues)


def test_evaluate_checks_allow_missing(tmp_path: Path) -> None:
    summary_path = tmp_path / "summary.json"
    _write_json(summary_path, {"overall": {"value_acc_mean": 0.9}})
    config = {
        "checks": [
            {
                "id": "missing-ok",
                "summary_path": str(summary_path),
                "metrics": [
                    {"path": "retrieval.gold_present_rate", "min": 0.9, "allow_missing": True}
                ],
            }
        ]
    }
    issues, errors = thresholds.evaluate_checks(config, root=Path("."))
    assert errors == 0
    assert any(issue.status == "skipped" for issue in issues)


def test_evaluate_checks_fail(tmp_path: Path) -> None:
    summary_path = tmp_path / "summary.json"
    _write_json(summary_path, {"overall": {"value_acc_mean": 0.1}})
    config = {
        "checks": [
            {
                "id": "fail",
                "summary_path": str(summary_path),
                "metrics": [{"path": "overall.value_acc_mean", "min": 0.5}],
            }
        ]
    }
    issues, errors = thresholds.evaluate_checks(config, root=Path("."))
    assert errors == 1
    assert any(issue.status == "fail" for issue in issues)


def test_evaluate_checks_skip_if(tmp_path: Path) -> None:
    summary_path = tmp_path / "summary.json"
    _write_json(
        summary_path,
        {
            "holdout": {
                "policy_task_pass_rate_min": 1.0,
                "greedy_task_pass_rate_min": 1.0,
                "sa_beats_greedy_rate": 0.0,
            }
        },
    )
    config = {
        "checks": [
            {
                "id": "skip",
                "summary_path": str(summary_path),
                "metrics": [
                    {
                        "path": "holdout.sa_beats_greedy_rate",
                        "min": 0.9,
                        "skip_if": [
                            {"path": "holdout.policy_task_pass_rate_min", "min": 0.9},
                            {"path": "holdout.greedy_task_pass_rate_min", "min": 0.9},
                        ],
                    }
                ],
            }
        ]
    }
    issues, errors = thresholds.evaluate_checks(config, root=Path("."))
    assert errors == 0
    assert any(issue.status == "skipped" for issue in issues)


def test_check_thresholds_out(tmp_path: Path) -> None:
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps({"overall": {"value_acc_mean": 0.9}}), encoding="utf-8")
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "checks": [
                    {
                        "id": "pass",
                        "summary_path": str(summary_path),
                        "metrics": [{"path": "overall.value_acc_mean", "min": 0.5}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    out_path = tmp_path / "issues.json"
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "check_thresholds.py"
    result = subprocess.run(
        [sys.executable, str(script_path), "--config", str(config_path), "--out", str(out_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert isinstance(payload.get("issues"), list)
    assert payload.get("error_count") == 0
