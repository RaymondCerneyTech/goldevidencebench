from __future__ import annotations

from collections.abc import Iterable
from typing import Any


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
    correct_count = 0
    wrong_count = 0
    abstain_count = 0

    for row, selected in zip(rows_list, selected_ids, strict=True):
        candidates = row.get("candidates", [])
        candidate_ids = {c.get("candidate_id") for c in candidates if isinstance(c, dict)}
        gold = row.get("gold", {})
        gold_id = gold.get("candidate_id") if isinstance(gold, dict) else None

        if gold_id in candidate_ids:
            gold_present_count += 1

        if selected is None:
            abstain_count += 1
            continue

        if selected == gold_id:
            correct_count += 1
        else:
            wrong_count += 1

    accuracy_when_gold_present = (
        (correct_count / gold_present_count) if gold_present_count else 0.0
    )

    return {
        "gold_present_rate": gold_present_count / total,
        "selection_rate": correct_count / total,
        "wrong_action_rate": wrong_count / total,
        "abstain_rate": abstain_count / total,
        "accuracy_when_gold_present": accuracy_when_gold_present,
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
