from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

from goldevidencebench.util import write_jsonl


_KEYS = (
    "tag.00",
    "tag.01",
    "tag.02",
    "tag.03",
    "tag.04",
    "tag.05",
)

_VALUES = {
    "tag.00": ["30", "45", "60", "90"],
    "tag.01": ["us-east", "us-west", "eu-central", "ap-south"],
    "tag.02": ["100", "250", "500", "1000"],
    "tag.03": ["ops", "sec", "infra", "platform"],
    "tag.04": ["pager", "ticket", "chatops"],
    "tag.05": ["normal", "audit", "locked", "review"],
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate compression_recoverability fixtures "
            "(anchors/holdout/canary) for extracting values from compact snapshots."
        )
    )
    parser.add_argument(
        "--out-dir",
        default="data/compression_recoverability",
        help="Output directory for generated JSONL files.",
    )
    parser.add_argument("--anchors", type=int, default=12, help="Number of anchor rows.")
    parser.add_argument("--holdout", type=int, default=32, help="Number of holdout rows.")
    parser.add_argument(
        "--canary",
        type=int,
        default=6,
        help="Number of canary rows (multi-row stress profile).",
    )
    parser.add_argument(
        "--canary-key-count",
        type=int,
        default=96,
        help="Approximate key count per canary row (large snapshots).",
    )
    parser.add_argument("--seed", type=int, default=17, help="Deterministic RNG seed.")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing generated files.",
    )
    return parser.parse_args()


