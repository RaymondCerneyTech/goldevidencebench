from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def score_ui_rows(
    rows: Iterable[dict[str, Any]], selected_ids: list[str | None]
) -> dict[str, float]:
    rows_list = list(rows)
    total = len(rows_list)
    if len(selected_ids) != total:
        raise ValueError("selected_ids length must match rows length")
    if total == 0:
        return {
            "gold_present_rate": 0.0,
            "selection_rate": 0.0,
            "wrong_action_rate": 0.0,
            "abstain_rate": 0.0,
            "accuracy_when_gold_present": 0.0,
        }

    gold_present_count = 0
    gold_present_for_accuracy = 0
    correct_count = 0
    wrong_count = 0
    abstain_count = 0
    abstain_expected_count = 0
    abstain_expected_correct = 0

    for row, selected in zip(rows_list, selected_ids, strict=True):
        candidates = row.get("candidates", [])
        candidate_ids = {c.get("candidate_id") for c in candidates if isinstance(c, dict)}
        gold = row.get("gold", {})
        gold_id = gold.get("candidate_id") if isinstance(gold, dict) else None
        abstain_expected = row.get("abstain_expected") is True

        if gold_id in candidate_ids:
            gold_present_count += 1
            if not abstain_expected:
                gold_present_for_accuracy += 1

        if selected is None:
            abstain_count += 1
            if abstain_expected:
                abstain_expected_count += 1
                abstain_expected_correct += 1
            continue

        if abstain_expected:
            abstain_expected_count += 1
            wrong_count += 1
            continue

        if selected == gold_id:
            correct_count += 1
        else:
            wrong_count += 1

    accuracy_when_gold_present = (
        (correct_count / gold_present_for_accuracy) if gold_present_for_accuracy else 0.0
    )
    abstain_expected_rate = (
        (abstain_expected_correct / abstain_expected_count)
        if abstain_expected_count
        else 0.0
    )

    return {
        "gold_present_rate": gold_present_count / total,
        "selection_rate": correct_count / total,
        "wrong_action_rate": wrong_count / total,
        "abstain_rate": abstain_count / total,
        "accuracy_when_gold_present": accuracy_when_gold_present,
        "abstain_expected_rate": abstain_expected_rate,
        "abstain_expected_count": float(abstain_expected_count),
    }


def score_post_action_verification(
    rows: Iterable[dict[str, Any]], observed_deltas: list[dict[str, Any] | None]
) -> dict[str, float]:
    rows_list = list(rows)
    total = len(rows_list)
    if len(observed_deltas) != total:
        raise ValueError("observed_deltas length must match rows length")
    if total == 0:
        return {"post_action_verify_rate": 0.0}

    expected_total = 0
    verified = 0

    for row, observed in zip(rows_list, observed_deltas, strict=True):
        if row.get("abstain_expected") is True:
            continue
        expected = row.get("expected_delta")
        if expected is None:
            continue
        if not isinstance(expected, dict):
            continue
        expected_total += 1
        if not isinstance(observed, dict):
            continue
        if all(observed.get(key) == value for key, value in expected.items()):
            verified += 1

    rate = (verified / expected_total) if expected_total else 0.0
    return {"post_action_verify_rate": rate}


def _task_min_steps(rows: list[dict[str, Any]], indices: list[int]) -> int | None:
    values = {
        row.get("min_steps")
        for idx in indices
        for row in [rows[idx]]
        if _is_int(row.get("min_steps"))
    }
    if not values:
        return None
    if len(values) > 1:
        return None
    return int(next(iter(values)))


