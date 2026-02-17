from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from goldevidencebench.model_runner import load_adapter
from goldevidencebench.rpa_runtime_policy import evaluate_runtime_policy
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


def _read_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid JSON object: {path}")
    return raw


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _reversibility_for_row(row: dict[str, Any]) -> str:
    meta = row.get("meta")
    if isinstance(meta, dict):
        value = meta.get("reversibility")
        if isinstance(value, str) and value.strip().lower() in {"reversible", "irreversible"}:
            return value.strip().lower()
    raw = row.get("reversibility")
    if isinstance(raw, str) and raw.strip().lower() in {"reversible", "irreversible"}:
        return raw.strip().lower()
    return "reversible"


def _policy_context_for_row(
    *,
    row: dict[str, Any],
    snapshot: dict[str, Any],
    horizon_depth: int,
    weak_continuity_planning_support: bool,
) -> dict[str, Any]:
    signals = snapshot.get("signals")
    if not isinstance(signals, dict):
        signals = {}
    derived_scores = signals.get("derived_scores")
    if not isinstance(derived_scores, dict):
        derived_scores = {}
    authority_means = signals.get("authority_means")
    if not isinstance(authority_means, dict):
        authority_means = {}
    implication_means = signals.get("implication_means")
    if not isinstance(implication_means, dict):
        implication_means = {}
    agency_means = signals.get("agency_means")
    if not isinstance(agency_means, dict):
        agency_means = {}

    authority_violation = _float_or_none(authority_means.get("authority_violation_rate"))
    contradiction_repair = _float_or_none(implication_means.get("contradiction_repair_rate"))
    context: dict[str, Any] = {
        "reversibility": _reversibility_for_row(row),
        "planning_score": _float_or_none(derived_scores.get("planning_score")),
        "horizon_depth": horizon_depth,
        "needed_info": snapshot.get("needed_info") if isinstance(snapshot.get("needed_info"), list) else [],
        "authority_conflict_high": (
            authority_violation is not None and authority_violation > 0.0
        ),
        "weak_continuity_planning_support": weak_continuity_planning_support,
        "contradiction_repair_pending": (
            contradiction_repair is not None and contradiction_repair < 0.999
        ),
        "ic_score": _float_or_none(implication_means.get("ic_score")),
        "implication_break_rate": _float_or_none(implication_means.get("implication_break_rate")),
        "contradiction_repair_rate": contradiction_repair,
        "intent_preservation_score": _float_or_none(agency_means.get("intent_preservation_score")),
        "substitution": {
            "requested_option": "",
            "proposed_option": "",
            "disclosed": True,
            "authorized": True,
            "recoverable": _reversibility_for_row(row) == "reversible",
        },
    }
    return context


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
    parser.add_argument(
        "--use-rpa-controller",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Apply runtime RPA policy gating to each selected step.",
    )
    parser.add_argument(
        "--control-snapshot",
        default="runs/rpa_control_latest.json",
        help="Path to runtime control snapshot JSON used by policy gating.",
    )
    parser.add_argument(
        "--policy-strict",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="When enabled, non-answer policy decisions are treated as blocked.",
    )
    args = parser.parse_args()

    if args.planner == "llm" and args.model:
        os.environ["GOLDEVIDENCEBENCH_MODEL"] = args.model

    fixture_path = Path(args.fixture)
    if not fixture_path.exists():
        raise FileNotFoundError(f"Fixture not found: {fixture_path}")

    control_snapshot: dict[str, Any] | None = None
    if args.use_rpa_controller:
        snapshot_path = Path(args.control_snapshot)
        if not snapshot_path.exists():
            raise FileNotFoundError(
                f"RPA control snapshot not found: {snapshot_path}"
            )
        control_snapshot = _read_json(snapshot_path)

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

    for step_index, (row, selected_id) in enumerate(zip(rows, plan, strict=True), start=1):
        policy_mode: str | None = None
        policy_decision: str | None = None
        policy_block_reason: str | None = None
        policy_blocked = False

        if control_snapshot is not None:
            policy_context = _policy_context_for_row(
                row=row,
                snapshot=control_snapshot,
                horizon_depth=step_index,
                weak_continuity_planning_support=len(row.get("candidates", []) or []) > 1,
            )
            policy = evaluate_runtime_policy(control_snapshot, policy_context)
            policy_mode = policy.mode
            policy_decision = policy.decision
            policy_blocked = bool(policy.blocked) or (
                bool(args.policy_strict) and policy.decision != "answer"
            )
            if policy_blocked:
                selected_id = None
                if policy.reasons:
                    policy_block_reason = policy.reasons[0].code
                elif policy.decision != "answer":
                    policy_block_reason = "BLOCKED_BY_RUNTIME_POLICY"

        selected = _candidate_by_id(row, selected_id)
        steps.append(
            {
                "row_id": row.get("id"),
                "step_index": row.get("step_index"),
                "instruction": row.get("instruction"),
                "selected_id": selected_id,
                "action_type": selected.get("action_type") if selected else None,
                "label": selected.get("label") if selected else None,
                "policy_mode": policy_mode,
                "policy_decision": policy_decision,
                "policy_block_reason": policy_block_reason,
                "policy_blocked": policy_blocked,
            }
        )

    payload = {
        "fixture": str(fixture_path),
        "task_id": args.task_id,
        "planner": args.planner,
        "policy": {
            "enabled": bool(args.use_rpa_controller),
            "strict": bool(args.policy_strict),
            "control_snapshot": str(args.control_snapshot) if args.use_rpa_controller else None,
        },
        "steps": steps,
    }
    out_path = Path(args.out)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
