from __future__ import annotations

import argparse
import random
from pathlib import Path
from typing import Any

from goldevidencebench.util import write_jsonl


_KEY_VALUES: dict[str, tuple[str, ...]] = {
    "policy.retention_days_eu": ("14", "30", "60", "90"),
    "policy.export_window_days": ("7", "14", "21", "30"),
    "policy.password_rotate_days": ("30", "45", "60", "90"),
    "policy.cache_ttl_minutes": ("15", "30", "60", "120"),
}

_NOISE_KEYS = (
    "ops.queue_limit",
    "ops.retry_budget",
    "ops.ui_timeout_ms",
    "ops.batch_size",
    "ops.redaction_mode",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate authority_under_interference_hardening fixtures "
            "(anchors/holdout/canary)."
        )
    )
    parser.add_argument("--out-dir", default="data/authority_under_interference_hardening")
    parser.add_argument("--anchors", type=int, default=20)
    parser.add_argument("--holdout", type=int, default=60)
    parser.add_argument("--canary", type=int, default=10)
    parser.add_argument("--seed", type=int, default=137)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _ensure_write(path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")


def _uid(rng: random.Random) -> str:
    return f"U{rng.randrange(16**6):06X}"


def _episode_id(split: str, index: int) -> str:
    return f"AUIH-{split.upper()}-{index:04d}"


def _row_id(episode_id: str) -> str:
    return f"{episode_id}-Q001"


def _pick_key(rng: random.Random, index: int) -> str:
    keys = sorted(_KEY_VALUES.keys())
    return keys[(index - 1) % len(keys)] if index > 0 else rng.choice(keys)


def _pick_value(
    key: str,
    rng: random.Random,
    *,
    exclude: str | None = None,
) -> str:
    values = [v for v in _KEY_VALUES[key] if v != exclude]
    return rng.choice(values)


def _build_row(*, split: str, index: int, rng: random.Random) -> dict[str, Any]:
    episode_id = _episode_id(split, index)
    row_id = _row_id(episode_id)
    key = _pick_key(rng, index)

    old_value = _pick_value(key, rng)
    note_value = _pick_value(key, rng, exclude=old_value)
    final_is_clear = (split == "holdout" and index % 7 == 0) or (
        split == "anchor" and index % 9 == 0
    )
    if final_is_clear:
        final_value = None
    else:
        final_value = _pick_value(key, rng, exclude=note_value)

    uid_set_old = _uid(rng)
    uid_note_decoy = _uid(rng)
    uid_stale_reinforce = _uid(rng)
    uid_latest = _uid(rng)
    uid_note_after = _uid(rng)

    ledger_lines = [
        f"- [{uid_set_old}] step=1 SET {key} = {old_value}",
        f"- [{uid_note_decoy}] step=2 NOTE {key} = {note_value}",
        f"- [{uid_stale_reinforce}] step=3 SET {key} = {old_value}",
    ]
    episode_lines = [
        f"- [{uid_set_old}] UPDATE step=1 SET {key} = {old_value}",
        f"- [{uid_note_decoy}] UPDATE step=2 NOTE {key} = {note_value}",
        f"- [{uid_stale_reinforce}] UPDATE step=3 SET {key} = {old_value}",
    ]

    if final_value is None:
        ledger_lines.append(f"- [{uid_latest}] step=4 CLEAR {key}")
        episode_lines.append(f"- [{uid_latest}] UPDATE step=4 CLEAR {key}")
        question_suffix = "If the key is cleared, return value=null."
    else:
        ledger_lines.append(f"- [{uid_latest}] step=4 SET {key} = {final_value}")
        episode_lines.append(f"- [{uid_latest}] UPDATE step=4 SET {key} = {final_value}")
        question_suffix = "Return the latest authoritative value."

    # A late NOTE should not replace the latest authoritative SET/CLEAR.
    ledger_lines.append(f"- [{uid_note_after}] step=5 NOTE {key} = {note_value}")
    episode_lines.append(f"- [{uid_note_after}] UPDATE step=5 NOTE {key} = {note_value}")

    for step in range(6, 10):
        noise_key = rng.choice(_NOISE_KEYS)
        noise_value = str(rng.randint(2, 999))
        uid_noise = _uid(rng)
        ledger_lines.append(f"- [{uid_noise}] step={step} SET {noise_key} = {noise_value}")
        episode_lines.append(
            f"- [{uid_noise}] UPDATE step={step} SET {noise_key} = {noise_value}"
        )

    stale_memo = (
        f"Legacy memo (stale): {key} was {old_value}. "
        f"Another comment claims {key} could be {note_value}."
    )
    stale_bullet = "\n".join(
        [
            f"- stale_snapshot: {key}={old_value}",
            f"- stale_snapshot_duplicate: {key}={old_value}",
            f"- rumor_snapshot: {key}={note_value}",
        ]
    )
    book = (
        f"# Authority Interference Episode {episode_id}\n\n"
        "## Rules\n"
        "- State Ledger is authoritative.\n"
        "- Only the latest SET/CLEAR for a key defines the answer.\n"
        "- NOTE lines are non-authoritative decoys.\n"
        "- Stale snapshots can repeat old values and must be ignored.\n\n"
        "## Interference\n"
        f"{stale_memo}\n{stale_bullet}\n\n"
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
            f"For key `{key}`, what is the latest authoritative value? {question_suffix} "
            "Return JSON with keys: value, support_ids."
        ),
        "gold": {
            "value": final_value,
            "support_ids": [uid_latest],
        },
        "meta": {
            "family": "authority_under_interference_hardening",
            "split": split,
            "case_index": index,
            "key": key,
            "latest_support_ids": [uid_latest],
            "stale_support_ids": [uid_set_old, uid_stale_reinforce],
            "note_support_ids": [uid_note_decoy, uid_note_after],
            "query_target_type": "null" if final_value is None else "value",
        },
    }


