from __future__ import annotations

import random
import math
from typing import Any, Callable

from goldevidencebench.ui_policy import preselect_candidates


def state_matches(requirements: dict[str, Any], state: dict[str, Any]) -> bool:
    for key, value in requirements.items():
        if state.get(key) != value:
            return False
    return True


def compute_potential(state: dict[str, Any]) -> int:
    score = 0

    overlay_present = state.get("overlay_present")
    if isinstance(overlay_present, bool):
        score += 1 if not overlay_present else -1

    modal_scope = state.get("modal_scope")
    if isinstance(modal_scope, str) and modal_scope.strip():
        score += 1 if modal_scope.strip().lower() == "main" else -1

    tab = state.get("tab")
    instruction_tab = state.get("instruction_tab")
    if isinstance(tab, str) and isinstance(instruction_tab, str):
        score += 1 if tab.strip().lower() == instruction_tab.strip().lower() else -1

    return score


def delta_phi(current_state: dict[str, Any], next_state: dict[str, Any]) -> int:
    return compute_potential(next_state) - compute_potential(current_state)


def _candidate_state(candidate: dict[str, Any]) -> dict[str, Any]:
    state = None
    if isinstance(candidate.get("state"), dict):
        state = candidate["state"]
    elif isinstance(candidate.get("next_state"), dict):
        state = candidate["next_state"]
    if state is None:
        state = candidate
    if "overlay_present" not in state and "overlay" in state:
        state = dict(state)
        state["overlay_present"] = bool(state.get("overlay"))
    return state


def _split_step(step: Any) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    if isinstance(step, dict) and "candidates" in step:
        candidates = step.get("candidates")
        if not isinstance(candidates, list):
            raise ValueError("step candidates must be a list")
        return step, candidates
    if isinstance(step, dict) and "row" in step and "candidates" in step:
        row = step.get("row")
        if row is not None and not isinstance(row, dict):
            raise ValueError("step row must be a dict when present")
        candidates = step.get("candidates")
        if not isinstance(candidates, list):
            raise ValueError("step candidates must be a list")
        return row, candidates
    if isinstance(step, list):
        return None, step
    raise ValueError("each step must be a row dict, a {row,candidates} dict, or a list of candidates")


def construct_greedy_plan(
    candidates_by_step: list[Any],
    *,
    seed: int = 0,
    apply_overlay_filter: bool = True,
    apply_rules: bool = True,
) -> list[str | None]:
    rng = random.Random(seed)
    current_state: dict[str, Any] = {}
    plan: list[str | None] = []

    for step in candidates_by_step:
        row, candidates = _split_step(step)
        row_for_select = row if isinstance(row, dict) else {}
        candidates = preselect_candidates(
            row_for_select,
            candidates,
            apply_overlay_filter=apply_overlay_filter,
            apply_rules=apply_rules,
        )
        if not candidates:
            plan.append(None)
            continue

        scored: list[tuple[dict[str, Any], int]] = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            next_state = _candidate_state(candidate)
            score = delta_phi(current_state, next_state)
            scored.append((candidate, score))

        if not scored:
            plan.append(None)
            continue

        best_score = max(score for _, score in scored)
        best_candidates = [candidate for candidate, score in scored if score == best_score]
        chosen = rng.choice(best_candidates)
        candidate_id = chosen.get("candidate_id")
        plan.append(candidate_id if isinstance(candidate_id, str) else None)
        current_state = _candidate_state(chosen)

    return plan


def swap_plan_steps(plan: list[str | None], left: int, right: int) -> list[str | None]:
    if left < 0 or right < 0 or left >= len(plan) or right >= len(plan):
        raise ValueError("swap indices out of range")
    if left == right:
        return list(plan)
    out = list(plan)
    out[left], out[right] = out[right], out[left]
    return out


def replace_plan_step(plan: list[str | None], index: int, candidate_id: str | None) -> list[str | None]:
    if index < 0 or index >= len(plan):
        raise ValueError("replace index out of range")
    out = list(plan)
    out[index] = candidate_id
    return out


