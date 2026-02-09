from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

from goldevidencebench.util import write_jsonl


_DIMS = ("identity", "timeline", "constraint")
_CHARS = ("arya", "ilya", "maren", "soren")
_ALIASES = ("rook", "wren", "glass-harbor", "ember-kite", "north-lantern")
_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday")
_RULES = ("no_blades_inside", "no_magic_on_platform", "no_engine_start", "no_open_flame")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate novel_continuity fixtures (anchors/holdout/canary) for "
            "long-context narrative state consistency."
        )
    )
    parser.add_argument("--out-dir", default="data/novel_continuity", help="Output directory.")
    parser.add_argument("--anchors", type=int, default=12, help="Anchor row count.")
    parser.add_argument("--holdout", type=int, default=36, help="Holdout row count.")
    parser.add_argument("--canary", type=int, default=6, help="Canary row count.")
    parser.add_argument("--seed", type=int, default=31, help="Deterministic seed.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing files.")
    return parser.parse_args()


def _ensure_write(path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")


def _episode_id(split: str, index: int) -> str:
    return f"NC-{split.upper()}-{index:04d}"


def _row_id(episode_id: str) -> str:
    return f"{episode_id}-Q001"


def _uid(rng: random.Random) -> str:
    return f"U{rng.randrange(16**6):06X}"


def _pick(items: tuple[str, ...], rng: random.Random, exclude: str | None = None) -> str:
    choices = [x for x in items if x != exclude]
    return rng.choice(choices)


def _identity_case(rng: random.Random) -> tuple[str, str, str, str, str]:
    char = _pick(_CHARS, rng)
    initial = _pick(_ALIASES, rng)
    rumor = _pick(_ALIASES, rng, exclude=initial)
    final = _pick(_ALIASES, rng, exclude=rumor)
    key = f"{char}.codename"
    question = f"By end of Chapter 4, what codename does {char.title()} use?"
    return key, initial, rumor, final, question


def _timeline_case(rng: random.Random) -> tuple[str, str, str, str, str]:
    event = _pick(("vault.unlock_day", "ferry.depart_day", "hearing.day"), rng)
    initial = _pick(_DAYS, rng)
    rumor = _pick(_DAYS, rng, exclude=initial)
    final = _pick(_DAYS, rng, exclude=rumor)
    question = f"By end of Chapter 4, what is the authoritative day for {event}?"
    return event, initial, rumor, final, question


def _constraint_case(rng: random.Random) -> tuple[str, str, str, str | None, str]:
    key = _pick(("citadel.rule", "dock.rule", "archive.rule"), rng)
    initial = _pick(_RULES, rng)
    rumor = _pick(_RULES, rng, exclude=initial)
    if rng.random() < 0.30:
        final = None
        question = f"By end of Chapter 4, what is the active constraint for {key}? If revoked, value is null."
    else:
        final = _pick(_RULES, rng, exclude=rumor)
        question = f"By end of Chapter 4, what is the active constraint for {key}?"
    return key, initial, rumor, final, question


def _build_row(*, split: str, index: int, rng: random.Random) -> dict[str, Any]:
    episode_id = _episode_id(split, index)
    row_id = _row_id(episode_id)
    dim = _DIMS[(index - 1) % len(_DIMS)]
    if split == "holdout":
        dim = rng.choice(_DIMS)

    if dim == "identity":
        key, initial, rumor, final, question = _identity_case(rng)
    elif dim == "timeline":
        key, initial, rumor, final, question = _timeline_case(rng)
    else:
        key, initial, rumor, final, question = _constraint_case(rng)

    side_key = _pick(("weather", "gate.status", "torch.count"), rng)
    side_value = _pick(("clear", "locked", "3", "6", "storm"), rng)

    uid_set1 = _uid(rng)
    uid_note = _uid(rng)
    uid_set2 = _uid(rng)
    uid_side = _uid(rng)

    ledger_lines = [
        f"- [{uid_set1}] step=1 SET {key} = {initial}",
        f"- [{uid_note}] step=2 NOTE {key} = {rumor}",
    ]
    episode_lines = [
        f"- [{uid_set1}] UPDATE step=1 SET {key} = {initial}",
        f"- [{uid_note}] UPDATE step=2 NOTE {key} = {rumor}",
    ]
    if final is None:
        ledger_lines.append(f"- [{uid_set2}] step=3 CLEAR {key}")
        episode_lines.append(f"- [{uid_set2}] UPDATE step=3 CLEAR {key}")
    else:
        ledger_lines.append(f"- [{uid_set2}] step=3 SET {key} = {final}")
        episode_lines.append(f"- [{uid_set2}] UPDATE step=3 SET {key} = {final}")
    ledger_lines.append(f"- [{uid_side}] step=4 SET {side_key} = {side_value}")
    episode_lines.append(f"- [{uid_side}] UPDATE step=4 SET {side_key} = {side_value}")

    ch1 = f"Chapter 1: The crew records {key} as {initial}."
    ch2 = f"Chapter 2: Rumors claim {key} might be {rumor}."
    ch3 = (
        f"Chapter 3: The archive updates {key} to {final}."
        if final is not None
        else f"Chapter 3: The archive revokes {key}."
    )
    ch4 = (
        f"Chapter 4: Team acts according to the latest {key} state while {side_key} stays at {side_value}."
    )
    book = (
        f"# Novel Continuity Episode {episode_id}\n\n"
        "## Reading rules\n"
        "- Chapter narration can contain rumor or stale statements.\n"
        "- State Ledger is authoritative for final state.\n"
        "- Only SET/CLEAR lines in the ledger define continuity state.\n\n"
        f"{ch1}\n{ch2}\n{ch3}\n{ch4}\n\n"
        "## State Ledger\n"
        + "\n".join(ledger_lines)
    )
    document = f"# Episode Log {episode_id}\n\n" + "\n".join(episode_lines)
    final_value = final
    if final_value is None:
        query_target_type = "null"
    else:
        query_target_type = "value"

    return {
        "id": row_id,
        "episode_id": episode_id,
        "schema_version": "0.1",
        "document": document,
        "book": book,
        "question": (
            f"{question} Return JSON with keys: value, support_ids. "
            "If revoked, set value=null."
        ),
        "gold": {
            "value": final_value,
            "support_ids": [uid_set2],
        },
        "meta": {
            "family": "novel_continuity",
            "split": split,
            "case_index": index,
            "dimension": dim,
            "key": key,
            "query_target_type": query_target_type,
            "requires_citation": True,
        },
    }


def _build_canary(*, seed: int, case_index: int) -> dict[str, Any]:
    rng = random.Random(seed + 701 + case_index)
    episode_id = _episode_id("canary", case_index)
    row_id = _row_id(episode_id)
    dim = _DIMS[(case_index - 1) % len(_DIMS)]

    if dim == "identity":
        key, initial, rumor, final, base_question = _identity_case(rng)
    elif dim == "timeline":
        key, initial, rumor, final, base_question = _timeline_case(rng)
    else:
        key, initial, rumor, final, base_question = _constraint_case(rng)

    if final is None:
        candidate_values: list[str | None] = [initial, rumor, _pick(_ALIASES if dim == "identity" else _DAYS if dim == "timeline" else _RULES, rng), None]
    else:
        candidate_values = [initial, rumor, final, _pick(_ALIASES if dim == "identity" else _DAYS if dim == "timeline" else _RULES, rng)]

    ledger_lines: list[str] = []
    episode_lines: list[str] = []
    support_final = ""
    for step in range(1, 13):
        uid = _uid(rng)
        if step in (2, 4, 6, 8, 10):
            rumor_val = rng.choice([v for v in candidate_values if v is not None])
            ledger_lines.append(f"- [{uid}] step={step} NOTE {key} = {rumor_val}")
            episode_lines.append(f"- [{uid}] UPDATE step={step} NOTE {key} = {rumor_val}")
            continue
        if step == 11:
            if final is None:
                ledger_lines.append(f"- [{uid}] step={step} CLEAR {key}")
                episode_lines.append(f"- [{uid}] UPDATE step={step} CLEAR {key}")
            else:
                ledger_lines.append(f"- [{uid}] step={step} SET {key} = {final}")
                episode_lines.append(f"- [{uid}] UPDATE step={step} SET {key} = {final}")
            support_final = uid
            continue
        set_val = rng.choice([v for v in candidate_values if v is not None])
        ledger_lines.append(f"- [{uid}] step={step} SET {key} = {set_val}")
        episode_lines.append(f"- [{uid}] UPDATE step={step} SET {key} = {set_val}")

    # Add unrelated updates to increase context pressure.
    for extra in range(1, 13):
        uid = _uid(rng)
        noise_key = f"noise.{extra:02d}"
        noise_val = f"n{rng.randint(10, 999)}"
        ledger_lines.append(f"- [{uid}] step={20 + extra} SET {noise_key} = {noise_val}")
        episode_lines.append(f"- [{uid}] UPDATE step={20 + extra} SET {noise_key} = {noise_val}")

    book = (
        f"# Novel Continuity Episode {episode_id}\n\n"
        "## Reading rules\n"
        "- This canary intentionally includes long retcon chains and decoys.\n"
        "- State Ledger is authoritative.\n"
        "- Only SET/CLEAR lines define final state.\n\n"
        "## Chapters\n"
        "Chapter 1-4 include conflicting statements and rumors across scenes.\n\n"
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
        "question": (
            f"{base_question} Return JSON with keys: value, support_ids. "
            "If revoked, set value=null."
        ),
        "gold": {
            "value": final,
            "support_ids": [support_final],
        },
        "meta": {
            "family": "novel_continuity",
            "split": "canary",
            "case_index": case_index,
            "dimension": dim,
            "key": key,
            "expected_fail": True,
            "canary_profile": "retcon_chain_tail",
        },
    }


def main() -> int:
    ns = _parse_args()
    out_dir = Path(ns.out_dir)
    anchors_path = out_dir / "novel_continuity_anchors.jsonl"
    holdout_path = out_dir / "novel_continuity_holdout.jsonl"
    canary_path = out_dir / "novel_continuity_canary.jsonl"

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
    canary = [_build_canary(seed=ns.seed, case_index=i + 1) for i in range(ns.canary)]

    write_jsonl(anchors_path, anchors)
    write_jsonl(holdout_path, holdout)
    write_jsonl(canary_path, canary)

    print("Wrote novel_continuity fixtures:")
    print(f"- {anchors_path}")
    print(f"- {holdout_path}")
    print(f"- {canary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
