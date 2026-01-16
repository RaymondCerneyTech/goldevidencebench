from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from goldevidencebench.model_runner import load_adapter
from goldevidencebench.ui_policy import preselect_candidates
from goldevidencebench.ui_search import delta_phi, state_matches
from goldevidencebench.util import read_jsonl


def _candidate_by_id(row: dict[str, Any], candidate_id: str | None) -> dict[str, Any] | None:
    if candidate_id is None:
        return None
    candidates = row.get("candidates", [])
    if not isinstance(candidates, list):
        return None
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if candidate.get("candidate_id") == candidate_id:
            return candidate
    return None


def _load_rows(path: Path, task_id: str) -> list[dict[str, Any]]:
    rows = [row for row in read_jsonl(path) if isinstance(row, dict)]
    filtered = [row for row in rows if row.get("task_id") == task_id]
    if not filtered:
        raise ValueError(f"No rows found for task_id={task_id}")
    filtered.sort(key=lambda row: int(row.get("step_index", 0)))
    return filtered


def _candidate_state(candidate: dict[str, Any]) -> dict[str, Any]:
    if isinstance(candidate.get("state"), dict):
        state = dict(candidate["state"])
    elif isinstance(candidate.get("next_state"), dict):
        state = dict(candidate["next_state"])
    else:
        state = dict(candidate)
    if "overlay_present" not in state and "overlay" in state:
        state["overlay_present"] = bool(state.get("overlay"))
    return state


def _candidate_state_from_row(row: dict[str, Any], candidate_id: str | None) -> dict[str, Any]:
    if candidate_id is None:
        return {}
    candidates = row.get("candidates", [])
    if not isinstance(candidates, list):
        return {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if candidate.get("candidate_id") == candidate_id:
            return _candidate_state(candidate)
    return {}


def _state_constrained_candidates(
    row: dict[str, Any],
    candidates: list[dict[str, Any]],
    current_state: dict[str, Any],
    *,
    apply_overlay_filter: bool,
    apply_rules: bool,
) -> list[dict[str, Any]]:
    filtered = preselect_candidates(
        row,
        candidates,
        apply_overlay_filter=apply_overlay_filter,
        apply_rules=apply_rules,
    )
    requires_state = row.get("requires_state")
    if not isinstance(requires_state, dict):
        return filtered
    if state_matches(requires_state, current_state):
        return filtered
    advance = [
        candidate
        for candidate in filtered
        if isinstance(candidate, dict)
        and (isinstance(candidate.get("next_state"), dict) or isinstance(candidate.get("state"), dict))
    ]
    return advance


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Select a UI action plan using the UI adapter."
    )
    parser.add_argument(
        "--fixture",
        required=True,
        help="Path to a UI fixture JSONL file.",
    )
    parser.add_argument(
        "--task-id",
        required=True,
        help="task_id to select rows for.",
    )
    parser.add_argument(
        "--adapter",
        default="goldevidencebench.adapters.ui_llama_cpp_adapter:create_adapter",
        help="UI adapter factory path.",
    )
    parser.add_argument(
        "--planner",
        choices=("llm", "policy", "greedy"),
        default="llm",
        help="Planner to use: llm (adapter), policy (deterministic), or greedy.",
    )
    parser.add_argument(
        "--model",
        default="",
        help="Optional model path (sets GOLDEVIDENCEBENCH_MODEL).",
    )
    parser.add_argument(
        "--overlay-filter",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Apply overlay filtering in deterministic planners.",
    )
    parser.add_argument(
        "--rules",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Apply deterministic preselect rules in deterministic planners.",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Output JSON path for the selected plan.",
    )
    args = parser.parse_args()

    if args.planner == "llm" and args.model:
        os.environ["GOLDEVIDENCEBENCH_MODEL"] = args.model

    fixture_path = Path(args.fixture)
    if not fixture_path.exists():
        raise FileNotFoundError(f"Fixture not found: {fixture_path}")

    rows = _load_rows(fixture_path, args.task_id)
    steps: list[dict[str, Any]] = []

    if args.planner == "llm":
        adapter = load_adapter(args.adapter)
        plan: list[str | None] = []
        for row in rows:
            pred = adapter.predict(row, protocol="ui")
            value = pred.get("value")
            selected_id = value if isinstance(value, str) and value.strip() else None
            plan.append(selected_id)
    else:
        plan = []
        current_state: dict[str, Any] = {}
        for row in rows:
            requires_state = row.get("requires_state")
            if args.planner == "policy":
                if isinstance(requires_state, dict) and not state_matches(
                    requires_state, current_state
                ):
                    plan.append(None)
                    continue
                candidates = row.get("candidates", [])
                if not isinstance(candidates, list):
                    plan.append(None)
                    continue
                filtered = preselect_candidates(
                    row,
                    candidates,
                    apply_overlay_filter=args.overlay_filter,
                    apply_rules=args.rules,
                )
                candidate_ids = [
                    candidate.get("candidate_id")
                    for candidate in filtered
                    if isinstance(candidate, dict) and isinstance(candidate.get("candidate_id"), str)
                ]
                selected_id = candidate_ids[0] if len(candidate_ids) == 1 else None
                plan.append(selected_id)
            else:
                candidates = row.get("candidates", [])
                if not isinstance(candidates, list):
                    plan.append(None)
                    continue
                filtered = _state_constrained_candidates(
                    row,
                    candidates,
                    current_state,
                    apply_overlay_filter=args.overlay_filter,
                    apply_rules=args.rules,
                )
                if not filtered:
                    plan.append(None)
                    continue
                scored: list[tuple[dict[str, Any], int]] = []
                for candidate in filtered:
                    if not isinstance(candidate, dict):
                        continue
                    next_state = _candidate_state(candidate)
                    score = delta_phi(current_state, next_state)
                    scored.append((candidate, score))
                if not scored:
                    plan.append(None)
                    continue
                best_score = max(score for _, score in scored)
                for candidate, score in scored:
                    if score == best_score:
                        selected_id = candidate.get("candidate_id")
                        plan.append(
                            selected_id if isinstance(selected_id, str) else None
                        )
                        current_state = _candidate_state(candidate)
                        break
                continue

            next_state = _candidate_state_from_row(row, plan[-1])
            if next_state:
                current_state = next_state

    for row, selected_id in zip(rows, plan, strict=True):
        selected = _candidate_by_id(row, selected_id)
        steps.append(
            {
                "row_id": row.get("id"),
                "step_index": row.get("step_index"),
                "instruction": row.get("instruction"),
                "selected_id": selected_id,
                "action_type": selected.get("action_type") if selected else None,
                "label": selected.get("label") if selected else None,
            }
        )

    payload = {
        "fixture": str(fixture_path),
        "task_id": args.task_id,
        "planner": args.planner,
        "steps": steps,
    }
    out_path = Path(args.out)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