def rebuild_suffix(
    plan: list[str | None],
    candidates_by_step: list[Any],
    start_index: int,
    *,
    seed: int = 0,
    apply_overlay_filter: bool = True,
    apply_rules: bool = True,
) -> list[str | None]:
    if start_index < 0 or start_index > len(plan):
        raise ValueError("start_index out of range")
    suffix = construct_greedy_plan(
        candidates_by_step[start_index:],
        seed=seed,
        apply_overlay_filter=apply_overlay_filter,
        apply_rules=apply_rules,
    )
    return list(plan[:start_index]) + suffix


def _selectable_candidates(
    step: Any,
    *,
    apply_overlay_filter: bool,
    apply_rules: bool,
) -> list[dict[str, Any]]:
    row, candidates = _split_step(step)
    row_for_select = row if isinstance(row, dict) else {}
    return preselect_candidates(
        row_for_select,
        candidates,
        apply_overlay_filter=apply_overlay_filter,
        apply_rules=apply_rules,
    )


def _candidate_ids(step: Any, *, apply_overlay_filter: bool, apply_rules: bool) -> list[str | None]:
    candidates = _selectable_candidates(
        step,
        apply_overlay_filter=apply_overlay_filter,
        apply_rules=apply_rules,
    )
    ids: list[str | None] = []
    for candidate in candidates:
        candidate_id = candidate.get("candidate_id")
        ids.append(candidate_id if isinstance(candidate_id, str) else None)
    return ids


def _temperature_at(iteration: int, total: int, start: float, end: float) -> float:
    if total <= 1:
        return end
    if start <= 0 or end <= 0:
        return 0.0
    ratio = iteration / (total - 1)
    return start * ((end / start) ** ratio)


def search_with_simulated_annealing(
    initial_plan: list[str | None],
    candidates_by_step: list[Any],
    compute_score: callable,
    *,
    is_valid_plan: Callable[[list[str | None]], bool] | None = None,
    iterations: int = 200,
    temp_start: float = 1.0,
    temp_end: float = 0.01,
    seed: int = 0,
    apply_overlay_filter: bool = True,
    apply_rules: bool = True,
    return_telemetry: bool = False,
) -> tuple[list[str | None], float] | tuple[list[str | None], float, dict[str, float | int]]:
    """
    Refine a plan with simulated annealing.

    compute_score(plan) should combine hard penalties (wrong actions) plus a small shaping term
    (e.g., alpha * delta_phi) for policy-invariant potential shaping.
    """
    if len(initial_plan) != len(candidates_by_step):
        raise ValueError("initial_plan length must match candidates_by_step length")
    if iterations <= 0:
        score = float(compute_score(initial_plan))
        telemetry = {
            "iterations": 0,
            "proposed_moves": 0,
            "accepted_moves": 0,
            "invalid_moves": 0,
            "accept_rate": 0.0,
            "start_score": score,
            "best_score": score,
            "best_iteration": 0,
            "end_score": score,
        }
        if return_telemetry:
            return list(initial_plan), score, telemetry
        return list(initial_plan), score

    rng = random.Random(seed)
    current_plan = list(initial_plan)
    current_valid = True if is_valid_plan is None else bool(is_valid_plan(current_plan))
    current_score = float(compute_score(current_plan)) if current_valid else -math.inf
    start_score = current_score
    best_plan = list(current_plan)
    best_score = current_score
    best_iteration = 0
    proposed_moves = 0
    accepted_moves = 0
    invalid_moves = 0
    move_stats = {
        "swap": {"proposed": 0, "accepted": 0, "invalid": 0},
        "replace": {"proposed": 0, "accepted": 0, "invalid": 0},
        "rebuild": {"proposed": 0, "accepted": 0, "invalid": 0},
    }
    move_ops = ("replace", "rebuild")

    for iteration in range(iterations):
        proposed_moves += 1
        if len(current_plan) <= 1:
            op = "replace"
        else:
            op = rng.choice(move_ops)
        move_stats[op]["proposed"] += 1
        if op == "swap" and len(current_plan) >= 2:
            left, right = rng.sample(range(len(current_plan)), 2)
            neighbor = swap_plan_steps(current_plan, left, right)
        elif op == "replace":
            index = rng.randrange(len(current_plan))
            ids = _candidate_ids(
                candidates_by_step[index],
                apply_overlay_filter=apply_overlay_filter,
                apply_rules=apply_rules,
            )
            if ids:
                current_id = current_plan[index]
                alt_ids = [candidate_id for candidate_id in ids if candidate_id != current_id]
                chosen_id = rng.choice(alt_ids) if alt_ids else rng.choice(ids)
            else:
                chosen_id = None
            neighbor = replace_plan_step(current_plan, index, chosen_id)
        else:
            start_index = rng.randrange(len(current_plan))
            neighbor = rebuild_suffix(
                current_plan,
                candidates_by_step,
                start_index,
                seed=rng.randrange(0, 1_000_000),
                apply_overlay_filter=apply_overlay_filter,
                apply_rules=apply_rules,
            )

        if is_valid_plan is not None and not is_valid_plan(neighbor):
            invalid_moves += 1
            move_stats[op]["invalid"] += 1
            continue

        neighbor_score = float(compute_score(neighbor))
        temperature = _temperature_at(iteration, iterations, temp_start, temp_end)
        delta = neighbor_score - current_score
        accept = False
        if delta >= 0:
            accept = True
        elif temperature > 0:
            accept = rng.random() < math.exp(delta / temperature)

        if accept:
            current_plan = neighbor
            current_score = neighbor_score
            accepted_moves += 1
            move_stats[op]["accepted"] += 1
            if neighbor_score > best_score:
                best_score = neighbor_score
                best_plan = list(neighbor)
                best_iteration = iteration

    accept_rate = accepted_moves / proposed_moves if proposed_moves else 0.0
    for stats in move_stats.values():
        proposed = stats["proposed"]
        accepted = stats["accepted"]
        stats["accept_rate"] = accepted / proposed if proposed else 0.0

    telemetry = {
        "iterations": iterations,
        "proposed_moves": proposed_moves,
        "accepted_moves": accepted_moves,
        "invalid_moves": invalid_moves,
        "accept_rate": accept_rate,
        "start_score": start_score,
        "best_score": best_score,
        "best_iteration": best_iteration,
        "end_score": current_score,
        "move_stats": move_stats,
    }
    if return_telemetry:
        return best_plan, best_score, telemetry
    return best_plan, best_score