def task_step_stats(
    rows: Iterable[dict[str, Any]],
    selected_ids: list[str | None],
    observed_deltas: list[dict[str, Any] | None] | None = None,
) -> list[dict[str, Any]]:
    rows_list = list(rows)
    total = len(rows_list)
    if len(selected_ids) != total:
        raise ValueError("selected_ids length must match rows length")
    if observed_deltas is not None and len(observed_deltas) != total:
        raise ValueError("observed_deltas length must match rows length")
    if total == 0:
        return []

    tasks: dict[str, list[int]] = {}
    for idx, row in enumerate(rows_list):
        task_id = row.get("task_id")
        if isinstance(task_id, str) and task_id.strip():
            key = task_id
        else:
            key = f"__row_{idx:04d}"
        tasks.setdefault(key, []).append(idx)

    stats: list[dict[str, Any]] = []
    for task_id, indices in tasks.items():
        wrong_action = False
        all_selected = True
        abstain_count = 0
        expected_total = 0
        verified = 0

        for idx in indices:
            row = rows_list[idx]
            selected = selected_ids[idx]
            abstain_expected = row.get("abstain_expected") is True
            candidates = row.get("candidates", [])
            candidate_ids = {
                c.get("candidate_id") for c in candidates if isinstance(c, dict)
            }
            gold = row.get("gold", {})
            gold_id = gold.get("candidate_id") if isinstance(gold, dict) else None

            if gold_id not in candidate_ids and not abstain_expected:
                all_selected = False
            if selected is None:
                abstain_count += 1
                if not abstain_expected:
                    all_selected = False
            elif abstain_expected:
                wrong_action = True
                all_selected = False
            elif selected != gold_id:
                wrong_action = True
                all_selected = False

            if observed_deltas is not None:
                if abstain_expected:
                    continue
                expected = row.get("expected_delta")
                if isinstance(expected, dict):
                    expected_total += 1
                    observed = observed_deltas[idx]
                    if isinstance(observed, dict) and all(
                        observed.get(key) == value for key, value in expected.items()
                    ):
                        verified += 1

        verify_rate: float | None
        if observed_deltas is not None and expected_total:
            verify_rate = verified / expected_total
        else:
            verify_rate = None

        pass_condition = (
            (not wrong_action)
            and all_selected
            and (verify_rate == 1.0 or (verify_rate is None and expected_total == 0))
        )

        min_steps = _task_min_steps(rows_list, indices)
        steps_taken = sum(
            1 for idx in indices if selected_ids[idx] is not None
        )
        step_overhead = (
            (steps_taken / min_steps) if pass_condition and min_steps else None
        )

        stats.append(
            {
                "task_id": task_id,
                "task_len": len(indices),
                "steps_taken": steps_taken,
                "min_steps": min_steps,
                "step_overhead": step_overhead,
                "pass": pass_condition,
                "wrong_action": wrong_action,
                "abstain_rate": abstain_count / len(indices),
                "verify_rate": verify_rate,
            }
        )
    return stats


def score_ui_sequences(
    rows: Iterable[dict[str, Any]],
    selected_ids: list[str | None],
    observed_deltas: list[dict[str, Any] | None] | None = None,
) -> dict[str, float | int | None]:
    rows_list = list(rows)
    total = len(rows_list)
    if len(selected_ids) != total:
        raise ValueError("selected_ids length must match rows length")
    if observed_deltas is not None and len(observed_deltas) != total:
        raise ValueError("observed_deltas length must match rows length")
    if total == 0:
        return {
            "tasks_total": 0,
            "task_pass_rate": 0.0,
            "task_wrong_action_rate": 0.0,
            "task_post_action_verify_mean": None,
            "task_abstain_rate_mean": 0.0,
            "task_len_mean": 0.0,
            "task_step_overhead_mean": None,
            "task_step_overhead_min": None,
            "task_step_overhead_max": None,
            "task_step_overhead_count": 0,
            "task_steps_taken_mean": None,
            "task_min_steps_mean": None,
        }
    stats = task_step_stats(rows_list, selected_ids, observed_deltas)
    tasks_total = len(stats)
    task_passes = sum(1 for stat in stats if stat["pass"])
    task_wrong_actions = sum(1 for stat in stats if stat["wrong_action"])
    task_abstain_rates = [stat["abstain_rate"] for stat in stats]
    task_lengths = [stat["task_len"] for stat in stats]
    task_verify_rates = [
        stat["verify_rate"] for stat in stats if stat["verify_rate"] is not None
    ]

    task_post_action_verify_mean = (
        sum(task_verify_rates) / len(task_verify_rates) if task_verify_rates else None
    )

    step_overheads = [
        stat["step_overhead"] for stat in stats if stat["step_overhead"] is not None
    ]
    step_overhead_count = len(step_overheads)
    steps_taken_values = [
        stat["steps_taken"] for stat in stats if stat["step_overhead"] is not None
    ]
    min_steps_values = [
        stat["min_steps"] for stat in stats if stat["step_overhead"] is not None
    ]

    return {
        "tasks_total": tasks_total,
        "task_pass_rate": task_passes / tasks_total,
        "task_wrong_action_rate": task_wrong_actions / tasks_total,
        "task_post_action_verify_mean": task_post_action_verify_mean,
        "task_abstain_rate_mean": sum(task_abstain_rates) / tasks_total,
        "task_len_mean": sum(task_lengths) / tasks_total,
        "task_step_overhead_mean": (
            sum(step_overheads) / step_overhead_count if step_overhead_count else None
        ),
        "task_step_overhead_min": min(step_overheads) if step_overheads else None,
        "task_step_overhead_max": max(step_overheads) if step_overheads else None,
        "task_step_overhead_count": step_overhead_count,
        "task_steps_taken_mean": (
            sum(steps_taken_values) / step_overhead_count if step_overhead_count else None
        ),
        "task_min_steps_mean": (
            sum(min_steps_values) / step_overhead_count if step_overhead_count else None
        ),
    }
