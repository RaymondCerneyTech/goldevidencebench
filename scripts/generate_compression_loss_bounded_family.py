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
            "Generate compression_loss_bounded trap fixtures "
            "(anchors/holdout/canary) with deterministic synthetic ledgers."
        )
    )
    parser.add_argument(
        "--out-dir",
        default="data/compression_loss_bounded",
        help="Output directory for generated JSONL files.",
    )
    parser.add_argument("--anchors", type=int, default=8, help="Number of anchor rows.")
    parser.add_argument("--holdout", type=int, default=24, help="Number of holdout rows.")
    parser.add_argument(
        "--canary",
        type=int,
        default=8,
        help=(
            "Number of canary rows. Canary rows are intentionally stress-heavy and "
            "are expected to fail without stronger compaction behavior."
        ),
    )
    parser.add_argument("--seed", type=int, default=7, help="Deterministic RNG seed.")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing generated files.",
    )
    return parser.parse_args()


def _episode_id(split: str, index: int) -> str:
    return f"CLB-{split.upper()}-{index:04d}"


def _row_id(episode_id: str) -> str:
    return f"{episode_id}-Q001"


def _pick_value(key: str, *, rng: random.Random, exclude: str | None = None) -> str:
    choices = [v for v in _VALUES[key] if v != exclude]
    return rng.choice(choices)


def _build_row(*, split: str, index: int, rng: random.Random) -> dict[str, Any]:
    episode_id = _episode_id(split, index)
    row_id = _row_id(episode_id)
    # Keep gold support IDs within default max_support_k=3.
    key_count = rng.randint(2, 3)
    keys = sorted(rng.sample(_KEYS, key_count))

    episode_log_lines: list[str] = []
    ledger_lines: list[str] = []
    support_ids: list[str] = []
    compact_state: dict[str, Any] = {}
    step = 1

    for key in keys:
        initial = _pick_value(key, rng=rng)
        note_guess = _pick_value(key, rng=rng, exclude=initial)
        final_update = rng.choice(["set", "clear", "set"])

        uid_initial = f"U{rng.randrange(16**6):06X}"
        episode_log_lines.append(f"- [{uid_initial}] UPDATE step={step} SET {key} = {initial}")
        ledger_lines.append(f"- [{uid_initial}] step={step} SET {key} = {initial}")
        step += 1

        uid_note = f"U{rng.randrange(16**6):06X}"
        episode_log_lines.append(f"- [{uid_note}] UPDATE step={step} NOTE {key} = {note_guess}")
        ledger_lines.append(f"- [{uid_note}] step={step} NOTE {key} = {note_guess}")
        step += 1

        uid_final = f"U{rng.randrange(16**6):06X}"
        if final_update == "clear":
            episode_log_lines.append(f"- [{uid_final}] UPDATE step={step} CLEAR {key}")
            ledger_lines.append(f"- [{uid_final}] step={step} CLEAR {key}")
            compact_state[key] = None
        else:
            final_value = _pick_value(key, rng=rng, exclude=initial)
            episode_log_lines.append(f"- [{uid_final}] UPDATE step={step} SET {key} = {final_value}")
            ledger_lines.append(f"- [{uid_final}] step={step} SET {key} = {final_value}")
            compact_state[key] = final_value
        support_ids.append(uid_final)
        step += 1

    question = (
        "Return JSON with keys: value, support_ids. "
        "Set value to a JSON string with shape {\"compact_state\": {...}}. "
        "Build compact_state from the ledger only: keep the latest SET/CLEAR decision per key, ignore NOTE lines, "
        "and include every key that has a SET/CLEAR entry in the ledger exactly once. "
        "If the latest decision for a key is CLEAR, emit that key with null (do not omit it)."
    )
    value_json = json.dumps({"compact_state": compact_state}, sort_keys=True, ensure_ascii=True)
    document = (
        f"# Compression Episode {episode_id}\n\n"
        "## Episode Log\n"
        + "\n".join(episode_log_lines)
    )
    glossary = "\n".join(f"- {key}: Synthetic compression key {key}." for key in keys)
    book = (
        f"# Compression Episode {episode_id}\n\n"
        "## Reading Rules\n"
        "- The STATE LEDGER is authoritative.\n"
        "- Only SET/CLEAR lines update compact state.\n"
        "- NOTE lines are commentary.\n\n"
        "## Glossary (Tags)\n"
        f"{glossary}\n\n"
        "## Chapter 1\n"
        "The ledger contains authoritative updates and NOTE distractors.\n\n"
        "## State Ledger\n"
        + "\n".join(ledger_lines)
    )
    return {
        "id": row_id,
        "episode_id": episode_id,
        "schema_version": "0.1",
        "document": document,
        "book": book,
        "question": question,
        "gold": {
            "value": value_json,
            "compact_state": compact_state,
            "support_ids": support_ids,
        },
        "meta": {
            "family": "compression_loss_bounded",
            "split": split,
            "case_index": index,
            "requires_citation": False,
            "expected_keys": keys,
        },
    }


