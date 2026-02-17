from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _run_select_ui_plan(
    *,
    fixture: Path,
    snapshot: Path,
    out: Path,
) -> subprocess.CompletedProcess[str]:
    script = Path(__file__).resolve().parents[1] / "scripts" / "select_ui_plan.py"
    return subprocess.run(
        [
            sys.executable,
            str(script),
            "--fixture",
            str(fixture),
            "--task-id",
            "task_1",
            "--planner",
            "policy",
            "--out",
            str(out),
            "--use-rpa-controller",
            "--control-snapshot",
            str(snapshot),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def _fixture_row() -> dict:
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


def test_select_ui_plan_policy_enforcement_allow_path(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.jsonl"
    _write_jsonl(fixture, [_fixture_row()])
    snapshot = tmp_path / "snapshot.json"
    _write_json(
        snapshot,
        {
            "confidence": 0.98,
            "risk": 0.05,
            "horizon_depth": 1,
            "needed_info": [],
            "reversibility": "reversible",
            "signals": {
                "derived_scores": {"planning_score": 0.95},
                "authority_means": {"authority_violation_rate": 0.0},
                "implication_means": {
                    "ic_score": 0.99,
                    "implication_break_rate": 0.0,
                    "contradiction_repair_rate": 1.0,
                },
                "agency_means": {"intent_preservation_score": 1.0},
            },
        },
    )
    out = tmp_path / "plan.json"

    result = _run_select_ui_plan(fixture=fixture, snapshot=snapshot, out=out)
    assert result.returncode == 0, result.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["policy"]["enabled"] is True
    step = payload["steps"][0]
    assert step["selected_id"] == "cand_continue"
    assert step["policy_mode"] == "act"
    assert step["policy_decision"] == "answer"
    assert step["policy_block_reason"] is None


def test_select_ui_plan_policy_enforcement_block_path(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.jsonl"
    _write_jsonl(fixture, [_fixture_row()])
    snapshot = tmp_path / "snapshot.json"
    _write_json(
        snapshot,
        {
            "confidence": 0.40,
            "risk": 0.10,
            "horizon_depth": 1,
            "needed_info": ["missing_dependency_specification"],
            "reversibility": "reversible",
            "signals": {
                "derived_scores": {"planning_score": 0.95},
                "authority_means": {"authority_violation_rate": 0.0},
                "implication_means": {
                    "ic_score": 0.99,
                    "implication_break_rate": 0.0,
                    "contradiction_repair_rate": 1.0,
                },
                "agency_means": {"intent_preservation_score": 1.0},
            },
        },
    )
    out = tmp_path / "plan.json"

    result = _run_select_ui_plan(fixture=fixture, snapshot=snapshot, out=out)
    assert result.returncode == 0, result.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    step = payload["steps"][0]
    assert step["selected_id"] is None
    assert step["policy_mode"] == "reason"
    assert step["policy_decision"] in {"ask", "retrieve", "abstain"}
    assert step["policy_block_reason"] in {
        "LOW_CONFIDENCE",
        "MISSING_NEEDED_INFO",
        "BLOCKED_BY_RUNTIME_POLICY",
    }