def _ensure_write(path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")


def _pick_value(*, key: str, rng: random.Random, exclude: str | None = None) -> str:
    choices = [v for v in _VALUES[key] if v != exclude]
    return rng.choice(choices)


def _episode_id(split: str, index: int) -> str:
    return f"CRV-{split.upper()}-{index:04d}"


def _row_id(episode_id: str) -> str:
    return f"{episode_id}-Q001"


def _build_row(*, split: str, index: int, rng: random.Random) -> dict[str, Any]:
    episode_id = _episode_id(split, index)
    row_id = _row_id(episode_id)
    key_count = rng.randint(3, 6)
    keys = sorted(rng.sample(_KEYS, key_count))
    query_key = rng.choice(keys)

    compact_state: dict[str, Any] = {}
    support_by_key: dict[str, str] = {}
    ledger_lines: list[str] = []
    episode_log_lines: list[str] = []
    for step, key in enumerate(keys, start=1):
        uid = f"U{rng.randrange(16**6):06X}"
        support_by_key[key] = uid
        if rng.random() < 0.25:
            compact_state[key] = None
            update_line = f"- [{uid}] step={step} CLEAR {key}"
            ledger_lines.append(update_line)
            episode_log_lines.append(f"- [{uid}] UPDATE step={step} CLEAR {key}")
        else:
            value = _pick_value(key=key, rng=rng)
            compact_state[key] = value
            update_line = f"- [{uid}] step={step} SET {key} = {value}"
            ledger_lines.append(update_line)
            episode_log_lines.append(f"- [{uid}] UPDATE step={step} SET {key} = {value}")

    glossary = "\n".join(f"- {key}: Snapshot key {key}." for key in keys)
    book = (
        f"# Recoverability Episode {episode_id}\n\n"
        "## Reading Rules\n"
        "- The STATE LEDGER below is already compacted (one authoritative update per key).\n"
        "- Answer only from the ledger.\n\n"
        "## Glossary (Tags)\n"
        f"{glossary}\n\n"
        "## State Ledger\n"
        + "\n".join(ledger_lines)
    )
    value = compact_state.get(query_key)
    question = (
        f"What is the value of {query_key} in the compact snapshot? "
        "Return JSON with keys: value, support_ids."
    )
    return {
        "id": row_id,
        "episode_id": episode_id,
        "schema_version": "0.1",
        "document": (
            f"# Recoverability Episode {episode_id}\n\n"
            "## Episode Log\n"
            + "\n".join(episode_log_lines)
        ),
        "book": book,
        "question": question,
        "gold": {
            "value": value,
            "support_ids": [support_by_key[query_key]],
        },
        "meta": {
            "family": "compression_recoverability",
            "split": split,
            "case_index": index,
            "key": query_key,
            "query_type": "direct",
            # Keep full compact snapshot visible (not key-filtered) for this family.
            "derived_op": "reports",
            "compact_state": compact_state,
        },
    }


def _build_canary(*, seed: int, case_index: int, key_count: int) -> dict[str, Any]:
    rng = random.Random(seed + 303 + case_index)
    episode_id = _episode_id("canary", case_index)
    row_id = _row_id(episode_id)
    snapshot_keys = max(24, key_count + rng.randint(-8, 8))
    keys = [f"tag.{i:03d}" for i in range(snapshot_keys)]
    compact_state: dict[str, Any] = {}
    ledger_lines: list[str] = []
    support_by_key: dict[str, str] = {}
    episode_log_lines: list[str] = []

    for step, key in enumerate(keys, start=1):
        uid = f"U{rng.randrange(16**6):06X}"
        support_by_key[key] = uid
        # Force a null/non-null mix while still adding variance.
        if step == 1:
            is_clear = False
        elif step == snapshot_keys:
            is_clear = True
        else:
            is_clear = ((step + case_index) % 7 == 0) or (rng.random() < 0.15)
        if is_clear:
            compact_state[key] = None
            ledger_lines.append(f"- [{uid}] step={step} CLEAR {key}")
            episode_log_lines.append(f"- [{uid}] UPDATE step={step} CLEAR {key}")
        else:
            value = f"{key}_snapshot_{rng.randint(1000, 9999)}"
            compact_state[key] = value
            ledger_lines.append(f"- [{uid}] step={step} SET {key} = {value}")
            episode_log_lines.append(f"- [{uid}] UPDATE step={step} SET {key} = {value}")

    tail_window = keys[max(0, len(keys) - 16) :]
    null_tail = [key for key in tail_window if compact_state.get(key) is None]
    value_tail = [key for key in tail_window if compact_state.get(key) is not None]
    prefer_null = (case_index % 2) == 1
    if prefer_null and null_tail:
        query_key = rng.choice(null_tail)
        query_target_type = "null"
    elif (not prefer_null) and value_tail:
        query_key = rng.choice(value_tail)
        query_target_type = "value"
    elif null_tail:
        query_key = rng.choice(null_tail)
        query_target_type = "null"
    elif value_tail:
        query_key = rng.choice(value_tail)
        query_target_type = "value"
    else:
        query_key = keys[-1]
        query_target_type = "null" if compact_state.get(query_key) is None else "value"

    book = (
        f"# Recoverability Episode {episode_id}\n\n"
        "## Reading Rules\n"
        "- This canary intentionally uses a large compact snapshot and tail-key queries.\n"
        "- A key may be CLEAR; if so, the answer value is null.\n"
        "- Answer only from the ledger.\n\n"
        "## State Ledger\n"
        + "\n".join(ledger_lines)
    )
    return {
        "id": row_id,
        "episode_id": episode_id,
        "schema_version": "0.1",
        "document": (
            f"# Recoverability Episode {episode_id}\n\n"
            "## Episode Log\n"
            + "\n".join(episode_log_lines)
        ),
        "book": book,
        "question": (
            f"What is the value of {query_key} in the compact snapshot? "
            "If the latest action is CLEAR, return value=null. "
            "Return JSON with keys: value, support_ids."
        ),
        "gold": {
            "value": compact_state[query_key],
            "support_ids": [support_by_key[query_key]],
        },
        "meta": {
            "family": "compression_recoverability",
            "split": "canary",
            "case_index": case_index,
            "key": query_key,
            "query_type": "direct",
            "derived_op": "reports",
            "expected_fail": True,
            "canary_profile": "stress_large_snapshot_tail_key",
            "snapshot_key_count": snapshot_keys,
            "query_position": "tail",
            "query_target_type": query_target_type,
        },
    }


def main() -> int:
    ns = _parse_args()
    out_dir = Path(ns.out_dir)
    anchors_path = out_dir / "compression_recoverability_anchors.jsonl"
    holdout_path = out_dir / "compression_recoverability_holdout.jsonl"
    canary_path = out_dir / "compression_recoverability_canary.jsonl"

    try:
        _ensure_write(anchors_path, ns.overwrite)
        _ensure_write(holdout_path, ns.overwrite)
        _ensure_write(canary_path, ns.overwrite)
    except FileExistsError as exc:
        print(exc)
        print("Use --overwrite to replace the generated files.")
        return 1

    rng = random.Random(ns.seed)
    anchors = [_build_row(split="anchor", index=i + 1, rng=rng) for i in range(ns.anchors)]
    holdout = [_build_row(split="holdout", index=i + 1, rng=rng) for i in range(ns.holdout)]
    canary = [
        _build_canary(seed=ns.seed, case_index=i + 1, key_count=ns.canary_key_count)
        for i in range(ns.canary)
    ]

    write_jsonl(anchors_path, anchors)
    write_jsonl(holdout_path, holdout)
    write_jsonl(canary_path, canary)

    print("Wrote compression_recoverability fixtures:")
    print(f"- {anchors_path}")
    print(f"- {holdout_path}")
    print(f"- {canary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
