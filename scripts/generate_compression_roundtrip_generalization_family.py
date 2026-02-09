from __future__ import annotations

import argparse
import random
from pathlib import Path
from typing import Any

from goldevidencebench.util import write_jsonl


_QUERY_TYPES = ("direct", "aggregate", "exception", "negation")
_GROUPS = ("alpha", "beta", "gamma", "delta")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate compression_roundtrip_generalization fixtures "
            "(anchors/holdout/canary) with query-type coverage and tail-key stress."
        )
    )
    parser.add_argument(
        "--out-dir",
        default="data/compression_roundtrip_generalization",
        help="Output directory for generated JSONL files.",
    )
    parser.add_argument("--anchors", type=int, default=16, help="Anchor row count.")
    parser.add_argument("--holdout", type=int, default=48, help="Holdout row count.")
    parser.add_argument("--canary", type=int, default=8, help="Canary row count.")
    parser.add_argument(
        "--canary-key-count",
        type=int,
        default=96,
        help="Approximate key count per canary row.",
    )
    parser.add_argument("--seed", type=int, default=67, help="Deterministic RNG seed.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing files.")
    return parser.parse_args()


def _episode_id(split: str, index: int) -> str:
    return f"CRG-{split.upper()}-{index:04d}"


def _row_id(episode_id: str) -> str:
    return f"{episode_id}-Q001"


def _uid(rng: random.Random) -> str:
    return f"U{rng.randrange(16**6):06X}"


def _value_for_key(key: str, *, rng: random.Random) -> str:
    if key == "policy.mode":
        return rng.choice(("normal", "review", "locked"))
    if key == "policy.window_days":
        return rng.choice(("7", "14", "30", "60"))
    if key.endswith(".tier"):
        return rng.choice(("bronze", "silver", "gold"))
    if key.endswith(".enabled"):
        return rng.choice(("true", "false"))
    return f"v{rng.randint(100, 999)}"