def _build_canary(*, seed: int, case_index: int) -> dict[str, Any]:
    rng = random.Random(seed + 900 + case_index)
    episode_id = _episode_id("canary", case_index)
    row_id = _row_id(episode_id)
    key = _pick_key(rng, case_index)

    old_value = _pick_value(key, rng)
    decoy_value = _pick_value(key, rng, exclude=old_value)
    final_value = _pick_value(key, rng, exclude=decoy_value)

    stale_ids: list[str] = []
    note_ids: list[str] = []
    latest_ids: list[str] = []
    penultimate_ids: list[str] = []
    ledger_lines: list[str] = []
    episode_lines: list[str] = []

    # Long chain with repeated stale and NOTE decoys.
    for step in range(1, 17):
        uid = _uid(rng)
        if step in (2, 4, 6, 8, 10, 12):
            ledger_lines.append(f"- [{uid}] step={step} NOTE {key} = {decoy_value}")
            episode_lines.append(f"- [{uid}] UPDATE step={step} NOTE {key} = {decoy_value}")
            note_ids.append(uid)
            continue
        if step in (3, 5, 7, 9, 11):
            ledger_lines.append(f"- [{uid}] step={step} SET {key} = {old_value}")
            episode_lines.append(f"- [{uid}] UPDATE step={step} SET {key} = {old_value}")
            stale_ids.append(uid)
            continue
        if step == 15:
            ledger_lines.append(f"- [{uid}] step={step} SET {key} = {final_value}")
            episode_lines.append(f"- [{uid}] UPDATE step={step} SET {key} = {final_value}")
            latest_ids.append(uid)
            continue
        if step == 16:
            # Final line is a NOTE decoy to tempt last-line selection mistakes.
            ledger_lines.append(f"- [{uid}] step={step} NOTE {key} = {decoy_value}")
            episode_lines.append(f"- [{uid}] UPDATE step={step} NOTE {key} = {decoy_value}")
            note_ids.append(uid)
            continue
        ledger_lines.append(f"- [{uid}] step={step} SET {key} = {old_value}")
        episode_lines.append(f"- [{uid}] UPDATE step={step} SET {key} = {old_value}")
        stale_ids.append(uid)
        if step == 14:
            penultimate_ids.append(uid)

    for step in range(20, 28):
        uid = _uid(rng)
        noise_key = f"noise.{step}"
        noise_value = f"n{rng.randint(10, 999)}"
        ledger_lines.append(f"- [{uid}] step={step} SET {noise_key} = {noise_value}")
        episode_lines.append(f"- [{uid}] UPDATE step={step} SET {noise_key} = {noise_value}")

    book = (
        f"# Authority Interference Episode {episode_id}\n\n"
        "## Rules\n"
        "- Ledger is authoritative.\n"
        "- Only latest SET/CLEAR counts.\n"
        "- NOTE entries are decoys even if they appear later.\n\n"
        "## Interference\n"
        f"- stale_snapshot: {key}={old_value}\n"
        f"- stale_snapshot_duplicate: {key}={old_value}\n"
        f"- rumor_snapshot: {key}={decoy_value}\n\n"
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
            f"For key `{key}`, return the authoritative value immediately before the "
            "latest authoritative update (ignore NOTE and stale snapshots). "
            "Return JSON with keys value, support_ids."
        ),
        "gold": {
            "value": old_value,
            "support_ids": penultimate_ids,
        },
        "meta": {
            "family": "authority_under_interference_hardening",
            "split": "canary",
            "case_index": case_index,
            "key": key,
            "latest_support_ids": latest_ids,
            "penultimate_support_ids": penultimate_ids,
            "stale_support_ids": stale_ids,
            "note_support_ids": note_ids,
            "expected_fail": True,
            "canary_profile": "prelatest_authority_lookup",
            "query_target_type": "prelatest_authoritative_value",
        },
    }


def main() -> int:
    ns = _parse_args()
    out_dir = Path(ns.out_dir)
    anchors_path = out_dir / "authority_under_interference_hardening_anchors.jsonl"
    holdout_path = out_dir / "authority_under_interference_hardening_holdout.jsonl"
    canary_path = out_dir / "authority_under_interference_hardening_canary.jsonl"

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
    holdout = [
        _build_row(split="holdout", index=i + 1, rng=rng) for i in range(ns.holdout)
    ]
    canary = [
        _build_canary(seed=ns.seed, case_index=i + 1) for i in range(ns.canary)
    ]

    write_jsonl(anchors_path, anchors)
    write_jsonl(holdout_path, holdout)
    write_jsonl(canary_path, canary)

    print("Wrote authority_under_interference_hardening fixtures:")
    print(f"- {anchors_path}")
    print(f"- {holdout_path}")
    print(f"- {canary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


