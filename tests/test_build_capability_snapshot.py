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


def _run_snapshot_script(args: list[str]) -> subprocess.CompletedProcess[str]:
    script = _repo_root() / "scripts" / "build_capability_snapshot.py"
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(_repo_root()),
    )


def _write_minimal_nontrap_artifacts(runs_root: Path) -> None:
    _write_json(
        runs_root / "real_world_utility_eval_latest.json",
        {
            "benchmark": "real_world_utility_eval",
            "status": "PASS",
            "task_count": 40,
            "comparison": {
                "first_pass_usable_delta": 0.40,
                "clarification_burden_delta": 0.40,
            },
            "pass_inputs": {
                "false_commit_improvement": 0.10,
                "correction_improvement": 0.60,
            },
            "pass_checks": {
                "base_requirements": True,
                "burden_tradeoff_requirements": True,
            },
        },
    )
    _write_json(
        runs_root / "ui_minipilot_notepad_gate.json",
        {
            "rows": 8,
            "metrics": {
                "wrong_action_rate": 0.0,
                "post_action_verify_rate": 1.0,
            },
            "sequence_metrics": {
                "task_pass_rate": 1.0,
            },
        },
    )
    _write_json(
        runs_root / "codex_next_step_report.json",
        {
            "status": "PASS",
            "blockers": [],
            "next_actions": ["a", "b"],
            "foundation_statuses": {
                "x": {"status": "PASS"},
                "y": {"status": "PASS"},
            },
        },
    )
    _write_json(
        runs_root / "rpa_control_latest.json",
        {
            "mode": "act",
            "decision": "answer",
            "confidence": 0.8,
            "risk": 0.2,
            "signals": {"reliability_signal_status": "PASS"},
        },
    )
    _write_json(
        runs_root / "drift_holdout_compare_latest.json",
        {
            "status": "PASS",
            "holdout": "stale_tab_state",
            "delta": 0.25,
            "improved": True,
            "baseline": {"drift_step_rate": 0.30},
            "fix": {"drift_step_rate": 0.05},
        },
    )


def test_build_capability_snapshot_passes_with_required_nontrap_artifacts(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    _write_minimal_nontrap_artifacts(runs_root)

    # Pointer values can contain escaped backslashes in this repo; ensure we normalize.
    case_dir = runs_root / "case_pack_20260218_010000"
    _write_json(
        case_dir / "case_pack_summary.json",
        {
            "status": "PASS",
            "steps": [
                {"name": "a", "status": "PASS", "required": True},
                {"name": "b", "status": "PASS", "required": True},
            ],
        },
    )
    (runs_root / "case_pack_latest.txt").write_text("runs\\\\case_pack_20260218_010000\n", encoding="utf-8")

    trust_dir = runs_root / "trust_demo_20260218_010000"
    _write_json(
        trust_dir / "trust_demo_summary.json",
        {
            "status": "PASS",
            "steps": [
                {"name": "rag_benchmark_lenient", "status": "PASS", "required": True},
                {"name": "rag_benchmark_strict", "status": "PASS", "required": False},
            ],
        },
    )
    (runs_root / "trust_demo_latest.txt").write_text("runs\\\\trust_demo_20260218_010000\n", encoding="utf-8")

    out_path = runs_root / "capability_snapshot_latest.json"
    archive_dir = runs_root / "capability_snapshots"
    result = _run_snapshot_script(
        [
            "--runs-root",
            str(runs_root),
            "--out",
            str(out_path),
            "--archive-dir",
            str(archive_dir),
        ]
    )
    assert result.returncode == 0, result.stderr
    payload = _read_json(out_path)
    assert payload["status"] == "PASS"
    assert payload["metrics"]["utility.status"] == "PASS"
    assert payload["metrics"]["ui_notepad.sequence.task_pass_rate"] == 1.0
    assert payload["metrics"]["codex_next_step.blocker_count"] == 0.0
    assert payload["metrics"]["rpa_control.decision_not_defer"] is True
    assert payload["metrics"]["case_pack.status"] == "PASS"
    assert payload["metrics"]["trust_demo.status"] == "PASS"
    assert payload["metrics"]["drift_baseline.status"] == "PASS"
    assert payload["metrics"]["drift_baseline.improved"] is True
    archived = list(archive_dir.glob("capability_snapshot_*.json"))
    assert len(archived) == 1


def test_build_capability_snapshot_fails_when_required_artifact_missing(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    # Missing utility artifact should hard-fail snapshot status.
    _write_json(
        runs_root / "ui_minipilot_notepad_gate.json",
        {
            "rows": 8,
            "metrics": {"wrong_action_rate": 0.0, "post_action_verify_rate": 1.0},
            "sequence_metrics": {"task_pass_rate": 1.0},
        },
    )

    out_path = runs_root / "capability_snapshot_latest.json"
    archive_dir = runs_root / "capability_snapshots"
    result = _run_snapshot_script(
        [
            "--runs-root",
            str(runs_root),
            "--out",
            str(out_path),
            "--archive-dir",
            str(archive_dir),
        ]
    )
    assert result.returncode == 1
    payload = _read_json(out_path)
    assert payload["status"] == "FAIL"
    assert "missing_real_world_utility_eval" in payload["failure_reasons"]
