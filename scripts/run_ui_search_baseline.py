from __future__ import annotations

import argparse
import csv
import json
import time
import random
from copy import deepcopy
from pathlib import Path
from typing import Any

from goldevidencebench.ui_eval import (
    score_post_action_verification,
    score_ui_rows,
    score_ui_sequences,
    task_step_stats,
)
from goldevidencebench.ui_fixture import validate_ui_fixture_path
from goldevidencebench.ui_gate import GateModel, select_candidate
from goldevidencebench.ui_policy import preselect_candidates, preselect_candidates_with_trace
from goldevidencebench.ui_prompt import extract_ui_instruction
from goldevidencebench.ui_search import (
    construct_greedy_plan,
    delta_phi,
    score_plan_against_gold,
    search_with_simulated_annealing,
    state_matches,
)
from goldevidencebench.util import read_jsonl

FUZZ_SYNONYMS = {
    "apply": ("confirm", "save"),
    "back": ("previous", "prev"),
    "begin": ("start", "open"),
    "cancel": ("close", "dismiss"),
    "close": ("cancel", "dismiss"),
    "confirm": ("ok", "okay", "yes", "apply", "save"),
    "continue": ("next", "proceed"),
    "done": ("finish", "complete"),
    "finish": ("done", "complete"),
    "next": ("continue", "proceed"),
    "ok": ("confirm", "okay", "yes"),
    "okay": ("confirm", "ok", "yes"),
    "open": ("start", "begin"),
    "previous": ("back", "prev"),
    "prev": ("back", "previous"),
    "proceed": ("continue", "next"),
    "save": ("apply", "confirm"),
    "start": ("begin", "open"),
    "yes": ("confirm", "ok", "okay"),
}
FUZZ_PUNCTUATION = (".", "!", "?")


def _load_observed_deltas(path: Path, rows: list[dict[str, Any]]) -> list[dict[str, Any] | None]:
    observed_rows = list(read_jsonl(path))
    observed_by_id: dict[str, dict[str, Any] | None] = {}
    for row in observed_rows:
        if not isinstance(row, dict):
            continue
        row_id = row.get("id")
        observed = row.get("observed_delta")
        if isinstance(row_id, str):
            observed_by_id[row_id] = observed if isinstance(observed, dict) else None
    observed_deltas: list[dict[str, Any] | None] = []
    for row in rows:
        row_id = row.get("id")
        observed_deltas.append(observed_by_id.get(row_id))
    return observed_deltas


def _load_gate_model(path: Path | None) -> GateModel | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return GateModel(
        feature_names=payload["feature_names"],
        weights=payload["weights"],
        bias=payload.get("bias", 0.0),
        min_score=payload.get("min_score", 0.5),
        min_margin=payload.get("min_margin", 0.0),
    )


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


def _candidate_snapshot(candidate: dict[str, Any] | None) -> dict[str, Any] | None:
    if candidate is None:
        return None
    snapshot: dict[str, Any] = {}
    keys = (
        "candidate_id",
        "label",
        "role",
        "app_path",
        "modal_scope",
        "overlay_present",
        "overlay",
        "enabled",
        "visible",
        "clickable",
        "bbox",
        "z_index",
        "state",
        "next_state",
    )
    for key in keys:
        if key in candidate:
            snapshot[key] = candidate.get(key)
    if "overlay_present" not in snapshot and "overlay" in candidate:
        snapshot["overlay_present"] = bool(candidate.get("overlay"))
    return snapshot


def _is_overlay_candidate(candidate: dict[str, Any] | None) -> bool:
    if candidate is None:
        return False
    if candidate.get("overlay_present") is True:
        return True
    if candidate.get("overlay") is True:
        return True
    modal_scope = candidate.get("modal_scope")
    if isinstance(modal_scope, str) and modal_scope.strip().lower() in {"popup", "overlay"}:
        return True
    return False


def _is_main_scope(candidate: dict[str, Any] | None) -> bool:
    if candidate is None:
        return False
    modal_scope = candidate.get("modal_scope")
    if modal_scope is None:
        return True
    if isinstance(modal_scope, str):
        return modal_scope.strip().lower() in {"", "main"}
    return False