def _build_canary(*, seed: int, case_index: int) -> dict[str, Any]:
    rng = random.Random(seed + 97)
    keys = [f"tag.{idx:02d}" for idx in range(48)]
    episode_id = f"CLB-CANARY-{case_index:04d}"
    row_id = _row_id(episode_id)
    episode_log_lines: list[str] = []
    ledger_lines: list[str] = []
    support_ids: list[str] = []
    compact_state: dict[str, Any] = {}
    step = 1

    for key in keys:
        value_a = f"{key}_v{rng.randint(10, 99)}_base"
        value_b = f"{key}_v{rng.randint(100, 999)}_latest"
        note_guess = f"{key}_note_{rng.randint(1000, 9999)}"
        uid_set0 = f"U{rng.randrange(16**6):06X}"
        uid_note = f"U{rng.randrange(16**6):06X}"
        uid_final = f"U{rng.randrange(16**6):06X}"
        episode_log_lines.append(f"- [{uid_set0}] UPDATE step={step} SET {key} = {value_a}")
        ledger_lines.append(f"- [{uid_set0}] step={step} SET {key} = {value_a}")
        step += 1
        episode_log_lines.append(f"- [{uid_note}] UPDATE step={step} NOTE {key} = {note_guess}")
        ledger_lines.append(f"- [{uid_note}] step={step} NOTE {key} = {note_guess}")
        step += 1
        if rng.random() < 0.2:
            episode_log_lines.append(f"- [{uid_final}] UPDATE step={step} CLEAR {key}")
            ledger_lines.append(f"- [{uid_final}] step={step} CLEAR {key}")
            compact_state[key] = None
        else:
            episode_log_lines.append(f"- [{uid_final}] UPDATE step={step} SET {key} = {value_b}")
            ledger_lines.append(f"- [{uid_final}] step={step} SET {key} = {value_b}")
            compact_state[key] = value_b
        support_ids.append(uid_final)
        step += 1

    glossary = "\n".join(f"- {key}: Synthetic compression key {key}." for key in keys)
    document = (
        f"# Compression Episode {episode_id}\n\n"
        "## Episode Log\n"
        + "\n".join(episode_log_lines)
    )
    book = (
        f"# Compression Episode {episode_id}\n\n"
        "## Reading Rules\n"
        "- The STATE LEDGER is authoritative.\n"
        "- Only SET/CLEAR lines update compact state.\n"
        "- NOTE lines are commentary.\n\n"
        "## Glossary (Tags)\n"
        f"{glossary}\n\n"
        "## Chapter 1\n"
        "This canary intentionally uses a large key set to stress compaction fidelity under context pressure.\n\n"
        "## State Ledger\n"
        + "\n".join(ledger_lines)
    )
    return {
        "id": row_id,
        "episode_id": episode_id,
        "schema_version": "0.1",
        "document": document,
        "book": book,
        "question": (
            "Return JSON with keys: value, support_ids. "
            "Set value to a JSON string with shape {\"compact_state\": {...}}. "
            "Use only ledger SET/CLEAR updates, ignore NOTE lines, and include every key with a SET/CLEAR entry exactly once. "
            "If latest is CLEAR, include that key with null."
        ),
        "gold": {
            "value": json.dumps({"compact_state": compact_state}, sort_keys=True, ensure_ascii=True),
            "compact_state": compact_state,
            "support_ids": support_ids,
        },
        "meta": {
            "family": "compression_loss_bounded",
            "split": "canary",
            "case_index": case_index,
            "seed": seed,
            "expected_fail": True,
            "expected_keys": sorted(compact_state.keys()),
            "canary_profile": "stress_many_keys",
        },
    }


def _build_canaries(*, count: int, seed: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx in range(count):
        row = _build_canary(seed=seed + idx, case_index=idx + 1)
        rows.append(row)
    return rows


def _ensure_write(path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")


def main() -> int:
    ns = _parse_args()
    out_dir = Path(ns.out_dir)
    anchors_path = out_dir / "compression_loss_bounded_anchors.jsonl"
    holdout_path = out_dir / "compression_loss_bounded_holdout.jsonl"
    canary_path = out_dir / "compression_loss_bounded_canary.jsonl"

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
    canary = _build_canaries(count=ns.canary, seed=ns.seed)

    write_jsonl(anchors_path, anchors)
    write_jsonl(holdout_path, holdout)
    write_jsonl(canary_path, canary)

    print("Wrote compression_loss_bounded fixtures:")
    print(f"- {anchors_path}")
    print(f"- {holdout_path}")
    print(f"- {canary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