def _ensure_write(path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")


def _query_target_type(value: Any) -> str:
    if value is None:
        return "null"
    return "nonnull"


def _key_pool() -> list[str]:
    out: list[str] = ["policy.mode", "policy.window_days"]
    for group in _GROUPS:
        for i in range(24):
            out.append(f"cfg.{group}.{i:02d}")
    out.extend(
        (
            "feature.export.enabled",
            "feature.audit.enabled",
            "feature.sync.enabled",
            "ops.alert.tier",
            "ops.backup.tier",
        )
    )
    return out


def _noise_lines(*, rng: random.Random, step_start: int, count: int) -> tuple[list[str], list[str]]:
    ledger: list[str] = []
    episode: list[str] = []
    for i in range(count):
        step = step_start + i
        uid = _uid(rng)
        key = f"noise.{i:02d}"
        value = f"n{rng.randint(1000, 9999)}"
        ledger.append(f"- [{uid}] step={step} NOTE {key} = {value}")
        episode.append(f"- [{uid}] UPDATE step={step} NOTE {key} = {value}")
    return ledger, episode


def _sample_query_type(*, split: str, index: int, rng: random.Random) -> str:
    if split == "holdout":
        return rng.choice(_QUERY_TYPES)
    return _QUERY_TYPES[(index - 1) % len(_QUERY_TYPES)]


def _snapshot_key_count(*, split: str, index: int, rng: random.Random) -> int:
    # Ensure anchors and holdout contain true large-snapshot rows so
    # large_snapshot_acc is measurable and gateable.
    if split == "anchor":
        # First 4 rows cycle query types and are forced large.
        if index <= 4:
            return rng.randint(68, 84)
        return rng.randint(18, 30)
    # Holdout: periodic large rows for stable subset coverage.
    if split == "holdout" and (index % 6 == 0):
        return rng.randint(68, 96)
    return rng.randint(24, 44)


def _build_row(*, split: str, index: int, rng: random.Random) -> dict[str, Any]:
    episode_id = _episode_id(split, index)
    row_id = _row_id(episode_id)

    pool = _key_pool()
    snapshot_key_count = _snapshot_key_count(split=split, index=index, rng=rng)
    selected = rng.sample(pool, snapshot_key_count)
    if "policy.mode" not in selected:
        selected[0] = "policy.mode"
    if "policy.window_days" not in selected:
        selected[1] = "policy.window_days"

    compact_state: dict[str, Any] = {}
    support_by_key: dict[str, str] = {}
    ledger_lines: list[str] = []
    episode_lines: list[str] = []
    step = 1

    for key in selected:
        if rng.random() < 0.30:
            uid_note = _uid(rng)
            note_value = _value_for_key(key, rng=rng)
            ledger_lines.append(f"- [{uid_note}] step={step} NOTE {key} = {note_value}")
            episode_lines.append(f"- [{uid_note}] UPDATE step={step} NOTE {key} = {note_value}")
            step += 1

        uid_final = _uid(rng)
        support_by_key[key] = uid_final
        force_set = key in ("policy.mode", "policy.window_days")
        if (not force_set) and rng.random() < 0.22:
            compact_state[key] = None
            ledger_lines.append(f"- [{uid_final}] step={step} CLEAR {key}")
            episode_lines.append(f"- [{uid_final}] UPDATE step={step} CLEAR {key}")
        else:
            value = _value_for_key(key, rng=rng)
            if key == "policy.mode":
                # Increase locked coverage for exception queries.
                value = rng.choice(("locked", "normal", "locked", "review"))
            compact_state[key] = value
            ledger_lines.append(f"- [{uid_final}] step={step} SET {key} = {value}")
            episode_lines.append(f"- [{uid_final}] UPDATE step={step} SET {key} = {value}")
        step += 1

    # Ensure at least one clear key for negation coverage.
    cleared_keys = [k for k, v in compact_state.items() if v is None]
    if not cleared_keys:
        target_clear = selected[-1]
        compact_state[target_clear] = None
        uid_clear = _uid(rng)
        support_by_key[target_clear] = uid_clear
        ledger_lines.append(f"- [{uid_clear}] step={step} CLEAR {target_clear}")
        episode_lines.append(f"- [{uid_clear}] UPDATE step={step} CLEAR {target_clear}")
        step += 1
        cleared_keys = [target_clear]

    noise_count = 6
    note_ledger, note_episode = _noise_lines(rng=rng, step_start=step, count=noise_count)
    ledger_lines.extend(note_ledger)
    episode_lines.extend(note_episode)
    step += noise_count

    query_type = _sample_query_type(split=split, index=index, rng=rng)
    tail_start = max(0, len(selected) - max(3, len(selected) // 5))
    tail_keys = selected[tail_start:]
    head_keys = selected[: max(3, len(selected) // 5)]
    value: Any = None
    support_ids: list[str] = []
    query_position = "mixed"
    question = ""
    extra_meta: dict[str, Any] = {}

    if query_type == "direct":
        # Alternate head/tail coverage across direct rows.
        direct_block = (index - 1) // len(_QUERY_TYPES)
        prefer_tail = (direct_block % 2) == 1
        source = tail_keys if prefer_tail else head_keys
        source_nonnull = [k for k in source if compact_state.get(k) is not None]
        selected_nonnull = [k for k in selected if compact_state.get(k) is not None]
        query_key = rng.choice(source_nonnull or source or selected_nonnull or selected)
        value = compact_state[query_key]
        support_ids = [support_by_key[query_key]]
        query_position = "tail" if query_key in tail_keys else "head"
        question = f"Resolve the current authoritative value for `{query_key}`."
        extra_meta["query_key"] = query_key
    elif query_type == "aggregate":
        triad = rng.sample(selected, 3)
        nonnull_count = sum(1 for k in triad if compact_state.get(k) is not None)
        value = str(nonnull_count)
        support_ids = [support_by_key[k] for k in triad]
        if all(k in tail_keys for k in triad):
            query_position = "tail"
        elif all(k in head_keys for k in triad):
            query_position = "head"
        question = "Resolve the authoritative aggregate non-null count."
        extra_meta["aggregate_keys"] = triad
    elif query_type == "exception":
        mode_key = "policy.mode"
        window_key = "policy.window_days"
        mode_value = compact_state.get(mode_key)
        window_value = compact_state.get(window_key)
        if mode_value == "locked":
            value = "0"
        elif window_value is None:
            value = None
        else:
            value = str(window_value)
        if mode_value == "locked":
            support_ids = [support_by_key[mode_key]]
        else:
            support_ids = [support_by_key[window_key]]
        query_position = "head"
        question = "Resolve authoritative `effective_window_days`."
        extra_meta["exception_rule"] = "locked=>0 else policy.window_days"
        extra_meta["mode_key"] = mode_key
        extra_meta["window_key"] = window_key
    else:  # negation
        query_key = rng.choice(cleared_keys)
        value = compact_state[query_key]
        support_ids = [support_by_key[query_key]]
        query_position = "tail" if query_key in tail_keys else "head"
        question = f"Resolve whether `{query_key}` is currently cleared."
        extra_meta["query_key"] = query_key

    resolved_uid = _uid(rng)
    resolved_key = "answer.resolved"
    if value is None:
        ledger_lines.append(f"- [{resolved_uid}] step={step} CLEAR {resolved_key}")
        episode_lines.append(f"- [{resolved_uid}] UPDATE step={step} CLEAR {resolved_key}")
    else:
        ledger_lines.append(f"- [{resolved_uid}] step={step} SET {resolved_key} = {value}")
        episode_lines.append(f"- [{resolved_uid}] UPDATE step={step} SET {resolved_key} = {value}")
    step += 1
    support_ids = [resolved_uid]
    question = (
        f"Return the latest authoritative value for `{resolved_key}` from the State Ledger. "
        "Return JSON with keys: value, support_ids (use value=null if cleared)."
    )
    extra_meta["resolved_key"] = resolved_key

    book = (
        f"# Compression Roundtrip Episode {episode_id}\n\n"
        "## Reading rules\n"
        "- State Ledger is authoritative for compact snapshot state.\n"
        "- Only the latest SET/CLEAR per key defines the compact state.\n"
        "- NOTE lines are non-authoritative distractors.\n"
        "- Use only the ledger for answers.\n\n"
        "## State Ledger\n"
        + "\n".join(ledger_lines)
    )

    return {
        "id": row_id,
        "episode_id": episode_id,
        "schema_version": "0.1",
        "document": f"# Episode Log {episode_id}\n\n" + "\n".join(episode_lines),
        "book": book,
        "question": question,
        "gold": {
            "value": value,
            "support_ids": support_ids,
        },
        "meta": {
            "family": "compression_roundtrip_generalization",
            "split": split,
            "case_index": index,
            "query_type": query_type,
            "query_position": query_position,
            "query_target_type": _query_target_type(value),
            "snapshot_key_count": len(selected),
            "requires_citation": True,
            **extra_meta,
        },
    }


def _build_canary(*, seed: int, case_index: int, key_count: int) -> dict[str, Any]:
    rng = random.Random(seed + 1900 + case_index)
    episode_id = _episode_id("canary", case_index)
    row_id = _row_id(episode_id)
    snapshot_key_count = max(64, key_count + rng.randint(-8, 8))
    keys = [f"cfg.tailstress.{i:03d}" for i in range(snapshot_key_count)]
    target_key = keys[-1]

    ledger_lines: list[str] = []
    episode_lines: list[str] = []
    step = 1
    prelatest_uid = ""
    prelatest_value: str | None = None

    for key in keys[:-1]:
        uid = _uid(rng)
        if rng.random() < 0.18:
            ledger_lines.append(f"- [{uid}] step={step} CLEAR {key}")
            episode_lines.append(f"- [{uid}] UPDATE step={step} CLEAR {key}")
        else:
            value = f"{key}_v{rng.randint(1000, 9999)}"
            ledger_lines.append(f"- [{uid}] step={step} SET {key} = {value}")
            episode_lines.append(f"- [{uid}] UPDATE step={step} SET {key} = {value}")
        step += 1

    # Canary target: ask for value before latest authoritative update.
    uid_first = _uid(rng)
    first_value = f"{target_key}_v{rng.randint(1000, 9999)}"
    ledger_lines.append(f"- [{uid_first}] step={step} SET {target_key} = {first_value}")
    episode_lines.append(f"- [{uid_first}] UPDATE step={step} SET {target_key} = {first_value}")
    step += 1

    uid_note = _uid(rng)
    note_value = f"{target_key}_note_{rng.randint(1000, 9999)}"
    ledger_lines.append(f"- [{uid_note}] step={step} NOTE {target_key} = {note_value}")
    episode_lines.append(f"- [{uid_note}] UPDATE step={step} NOTE {target_key} = {note_value}")
    step += 1

    uid_prelatest = _uid(rng)
    prelatest_value = f"{target_key}_v{rng.randint(1000, 9999)}"
    prelatest_uid = uid_prelatest
    ledger_lines.append(f"- [{uid_prelatest}] step={step} SET {target_key} = {prelatest_value}")
    episode_lines.append(f"- [{uid_prelatest}] UPDATE step={step} SET {target_key} = {prelatest_value}")
    step += 1

    uid_latest = _uid(rng)
    latest_value = f"{target_key}_v{rng.randint(1000, 9999)}"
    ledger_lines.append(f"- [{uid_latest}] step={step} SET {target_key} = {latest_value}")
    episode_lines.append(f"- [{uid_latest}] UPDATE step={step} SET {target_key} = {latest_value}")

    book = (
        f"# Compression Roundtrip Episode {episode_id}\n\n"
        "## Reading rules\n"
        "- This canary stresses tail-key retrieval in large snapshots.\n"
        "- State Ledger is authoritative.\n"
        "- NOTE lines are non-authoritative.\n\n"
        "## State Ledger\n"
        + "\n".join(ledger_lines)
    )

    return {
        "id": row_id,
        "episode_id": episode_id,
        "schema_version": "0.1",
        "document": f"# Episode Log {episode_id}\n\n" + "\n".join(episode_lines),
        "book": book,
        "question": (
            f"For `{target_key}`, what was the value immediately before the latest authoritative update? "
            "Return JSON with keys: value, support_ids."
        ),
        "gold": {
            "value": prelatest_value,
            "support_ids": [prelatest_uid] if prelatest_uid else [],
        },
        "meta": {
            "family": "compression_roundtrip_generalization",
            "split": "canary",
            "case_index": case_index,
            "query_type": "prelatest_tail",
            "query_position": "tail",
            "query_target_type": "nonnull",
            "snapshot_key_count": snapshot_key_count,
            "expected_fail": True,
            "canary_profile": "large_tail_prelatest_lookup",
            "query_key": target_key,
        },
    }


def main() -> int:
    ns = _parse_args()
    out_dir = Path(ns.out_dir)
    anchors_path = out_dir / "compression_roundtrip_generalization_anchors.jsonl"
    holdout_path = out_dir / "compression_roundtrip_generalization_holdout.jsonl"
    canary_path = out_dir / "compression_roundtrip_generalization_canary.jsonl"

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
    canary = [
        _build_canary(seed=ns.seed, case_index=i + 1, key_count=ns.canary_key_count)
        for i in range(ns.canary)
    ]

    write_jsonl(anchors_path, anchors)
    write_jsonl(holdout_path, holdout)
    write_jsonl(canary_path, canary)

    print("Wrote compression_roundtrip_generalization fixtures:")
    print(f"- {anchors_path}")
    print(f"- {holdout_path}")
    print(f"- {canary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