def _candidate_feature_diff(
    greedy: dict[str, Any] | None,
    sa: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    greedy_snapshot = _candidate_snapshot(greedy) or {}
    sa_snapshot = _candidate_snapshot(sa) or {}
    keys = set(greedy_snapshot) | set(sa_snapshot)
    diff: dict[str, dict[str, Any]] = {}
    for key in keys:
        if greedy_snapshot.get(key) != sa_snapshot.get(key):
            diff[key] = {"greedy": greedy_snapshot.get(key), "sa": sa_snapshot.get(key)}
    return diff


def _decoy_reasons(greedy: dict[str, Any] | None, sa: dict[str, Any] | None) -> list[str]:
    reasons: list[str] = []
    if _is_main_scope(greedy) and not _is_main_scope(sa):
        reasons.append("prefer_main_scope")
    if not _is_overlay_candidate(greedy) and _is_overlay_candidate(sa):
        reasons.append("avoid_overlay")
    if greedy and greedy.get("enabled") is True and sa and sa.get("enabled") is False:
        reasons.append("prefer_enabled")
    if greedy and greedy.get("visible") is True and sa and sa.get("visible") is False:
        reasons.append("prefer_visible")
    if greedy and greedy.get("clickable") is True and sa and sa.get("clickable") is False:
        reasons.append("prefer_clickable")
    greedy_id = greedy.get("candidate_id") if isinstance(greedy, dict) else None
    sa_id = sa.get("candidate_id") if isinstance(sa, dict) else None
    if isinstance(greedy_id, str) and "primary" in greedy_id and isinstance(sa_id, str):
        if "primary" not in sa_id:
            reasons.append("prefer_primary_id")
    greedy_label = greedy.get("label") if isinstance(greedy, dict) else None
    sa_label = sa.get("label") if isinstance(sa, dict) else None
    if isinstance(greedy_label, str) and isinstance(sa_label, str) and greedy_label != sa_label:
        reasons.append("label_mismatch")
    return reasons


def _state_before_step(
    rows: list[dict[str, Any]], plan: list[str | None], index: int
) -> dict[str, Any]:
    current_state: dict[str, Any] = {}
    for row, selected_id in zip(rows[:index], plan[:index], strict=True):
        next_state = _candidate_state_from_row(row, selected_id)
        if next_state:
            current_state = next_state
    return current_state


def _sa_vs_greedy_diff(
    rows: list[dict[str, Any]],
    greedy_plan: list[str | None],
    sa_plan: list[str | None],
) -> dict[str, Any] | None:
    for index, (greedy_id, sa_id) in enumerate(zip(greedy_plan, sa_plan, strict=True)):
        if greedy_id == sa_id:
            continue
        row = rows[index]
        greedy_candidate = _candidate_by_id(row, greedy_id)
        sa_candidate = _candidate_by_id(row, sa_id)
        return {
            "step_index": index,
            "row_id": row.get("id"),
            "task_id": row.get("task_id"),
            "step_number": row.get("step_index"),
            "instruction": extract_ui_instruction(row),
            "requires_state": row.get("requires_state"),
            "state_before": _state_before_step(rows, greedy_plan, index),
            "greedy_choice": _candidate_snapshot(greedy_candidate),
            "sa_choice": _candidate_snapshot(sa_candidate),
            "feature_diff": _candidate_feature_diff(greedy_candidate, sa_candidate),
            "decoy_reasons": _decoy_reasons(greedy_candidate, sa_candidate),
        }
    return None


def _policy_only_plan(
    rows: list[dict[str, Any]],
    *,
    apply_overlay_filter: bool,
    apply_rules: bool,
) -> list[str | None]:
    selected_ids: list[str | None] = []
    current_state: dict[str, Any] = {}
    for row in rows:
        requires_state = row.get("requires_state")
        if isinstance(requires_state, dict) and not state_matches(requires_state, current_state):
            selected_ids.append(None)
            continue
        candidates = row.get("candidates", [])
        if not isinstance(candidates, list):
            selected_ids.append(None)
            continue
        filtered = preselect_candidates(
            row,
            candidates,
            apply_overlay_filter=apply_overlay_filter,
            apply_rules=apply_rules,
        )
        candidate_ids = [
            candidate.get("candidate_id")
            for candidate in filtered
            if isinstance(candidate, dict) and isinstance(candidate.get("candidate_id"), str)
        ]
        if len(candidate_ids) == 1:
            selected_ids.append(candidate_ids[0])
        else:
            selected_ids.append(None)
        next_state = _candidate_state_from_row(row, selected_ids[-1])
        if next_state:
            current_state = next_state
    return selected_ids


def _gate_plan(
    rows: list[dict[str, Any]],
    model: GateModel,
    *,
    apply_overlay_filter: bool,
    apply_rules: bool,
) -> list[str | None]:
    selected_ids: list[str | None] = []
    current_state: dict[str, Any] = {}
    for row in rows:
        candidates = _state_constrained_candidates(
            row,
            current_state,
            apply_overlay_filter=apply_overlay_filter,
            apply_rules=apply_rules,
        )
        candidate_id = select_candidate(row, candidates, model) if candidates else None
        selected_ids.append(candidate_id if isinstance(candidate_id, str) else None)
        next_state = _candidate_state_from_row(row, selected_ids[-1])
        if next_state:
            current_state = next_state
    return selected_ids


def _candidate_state_from_row(row: dict[str, Any], selected_id: str | None) -> dict[str, Any]:
    if selected_id is None:
        return {}
    candidates = row.get("candidates", [])
    if not isinstance(candidates, list):
        return {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if candidate.get("candidate_id") != selected_id:
            continue
        if isinstance(candidate.get("state"), dict):
            state = dict(candidate["state"])
        elif isinstance(candidate.get("next_state"), dict):
            state = dict(candidate["next_state"])
        else:
            return {}
        if "overlay_present" not in state and "overlay" in state:
            state["overlay_present"] = bool(state.get("overlay"))
        return state
    return {}


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


def _mutate_case(text: str, rng: random.Random) -> str:
    mode = rng.choice(("lower", "upper", "title"))
    if mode == "lower":
        return text.lower()
    if mode == "upper":
        return text.upper()
    return text.title()


def _mutate_whitespace(text: str, rng: random.Random) -> str:
    if " " not in text:
        return f"{text} "
    parts = text.split(" ")
    if len(parts) < 2:
        return text
    idx = rng.randrange(len(parts) - 1)
    parts[idx] = parts[idx] + " "
    return " ".join(parts)


def _mutate_punctuation(text: str, rng: random.Random) -> str:
    if text and text[-1] in FUZZ_PUNCTUATION:
        options = [mark for mark in FUZZ_PUNCTUATION if mark != text[-1]]
        return f"{text[:-1]}{rng.choice(options)}"
    return f"{text}{rng.choice(FUZZ_PUNCTUATION)}"


def _replace_with_synonym(text: str, rng: random.Random) -> str:
    tokens = text.split()
    if not tokens:
        return text
    indices = []
    for idx, token in enumerate(tokens):
        base = token.rstrip(".,!?")
        if base.lower() in FUZZ_SYNONYMS:
            indices.append(idx)
    if not indices:
        return text
    idx = rng.choice(indices)
    token = tokens[idx]
    base = token.rstrip(".,!?")
    suffix = token[len(base) :]
    synonyms = FUZZ_SYNONYMS.get(base.lower(), ())
    if not synonyms:
        return text
    replacement = rng.choice(synonyms)
    if base.isupper():
        replacement = replacement.upper()
    elif base[:1].isupper():
        replacement = replacement.capitalize()
    tokens[idx] = f"{replacement}{suffix}"
    return " ".join(tokens)


def _mutate_text(text: str, rng: random.Random) -> str:
    if not text:
        return text
    op = rng.choice(("synonym", "case", "punct", "whitespace"))
    if op == "synonym":
        mutated = _replace_with_synonym(text, rng)
        if mutated != text:
            return mutated
    if op == "case":
        return _mutate_case(text, rng)
    if op == "punct":
        return _mutate_punctuation(text, rng)
    if op == "whitespace":
        return _mutate_whitespace(text, rng)
    return text


def _apply_text_fuzz(rows: list[dict[str, Any]], rng: random.Random) -> list[dict[str, Any]]:
    mutated = deepcopy(rows)
    for row in mutated:
        instruction = row.get("instruction")
        if isinstance(instruction, str) and instruction.strip():
            row["instruction"] = _mutate_text(instruction, rng)
        candidates = row.get("candidates")
        if not isinstance(candidates, list):
            continue
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            label = candidate.get("label")
            if isinstance(label, str) and label.strip() and rng.random() < 0.35:
                candidate["label"] = _mutate_text(label, rng)
    return mutated


def _mean(values: list[float | None]) -> float | None:
    cleaned = [value for value in values if isinstance(value, (int, float))]
    if not cleaned:
        return None
    return sum(cleaned) / len(cleaned)


def _min(values: list[float | None]) -> float | None:
    cleaned = [value for value in values if isinstance(value, (int, float))]
    if not cleaned:
        return None
    return min(cleaned)


def _mean_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _as_seed_runs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    seed_runs = payload.get("seed_runs")
    if isinstance(seed_runs, list):
        return seed_runs
    strategies = ["policy", "greedy", "sa"]
    if "gate" in payload:
        strategies.append("gate")
    return [{name: payload.get(name, {}) for name in strategies}]


def _summarize_seed_runs(seed_runs: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    metric_template = {
        "selection_rate": [],
        "abstain_rate": [],
        "wrong_action_rate": [],
        "task_pass_rate": [],
        "task_step_overhead_mean": [],
        "task_steps_taken_mean": [],
        "task_min_steps_mean": [],
    }
    preferred = ["policy", "greedy", "sa", "gate"]
    discovered: set[str] = set()
    for run in seed_runs:
        if not isinstance(run, dict):
            continue
        for key, value in run.items():
            if isinstance(value, dict) and isinstance(value.get("metrics"), dict):
                discovered.add(key)
    strategies = [name for name in preferred if name in discovered]
    for name in sorted(discovered):
        if name not in strategies:
            strategies.append(name)
    metrics = {name: deepcopy(metric_template) for name in strategies}
    for run in seed_runs:
        for strategy in metrics:
            block = run.get(strategy, {})
            if not isinstance(block, dict):
                continue
            strategy_metrics = block.get("metrics", {})
            sequence_metrics = block.get("sequence_metrics", {})
            if isinstance(strategy_metrics, dict):
                for key in ("selection_rate", "abstain_rate", "wrong_action_rate"):
                    value = strategy_metrics.get(key)
                    if isinstance(value, (int, float)):
                        metrics[strategy][key].append(float(value))
            if isinstance(sequence_metrics, dict):
                task_pass_rate = sequence_metrics.get("task_pass_rate")
                if isinstance(task_pass_rate, (int, float)):
                    metrics[strategy]["task_pass_rate"].append(float(task_pass_rate))
                for key in (
                    "task_step_overhead_mean",
                    "task_steps_taken_mean",
                    "task_min_steps_mean",
                ):
                    value = sequence_metrics.get(key)
                    if isinstance(value, (int, float)):
                        metrics[strategy][key].append(float(value))
    summary: dict[str, dict[str, float]] = {}
    for strategy, values in metrics.items():
        summary[strategy] = {key: _mean_or_none(vals) for key, vals in values.items()}
    return summary


def _write_summary_csv(
    path: Path,
    *,
    fixture: str,
    seeds: int,
    strategy_summary: dict[str, dict[str, float]],
) -> None:
    fieldnames = [
        "fixture",
        "seeds",
        "strategy",
        "selection_rate_mean",
        "abstain_rate_mean",
        "wrong_action_rate_mean",
        "task_pass_rate_mean",
        "task_step_overhead_mean",
        "task_steps_taken_mean",
        "task_min_steps_mean",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for strategy, metrics in strategy_summary.items():
            writer.writerow(
                {
                    "fixture": fixture,
                    "seeds": seeds,
                    "strategy": strategy,
                    "selection_rate_mean": metrics.get("selection_rate", 0.0),
                    "abstain_rate_mean": metrics.get("abstain_rate", 0.0),
                    "wrong_action_rate_mean": metrics.get("wrong_action_rate", 0.0),
                    "task_pass_rate_mean": metrics.get("task_pass_rate", 0.0),
                    "task_step_overhead_mean": metrics.get("task_step_overhead_mean", ""),
                    "task_steps_taken_mean": metrics.get("task_steps_taken_mean", ""),
                    "task_min_steps_mean": metrics.get("task_min_steps_mean", ""),
                }
            )


def _stats_by_task(
    rows: list[dict[str, Any]],
    selected_ids: list[str | None],
    observed: list[dict[str, Any] | None] | None,
) -> dict[str, dict[str, Any]]:
    stats = task_step_stats(rows, selected_ids, observed)
    return {stat["task_id"]: stat for stat in stats}


def _shorter_valid_prefs(
    fixture: str,
    seed: int,
    stats_by_strategy: dict[str, dict[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    pairs = [("policy", "greedy"), ("policy", "sa"), ("greedy", "sa")]
    task_ids = set()
    for stats in stats_by_strategy.values():
        task_ids.update(stats.keys())
    preferences: list[dict[str, Any]] = []
    for task_id in sorted(task_ids):
        for left, right in pairs:
            left_stat = stats_by_strategy.get(left, {}).get(task_id)
            right_stat = stats_by_strategy.get(right, {}).get(task_id)
            if not left_stat or not right_stat:
                continue
            if not (left_stat["pass"] and right_stat["pass"]):
                continue
            left_steps = left_stat["steps_taken"]
            right_steps = right_stat["steps_taken"]
            if left_steps == right_steps:
                continue
            if left_steps < right_steps:
                preferred, rejected = left, right
                preferred_stat, rejected_stat = left_stat, right_stat
            else:
                preferred, rejected = right, left
                preferred_stat, rejected_stat = right_stat, left_stat
            preferences.append(
                {
                    "fixture": fixture,
                    "task_id": task_id,
                    "seed": seed,
                    "preferred_strategy": preferred,
                    "rejected_strategy": rejected,
                    "preferred_steps": preferred_stat["steps_taken"],
                    "rejected_steps": rejected_stat["steps_taken"],
                    "min_steps": preferred_stat["min_steps"],
                    "preferred_overhead": preferred_stat["step_overhead"],
                    "rejected_overhead": rejected_stat["step_overhead"],
                }
            )
    return preferences


def _state_constrained_candidates(
    step: Any,
    current_state: dict[str, Any],
    *,
    apply_overlay_filter: bool,
    apply_rules: bool,
) -> list[dict[str, Any]]:
    row, candidates = _split_step(step)
    row_for_select = row if isinstance(row, dict) else {}
    filtered = preselect_candidates(
        row_for_select,
        candidates,
        apply_overlay_filter=apply_overlay_filter,
        apply_rules=apply_rules,
    )
    requires_state = row_for_select.get("requires_state")
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


def _state_gate_metrics(
    rows: list[dict[str, Any]], selected_ids: list[str | None]
) -> dict[str, float]:
    if len(rows) != len(selected_ids):
        raise ValueError("rows and selected_ids must be the same length")
    total = 0
    violations = 0
    current_state: dict[str, Any] = {}
    for row, selected_id in zip(rows, selected_ids, strict=True):
        requires_state = row.get("requires_state")
        if isinstance(requires_state, dict):
            total += 1
            if selected_id is not None and not state_matches(requires_state, current_state):
                violations += 1
        next_state = _candidate_state_from_row(row, selected_id)
        if next_state:
            current_state = next_state
    if total == 0:
        return {"state_gate_pass_rate": 1.0, "state_gate_violation_rate": 0.0}
    return {
        "state_gate_pass_rate": (total - violations) / total,
        "state_gate_violation_rate": violations / total,
    }


def _score_strategy(
    rows: list[dict[str, Any]],
    selected_ids: list[str | None],
    observed_deltas: list[dict[str, Any] | None] | None,
    *,
    apply_overlay_filter: bool,
    apply_rules: bool,
) -> dict[str, Any]:
    metrics = score_ui_rows(rows, selected_ids)
    if observed_deltas is not None:
        metrics.update(score_post_action_verification(rows, observed_deltas))
    sequence_metrics = score_ui_sequences(rows, selected_ids, observed_deltas)
    state_gate = _state_gate_metrics(rows, selected_ids)
    abstain_debug = _abstain_telemetry(
        rows,
        selected_ids,
        apply_overlay_filter=apply_overlay_filter,
        apply_rules=apply_rules,
    )
    return {
        "metrics": metrics,
        "sequence_metrics": sequence_metrics,
        "state_gate": state_gate,
        "abstain_debug": abstain_debug,
    }


def _abstain_telemetry(
    rows: list[dict[str, Any]],
    selected_ids: list[str | None],
    *,
    apply_overlay_filter: bool,
    apply_rules: bool,
) -> dict[str, Any]:
    if len(rows) != len(selected_ids):
        raise ValueError("rows and selected_ids must be the same length")

    reason_counts: dict[str, int] = {}
    filter_totals = {"candidates_in": 0, "after_overlay_filter": 0, "after_rules": 0}
    abstain_rows = 0
    current_state: dict[str, Any] = {}

    for row, selected_id in zip(rows, selected_ids, strict=True):
        requires_state = row.get("requires_state")
        state_unmet = isinstance(requires_state, dict) and not state_matches(
            requires_state, current_state
        )

        if selected_id is None:
            abstain_rows += 1
            if state_unmet:
                reason_counts["requires_state_unmet"] = reason_counts.get(
                    "requires_state_unmet", 0
                ) + 1
            candidates = row.get("candidates", [])
            if isinstance(candidates, list):
                _, trace = preselect_candidates_with_trace(
                    row,
                    candidates,
                    apply_overlay_filter=apply_overlay_filter,
                    apply_rules=apply_rules,
                )
                candidates_in = trace.get("candidates_in") or []
                after_overlay = trace.get("after_overlay_filter") or []
                after_rules = trace.get("after_rules") or []
                filter_totals["candidates_in"] += len(candidates_in)
                filter_totals["after_overlay_filter"] += len(after_overlay)
                filter_totals["after_rules"] += len(after_rules)
                reasons = trace.get("reasons", {})
                if isinstance(reasons, dict):
                    for reason_list in reasons.values():
                        if not isinstance(reason_list, list):
                            continue
                        for reason in reason_list:
                            if isinstance(reason, str) and reason:
                                reason_counts[reason] = reason_counts.get(reason, 0) + 1
                if after_rules and len(after_rules) > 1:
                    reason_counts["ambiguous_remaining"] = reason_counts.get(
                        "ambiguous_remaining", 0
                    ) + 1
                if not after_rules:
                    reason_counts["no_candidates_after_rules"] = reason_counts.get(
                        "no_candidates_after_rules", 0
                    ) + 1

        next_state = _candidate_state_from_row(row, selected_id)
        if next_state:
            current_state = next_state

    if abstain_rows:
        filter_avgs = {
            key: value / abstain_rows for key, value in filter_totals.items()
        }
    else:
        filter_avgs = {key: 0.0 for key in filter_totals}

    return {
        "abstain_rows": abstain_rows,
        "abstain_reason_counts": reason_counts,
        "abstain_filter_averages": filter_avgs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare policy-only, greedy, and SA plans on UI fixtures."
    )
    parser.add_argument(
        "--fixture",
        default="data/ui_minipilot_traps_fixture.jsonl",
        help="Path to the UI fixture JSONL file.",
    )
    parser.add_argument(
        "--observed",
        help="Optional JSONL with {id, observed_delta} rows for post-action verification.",
    )
    parser.add_argument("--gate-model", help="Optional gate model JSON path.")
    parser.add_argument("--out", help="Optional output JSON path.")
    parser.add_argument("--out-csv", help="Optional output CSV summary path.")
    parser.add_argument(
        "--preferences-out",
        help="Optional output JSONL path for shorter & valid preferences.",
    )
    parser.add_argument("--seed", type=int, default=0, help="Random seed for greedy/SA.")
    parser.add_argument(
        "--seeds",
        type=int,
        default=1,
        help="Number of seeds to run (uses 0..seeds-1).",
    )
    parser.add_argument("--sa-iterations", type=int, default=200, help="SA iterations.")
    parser.add_argument("--sa-temp-start", type=float, default=1.0, help="SA start temperature.")
    parser.add_argument("--sa-temp-end", type=float, default=0.01, help="SA end temperature.")
    parser.add_argument("--alpha", type=float, default=0.1, help="Potential shaping weight.")
    parser.add_argument(
        "--wrong-action-penalty",
        type=float,
        default=1000.0,
        help="Penalty for wrong actions when fatal_wrong is off.",
    )
    parser.add_argument(
        "--abstain-penalty",
        type=float,
        default=1.0,
        help="Penalty for abstains when scoring plans.",
    )
    parser.add_argument(
        "--fatal-wrong",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Treat wrong actions as fatal when scoring plans.",
    )
    parser.add_argument(
        "--overlay-filter",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Apply overlay filtering in the policy and search.",
    )
    parser.add_argument(
        "--rules",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Apply deterministic preselect rules in the policy and search.",
    )
    parser.add_argument(
        "--state-gate",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Respect requires_state gating when scoring plans.",
    )
    parser.add_argument(
        "--fuzz-variants",
        type=int,
        default=0,
        help="Number of instruction/label fuzz variants to evaluate.",
    )
    parser.add_argument(
        "--fuzz-seed",
        type=int,
        default=0,
        help="Random seed for fuzzing variants.",
    )
    args = parser.parse_args()

    fixture_path = Path(args.fixture)
    if not fixture_path.exists():
        print(f"Fixture not found: {fixture_path}")
        return 1

    errors = validate_ui_fixture_path(fixture_path)
    if errors:
        print("Fixture validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    rows = list(read_jsonl(fixture_path))
    observed_deltas = None
    if args.observed:
        observed_path = Path(args.observed)
        if not observed_path.exists():
            print(f"Observed deltas not found: {observed_path}")
            return 1
        observed_deltas = _load_observed_deltas(observed_path, rows)

    gate_model = None
    if args.gate_model:
        gate_path = Path(args.gate_model)
        if not gate_path.exists():
            print(f"Gate model not found: {gate_path}")
            return 1
        gate_model = _load_gate_model(gate_path)

    def run_baseline(
        rows_to_score: list[dict[str, Any]],
        observed: list[dict[str, Any] | None] | None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        policy_plan = _policy_only_plan(
            rows_to_score,
            apply_overlay_filter=args.overlay_filter,
            apply_rules=args.rules,
        )
        gate_plan = None
        if gate_model is not None:
            gate_plan = _gate_plan(
                rows_to_score,
                gate_model,
                apply_overlay_filter=args.overlay_filter,
                apply_rules=args.rules,
            )
        def compute_score(plan: list[str | None]) -> float:
            score, _ = score_plan_against_gold(
                rows_to_score,
                plan,
                alpha=args.alpha,
                wrong_action_penalty=args.wrong_action_penalty,
                abstain_penalty=args.abstain_penalty,
                fatal_wrong=args.fatal_wrong,
                require_state_gate=args.state_gate,
                apply_overlay_filter=args.overlay_filter,
                apply_rules=args.rules,
            )
            return score

        def plan_validator(plan: list[str | None]) -> bool:
            if len(plan) != len(rows_to_score):
                return False
            if not args.state_gate:
                return True
            current_state: dict[str, Any] = {}
            for step, selected_id in zip(rows_to_score, plan, strict=True):
                candidates = _state_constrained_candidates(
                    step,
                    current_state,
                    apply_overlay_filter=args.overlay_filter,
                    apply_rules=args.rules,
                )
                if selected_id is not None:
                    allowed_ids = {
                        candidate.get("candidate_id")
                        for candidate in candidates
                        if isinstance(candidate, dict)
                        and isinstance(candidate.get("candidate_id"), str)
                    }
                    if selected_id not in allowed_ids:
                        return False
                next_state = _candidate_state_from_row(step, selected_id)
                if next_state:
                    current_state = next_state
            return True

        def run_for_seed(seed: int) -> dict[str, Any]:
            current_state: dict[str, Any] = {}
            greedy_plan: list[str | None] = []
            for step in rows_to_score:
                row, _ = _split_step(step)
                row_for_select = row if isinstance(row, dict) else {}
                candidates = _state_constrained_candidates(
                    step,
                    current_state,
                    apply_overlay_filter=args.overlay_filter,
                    apply_rules=args.rules,
                )
                if not candidates:
                    greedy_plan.append(None)
                    continue
                scored: list[tuple[dict[str, Any], int]] = []
                for candidate in candidates:
                    if not isinstance(candidate, dict):
                        continue
                    next_state = _candidate_state_from_row(
                        row_for_select, candidate.get("candidate_id")
                    )
                    score = delta_phi(current_state, next_state) if next_state else -1.0
                    scored.append((candidate, score))
                if not scored:
                    greedy_plan.append(None)
                    continue
                best_score = max(score for _, score in scored)
                best_candidates = [
                    candidate for candidate, score in scored if score == best_score
                ]
                chosen = best_candidates[seed % len(best_candidates)]
                candidate_id = chosen.get("candidate_id")
                greedy_plan.append(candidate_id if isinstance(candidate_id, str) else None)
                next_state = _candidate_state_from_row(row_for_select, greedy_plan[-1])
                if next_state:
                    current_state = next_state

            sa_start = time.perf_counter()
            sa_plan, sa_score, sa_telemetry = search_with_simulated_annealing(
                greedy_plan,
                rows_to_score,
                compute_score,
                is_valid_plan=plan_validator,
                iterations=args.sa_iterations,
                temp_start=args.sa_temp_start,
                temp_end=args.sa_temp_end,
                seed=seed,
                apply_overlay_filter=args.overlay_filter,
                apply_rules=args.rules,
                return_telemetry=True,
            )
            sa_runtime = time.perf_counter() - sa_start
            sa_telemetry["runtime_s"] = sa_runtime
            if sa_telemetry.get("iterations"):
                sa_telemetry["runtime_ms_per_iter"] = (
                    sa_runtime * 1000.0 / float(sa_telemetry["iterations"])
                )
            else:
                sa_telemetry["runtime_ms_per_iter"] = 0.0

            greedy_result = _score_strategy(
                rows_to_score,
                greedy_plan,
                observed,
                apply_overlay_filter=args.overlay_filter,
                apply_rules=args.rules,
            )
            sa_result = _score_strategy(
                rows_to_score,
                sa_plan,
                observed,
                apply_overlay_filter=args.overlay_filter,
                apply_rules=args.rules,
            )
            gate_result = None
            if gate_plan is not None:
                gate_result = _score_strategy(
                    rows_to_score,
                    gate_plan,
                    observed,
                    apply_overlay_filter=args.overlay_filter,
                    apply_rules=args.rules,
                )
            sa_beats_greedy = (
                sa_result["sequence_metrics"]["task_pass_rate"]
                > greedy_result["sequence_metrics"]["task_pass_rate"]
            )
            sa_diff = (
                _sa_vs_greedy_diff(rows_to_score, greedy_plan, sa_plan)
                if sa_beats_greedy
                else None
            )

            stats_by_strategy = {
                "policy": _stats_by_task(rows_to_score, policy_plan, observed),
                "greedy": _stats_by_task(rows_to_score, greedy_plan, observed),
                "sa": _stats_by_task(rows_to_score, sa_plan, observed),
            }
            if gate_plan is not None and gate_result is not None:
                stats_by_strategy["gate"] = _stats_by_task(
                    rows_to_score, gate_plan, observed
                )
            seed_preferences = _shorter_valid_prefs(
                str(fixture_path), seed, stats_by_strategy
            )

            return {
                "seed": seed,
                "policy": _score_strategy(
                    rows_to_score,
                    policy_plan,
                    observed,
                    apply_overlay_filter=args.overlay_filter,
                    apply_rules=args.rules,
                ),
                "greedy": greedy_result,
                "sa": {
                    **sa_result,
                    "score": sa_score,
                    "telemetry": sa_telemetry,
                },
                "gate": gate_result,
                "sa_beats_greedy": sa_beats_greedy,
                "sa_diff": sa_diff,
                "preferences": seed_preferences,
            }

        seed_count = max(1, args.seeds)
        seed_list = list(range(seed_count))
        seed_runs = [run_for_seed(seed) for seed in seed_list]
        run_preferences: list[dict[str, Any]] = []
        for run in seed_runs:
            run_preferences.extend(run.pop("preferences", []))
        payload = {
            "rows": len(rows_to_score),
            "fixture": str(fixture_path),
            "seed_list": seed_list,
        }
        payload["strategy_summary"] = _summarize_seed_runs(seed_runs)

        if seed_count == 1:
            single = seed_runs[0]
            payload.update(
                {
                    "policy": single["policy"],
                    "greedy": single["greedy"],
                    "sa": single["sa"],
                }
            )
            if single.get("gate") is not None:
                payload["gate"] = single["gate"]
        else:
            beats = 0
            for run in seed_runs:
                if run.get("sa_beats_greedy"):
                    beats += 1
            payload["seed_runs"] = seed_runs
            payload["seed_summary"] = {
                "seeds": seed_count,
                "seed_list": seed_list,
                "sa_beats_greedy_rate": beats / seed_count,
            }
        return payload, run_preferences

    payload, preferences = run_baseline(rows, observed_deltas)

    if args.fuzz_variants > 0:
        fuzz_seed = args.fuzz_seed
        variant_summaries: list[dict[str, Any]] = []
        for variant_index in range(args.fuzz_variants):
            rng = random.Random(fuzz_seed + variant_index)
            mutated_rows = _apply_text_fuzz(rows, rng)
            variant_payload, _ = run_baseline(mutated_rows, observed_deltas)
            seed_runs = _as_seed_runs(variant_payload)
            variant_summaries.append(
                {
                    "variant": variant_index,
                    "strategy_means": _summarize_seed_runs(seed_runs),
                }
            )
        strategy_means: dict[str, dict[str, list[float]]] = {}
        for entry in variant_summaries:
            for strategy, metrics in entry["strategy_means"].items():
                if strategy not in strategy_means:
                    strategy_means[strategy] = {key: [] for key in metrics}
                for key, value in metrics.items():
                    strategy_means[strategy][key].append(value)
        fuzz_summary: dict[str, Any] = {"variants": args.fuzz_variants, "seed": fuzz_seed}
        fuzz_summary["strategy_means"] = {
            strategy: {key: _mean(values) for key, values in metrics.items()}
            for strategy, metrics in strategy_means.items()
        }
        fuzz_summary["strategy_mins"] = {
            strategy: {key: _min(values) for key, values in metrics.items()}
            for strategy, metrics in strategy_means.items()
        }
        fuzz_summary["variant_summaries"] = variant_summaries
        payload["fuzz_summary"] = fuzz_summary

    out_path = Path(args.out) if args.out else None
    if out_path:
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    csv_path: Path | None = None
    if args.out_csv:
        csv_path = Path(args.out_csv)
    elif out_path:
        csv_path = out_path.with_name(out_path.stem + "_summary.csv")
    if csv_path:
        _write_summary_csv(
            csv_path,
            fixture=str(fixture_path),
            seeds=max(1, args.seeds),
            strategy_summary=payload.get("strategy_summary", {}),
        )

    pref_path: Path | None = None
    if args.preferences_out:
        pref_path = Path(args.preferences_out)
    elif out_path:
        pref_path = out_path.with_name(out_path.stem + "_preferences.jsonl")
    if pref_path:
        pref_path.parent.mkdir(parents=True, exist_ok=True)
        with pref_path.open("w", encoding="utf-8") as handle:
            for entry in preferences:
                handle.write(json.dumps(entry) + "\n")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