def score_plan_against_gold(
    candidates_by_step: list[Any],
    plan: list[str | None],
    *,
    alpha: float = 0.1,
    wrong_action_penalty: float = 1_000.0,
    abstain_penalty: float = 1.0,
    fatal_wrong: bool = True,
    require_state_gate: bool = False,
    apply_overlay_filter: bool = True,
    apply_rules: bool = True,
) -> tuple[float, bool]:
    if len(plan) != len(candidates_by_step):
        raise ValueError("plan length must match candidates_by_step length")

    current_state: dict[str, Any] = {}
    score = 0.0
    wrong_action = False

    for step, selected_id in zip(candidates_by_step, plan, strict=True):
        row, candidates = _split_step(step)
        row_for_select = row if isinstance(row, dict) else {}
        candidates = preselect_candidates(
            row_for_select,
            candidates,
            apply_overlay_filter=apply_overlay_filter,
            apply_rules=apply_rules,
        )
        candidate_by_id = {
            candidate.get("candidate_id"): candidate
            for candidate in candidates
            if isinstance(candidate, dict) and isinstance(candidate.get("candidate_id"), str)
        }

        gold_id = None
        if isinstance(row, dict):
            gold = row.get("gold")
            if isinstance(gold, dict):
                gold_id = gold.get("candidate_id")

        requires_state = row.get("requires_state") if isinstance(row, dict) else None
        if require_state_gate and isinstance(requires_state, dict):
            if not state_matches(requires_state, current_state):
                wrong_action = True
                if fatal_wrong:
                    return -1e9, True
                score -= wrong_action_penalty

        if selected_id is None:
            score -= abstain_penalty
            continue

        if gold_id is not None and selected_id != gold_id:
            wrong_action = True
            if fatal_wrong:
                return -1e9, True
            score -= wrong_action_penalty

        selected = candidate_by_id.get(selected_id)
        if selected is None:
            score -= abstain_penalty
            continue

        score += alpha * delta_phi(current_state, _candidate_state(selected))
        current_state = _candidate_state(selected)

    return score, wrong_action
