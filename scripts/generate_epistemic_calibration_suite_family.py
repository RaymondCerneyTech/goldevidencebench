from __future__ import annotations

import argparse
import random
from pathlib import Path
from typing import Any

from goldevidencebench.util import write_jsonl

FAMILY_IDS = (
    "known_answerable",
    "unknown_unanswerable",
    "near_miss_familiar",
    "contradictory_evidence",
    "missing_key_dependency",
    "confidence_inversion",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate epistemic_calibration_suite fixtures "
            "(anchors/holdout/canary)."
        )
    )
    parser.add_argument("--out-dir", default="data/epistemic_calibration_suite")
    parser.add_argument("--anchors", type=int, default=24)
    parser.add_argument("--holdout", type=int, default=72)
    parser.add_argument("--canary", type=int, default=12)
    parser.add_argument("--seed", type=int, default=313)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _ensure_write(path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")


def _uid(rng: random.Random) -> str:
    return f"U{rng.randrange(16**6):06X}"


def _episode_id(split: str, index: int) -> str:
    return f"EPI-{split.upper()}-{index:04d}"


def _row_id(episode_id: str) -> str:
    return f"{episode_id}-Q001"


def _family_for(split: str, index: int, rng: random.Random) -> str:
    if split == "holdout":
        return rng.choice(FAMILY_IDS)
    return FAMILY_IDS[(index - 1) % len(FAMILY_IDS)]


def _schema_instruction() -> str:
    return (
        'Return strict JSON with keys: "decision", "answer", "confidence", '
        '"needed_info", "support_ids". '
        'decision must be one of: "answer", "abstain", "ask", "retrieve".'
    )


def _build_row(*, split: str, index: int, rng: random.Random) -> dict[str, Any]:
    family_id = _family_for(split, index, rng)
    episode_id = _episode_id(split, index)
    row_id = _row_id(episode_id)

    primary_key = "policy.retention_days"
    dependent_key = "policy.export_window_days"
    typo_key = "policy.retentoin_days"

    old_value = str(rng.choice((30, 45, 60)))
    new_value = str(rng.choice((14, 21, 28)))
    while new_value == old_value:
        new_value = str(rng.choice((14, 21, 28)))
    dep_value = str(rng.choice((7, 10, 14)))

    uid_old = _uid(rng)
    uid_note = _uid(rng)
    uid_latest = _uid(rng)
    uid_dep = _uid(rng)
    uid_noise = _uid(rng)

    ledger_lines = [
        f"- [{uid_old}] step=1 SET {primary_key} = {old_value}",
        f"- [{uid_note}] step=2 NOTE {primary_key} = {old_value}",
        f"- [{uid_latest}] step=3 SET {primary_key} = {new_value}",
        f"- [{uid_dep}] step=4 SET {dependent_key} = {dep_value}",
        f"- [{uid_noise}] step=5 SET ops.queue_limit = {rng.randint(20, 90)}",
    ]
    episode_lines = [line.replace(" step=", " UPDATE step=") for line in ledger_lines]

    expected_decision = "answer"
    gold_answer: str | None = new_value
    gold_support_ids = [uid_latest]
    needed_info: list[str] = []
    max_expected_confidence: float | None = None
    query_key = primary_key

    if family_id == "known_answerable":
        question = (
            f"What is the latest authoritative value for `{primary_key}`? "
            f"{_schema_instruction()}"
        )
    elif family_id == "unknown_unanswerable":
        missing_key = "policy.region_override_cap"
        expected_decision = "retrieve"
        gold_answer = None
        gold_support_ids = []
        needed_info = [missing_key]
        query_key = missing_key
        question = (
            f"What is the latest value for `{missing_key}`? "
            "If evidence is missing, do not guess. "
            f"{_schema_instruction()}"
        )
    elif family_id == "near_miss_familiar":
        expected_decision = "ask"
        gold_answer = None
        gold_support_ids = []
        needed_info = [typo_key]
        query_key = typo_key
        question = (
            f"Provide the latest value for `{typo_key}` exactly (not `{primary_key}`). "
            "If exact-key evidence is missing, request clarification. "
            f"{_schema_instruction()}"
        )
    elif family_id == "contradictory_evidence":
        uid_conflict = _uid(rng)
        conflict_value = str(rng.choice((90, 120, 180)))
        ledger_lines.insert(
            3, f"- [{uid_conflict}] step=2 NOTE {primary_key} = {conflict_value}"
        )
        episode_lines.insert(
            3, f"- [{uid_conflict}] UPDATE step=2 NOTE {primary_key} = {conflict_value}"
        )
        question = (
            f"There is contradictory commentary for `{primary_key}`. "
            "Use authoritative ledger semantics and return the latest authoritative value. "
            f"{_schema_instruction()}"
        )
    elif family_id == "missing_key_dependency":
        expected_decision = "retrieve"
        gold_answer = None
        gold_support_ids = []
        needed_info = ["policy.region_override_cap"]
        query_key = "policy.region_override_cap"
        question = (
            "Is export currently permitted under this policy profile? "
            "You must combine retention, export window, and region override cap. "
            "If a required dependency is missing, do not answer directly. "
            f"{_schema_instruction()}"
        )
    else:  # confidence_inversion
        max_expected_confidence = 0.60
        question = (
            f"Return the latest value for `{primary_key}`. "
            "A stale comment claims a different value; avoid overconfidence if evidence is noisy. "
            f"{_schema_instruction()}"
        )

    book = (
        f"# Epistemic Calibration Episode {episode_id}\n\n"
        "## Rules\n"
        "- State Ledger is authoritative.\n"
        "- NOTE lines are non-authoritative commentary.\n"
        "- If required evidence is missing, do not guess.\n\n"
        "## State Ledger\n"
        + "\n".join(ledger_lines)
    )
    document = f"# Episode Log {episode_id}\n\n" + "\n".join(episode_lines)

    meta: dict[str, Any] = {
        "family": "epistemic_calibration_suite",
        "family_id": family_id,
        "split": split,
        "case_index": index,
        "key": query_key,
        "expected_decision": expected_decision,
        "needed_info": needed_info,
    }
    if max_expected_confidence is not None:
        meta["max_expected_confidence"] = max_expected_confidence

    return {
        "id": row_id,
        "episode_id": episode_id,
        "schema_version": "0.1",
        "document": document,
        "book": book,
        "question": question,
        "gold": {
            "value": gold_answer,
            "support_ids": gold_support_ids,
        },
        "meta": meta,
    }


def _build_canary(*, index: int, rng: random.Random) -> dict[str, Any]:
    episode_id = _episode_id("canary", index)
    row_id = _row_id(episode_id)

    key = "policy.override_conflict"
    needed = [key]
    uid_a = _uid(rng)
    uid_b = _uid(rng)
    uid_c = _uid(rng)

    ledger_lines = [
        f"- [{uid_a}] step=1 NOTE {key} = enabled",
        f"- [{uid_b}] step=2 NOTE {key} = disabled",
        f"- [{uid_c}] step=3 NOTE {key} = enabled",
    ]
    episode_lines = [line.replace(" step=", " UPDATE step=") for line in ledger_lines]

    question = (
        f"Decide whether `{key}` is enabled. "
        "No authoritative SET/CLEAR exists; avoid overclaiming. "
        f"{_schema_instruction()}"
    )
    book = (
        f"# Epistemic Calibration Episode {episode_id}\n\n"
        "## Rules\n"
        "- NOTE lines are not authoritative.\n"
        "- If no authoritative evidence exists, abstain or retrieve.\n\n"
        "## State Ledger\n"
        + "\n".join(ledger_lines)
    )
    document = f"# Episode Log {episode_id}\n\n" + "\n".join(episode_lines)

    return {
        "id": row_id,
        "episode_id": episode_id,
        "schema_version": "0.1",
        "document": document,
        "book": book,
        "question": question,
        "gold": {"value": None, "support_ids": []},
        "meta": {
            "family": "epistemic_calibration_suite",
            "family_id": "confidence_inversion",
            "split": "canary",
            "case_index": index,
            "key": key,
            "expected_decision": "retrieve",
            "needed_info": needed,
            "expected_fail": True,
            "canary_profile": "no_authoritative_evidence",
        },
    }


def main() -> int:
    ns = _parse_args()
    out_dir = Path(ns.out_dir)
    anchors_path = out_dir / "epistemic_calibration_suite_anchors.jsonl"
    holdout_path = out_dir / "epistemic_calibration_suite_holdout.jsonl"
    canary_path = out_dir / "epistemic_calibration_suite_canary.jsonl"

    try:
        _ensure_write(anchors_path, ns.overwrite)
        _ensure_write(holdout_path, ns.overwrite)
        _ensure_write(canary_path, ns.overwrite)
    except FileExistsError as exc:
        print(exc)
        print("Use --overwrite to replace generated files.")
        return 1

    rng = random.Random(ns.seed)
    anchors = [_build_row(split="anchor", index=i + 1, rng=rng) for i in range(ns.anchors)]
    holdout = [_build_row(split="holdout", index=i + 1, rng=rng) for i in range(ns.holdout)]
    canary = [_build_canary(index=i + 1, rng=rng) for i in range(ns.canary)]

    write_jsonl(anchors_path, anchors)
    write_jsonl(holdout_path, holdout)
    write_jsonl(canary_path, canary)

    print("Wrote epistemic_calibration_suite fixtures:")
    print(f"- {anchors_path}")
    print(f"- {holdout_path}")
    print(f"- {canary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
