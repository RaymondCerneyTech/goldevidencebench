from __future__ import annotations

import argparse
import random
from pathlib import Path
from typing import Any

from goldevidencebench.util import write_jsonl


_DIMS = ("identity", "timeline", "constraint")
_CHARS = ("arya", "ilya", "maren", "soren", "talia", "corin")
_ALIASES = ("rook", "wren", "glass-harbor", "ember-kite", "north-lantern", "pale-bridge")
_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday")
_RULES = (
    "no_blades_inside",
    "no_magic_on_platform",
    "no_engine_start",
    "no_open_flame",
    "no_radio_after_midnight",
)
_NOISE_KEYS = (
    "weather.front",
    "gate.status",
    "torch.count",
    "dock.queue",
    "patrol.zone",
    "supply.batch",
    "archive.code",
    "signal.band",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate novel_continuity_long_horizon fixtures "
            "(anchors/holdout/canary) with longer callback gaps and contradiction pressure."
        )
    )
    parser.add_argument("--out-dir", default="data/novel_continuity_long_horizon", help="Output directory.")
    parser.add_argument("--anchors", type=int, default=16, help="Anchor row count.")
    parser.add_argument("--holdout", type=int, default=48, help="Holdout row count.")
    parser.add_argument("--canary", type=int, default=8, help="Canary row count.")
    parser.add_argument("--seed", type=int, default=47, help="Deterministic seed.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing files.")
    return parser.parse_args()


def _ensure_write(path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")


def _episode_id(split: str, index: int) -> str:
    return f"NCLH-{split.upper()}-{index:04d}"


def _row_id(episode_id: str) -> str:
    return f"{episode_id}-Q001"


def _uid(rng: random.Random) -> str:
    return f"U{rng.randrange(16**6):06X}"


def _pick(items: tuple[str, ...], rng: random.Random, exclude: str | None = None) -> str:
    choices = [x for x in items if x != exclude]
    return rng.choice(choices)


def _identity_case(rng: random.Random) -> tuple[str, str, str, str]:
    char = _pick(_CHARS, rng)
    initial = _pick(_ALIASES, rng)
    rumor = _pick(_ALIASES, rng, exclude=initial)
    final = _pick(_ALIASES, rng, exclude=rumor)
    return f"{char}.codename", initial, rumor, final


def _timeline_case(rng: random.Random) -> tuple[str, str, str, str]:
    event = _pick(("vault.unlock_day", "ferry.depart_day", "hearing.day", "transit.window_day"), rng)
    initial = _pick(_DAYS, rng)
    rumor = _pick(_DAYS, rng, exclude=initial)
    final = _pick(_DAYS, rng, exclude=rumor)
    return event, initial, rumor, final


def _constraint_case(rng: random.Random) -> tuple[str, str, str, str | None]:
    key = _pick(("citadel.rule", "dock.rule", "archive.rule", "reactor.rule"), rng)
    initial = _pick(_RULES, rng)
    rumor = _pick(_RULES, rng, exclude=initial)
    if rng.random() < 0.25:
        return key, initial, rumor, None
    final = _pick(_RULES, rng, exclude=rumor)
    return key, initial, rumor, final


def _noise_lines(*, rng: random.Random, step_start: int, count: int) -> tuple[list[str], list[str]]:
    ledger: list[str] = []
    episode: list[str] = []
    for i in range(count):
        step = step_start + i
        uid = _uid(rng)
        key = rng.choice(_NOISE_KEYS)
        value = f"n{rng.randint(100, 999)}"
        ledger.append(f"- [{uid}] step={step} SET {key} = {value}")
        episode.append(f"- [{uid}] UPDATE step={step} SET {key} = {value}")
    return ledger, episode


def _build_row(*, split: str, index: int, rng: random.Random) -> dict[str, Any]:
    episode_id = _episode_id(split, index)
    row_id = _row_id(episode_id)

    dim = _DIMS[(index - 1) % len(_DIMS)]
    if split == "holdout":
        dim = rng.choice(_DIMS)

    if dim == "identity":
        key, initial, rumor, final = _identity_case(rng)
    elif dim == "timeline":
        key, initial, rumor, final = _timeline_case(rng)
    else:
        key, initial, rumor, final = _constraint_case(rng)

    delayed_dependency = (index % 3) == 0
    repair_transition = (index % 2) == 0
    contradiction_pressure_count = 4 if (index % 4) else 5

    uid_set_initial = _uid(rng)
    uid_note_1 = _uid(rng)
    uid_set_stale = _uid(rng)
    uid_note_2 = _uid(rng)
    uid_note_3 = _uid(rng)
    uid_dependency = _uid(rng)
    uid_repair = _uid(rng)
    uid_final = _uid(rng)

    ledger_lines = [
        f"- [{uid_set_initial}] step=1 SET {key} = {initial}",
        f"- [{uid_note_1}] step=2 NOTE {key} = {rumor}",
    ]
    episode_lines = [
        f"- [{uid_set_initial}] UPDATE step=1 SET {key} = {initial}",
        f"- [{uid_note_1}] UPDATE step=2 NOTE {key} = {rumor}",
    ]

    pre_noise_ledger, pre_noise_episode = _noise_lines(rng=rng, step_start=3, count=4)
    ledger_lines.extend(pre_noise_ledger)
    episode_lines.extend(pre_noise_episode)

    # Retcon pressure: stale authoritative reset.
    ledger_lines.append(f"- [{uid_set_stale}] step=7 SET {key} = {initial}")
    episode_lines.append(f"- [{uid_set_stale}] UPDATE step=7 SET {key} = {initial}")
    ledger_lines.append(f"- [{uid_note_2}] step=8 NOTE {key} = {rumor}")
    episode_lines.append(f"- [{uid_note_2}] UPDATE step=8 NOTE {key} = {rumor}")
    ledger_lines.append(f"- [{uid_note_3}] step=9 NOTE {key} = {initial}")
    episode_lines.append(f"- [{uid_note_3}] UPDATE step=9 NOTE {key} = {initial}")

    if delayed_dependency:
        dep_key = f"{key}.dependency_gate"
        dep_val = "unlock:chapter10"
        ledger_lines.append(f"- [{uid_dependency}] step=10 SET {dep_key} = {dep_val}")
        episode_lines.append(f"- [{uid_dependency}] UPDATE step=10 SET {dep_key} = {dep_val}")
        if repair_transition:
            ledger_lines.append(f"- [{uid_repair}] step=11 SET {key} = {rumor}")
            episode_lines.append(f"- [{uid_repair}] UPDATE step=11 SET {key} = {rumor}")
    else:
        if repair_transition:
            ledger_lines.append(f"- [{uid_repair}] step=10 SET {key} = {rumor}")
            episode_lines.append(f"- [{uid_repair}] UPDATE step=10 SET {key} = {rumor}")

    final_step = 12 if delayed_dependency else 11
    if final is None:
        ledger_lines.append(f"- [{uid_final}] step={final_step} CLEAR {key}")
        episode_lines.append(f"- [{uid_final}] UPDATE step={final_step} CLEAR {key}")
    else:
        ledger_lines.append(f"- [{uid_final}] step={final_step} SET {key} = {final}")
        episode_lines.append(f"- [{uid_final}] UPDATE step={final_step} SET {key} = {final}")

    post_noise_ledger, post_noise_episode = _noise_lines(rng=rng, step_start=13, count=6)
    ledger_lines.extend(post_noise_ledger)
    episode_lines.extend(post_noise_episode)

    callback_gap_steps = final_step - 1
    if final is None:
        expected = None
        expected_text = "null"
    else:
        expected = final
        expected_text = final

    question = (
        f"By the end of Chapter 10, what is the authoritative value for `{key}`? "
        f"Return JSON with keys: value, support_ids. If revoked, set value=null."
    )

    chapters = [
        f"Chapter 1: Registry sets {key} = {initial}.",
        f"Chapter 2: Rumor claims {key} = {rumor}.",
        "Chapter 3: Side-quests add unrelated state updates.",
        "Chapter 4: Investigators revisit old notes and stale snapshots.",
        "Chapter 5: Contradictions increase and confidence drops.",
        "Chapter 6: Team records provisional state that may be stale.",
        "Chapter 7: A stale restatement appears in an official memo.",
        "Chapter 8: Another rumor conflicts with prior steps.",
        "Chapter 9: Transition chapter introduces repair conditions.",
        f"Chapter 10: Canon state resolves with {key} = {expected_text}.",
    ]
    rules = [
        "- State Ledger is authoritative.",
        "- Only latest SET/CLEAR lines define canonical state.",
        "- NOTE lines are non-authoritative and may be contradictory.",
        "- If a repair transition occurs, prefer the final authoritative update.",
    ]
    book = (
        f"# Novel Continuity Long Horizon Episode {episode_id}\n\n"
        "## Reading rules\n"
        + "\n".join(rules)
        + "\n\n## Chapters\n"
        + "\n".join(chapters)
        + "\n\n## State Ledger\n"
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
        "gold": {
            "value": expected,
            "support_ids": [uid_final],
        },
        "meta": {
            "family": "novel_continuity_long_horizon",
            "split": split,
            "case_index": index,
            "dimension": dim,
            "key": key,
            "query_target_type": "null" if expected is None else "value",
            "requires_citation": True,
            "callback_gap_steps": callback_gap_steps,
            "contradiction_pressure_count": contradiction_pressure_count,
            "delayed_dependency": delayed_dependency,
            "repair_transition": repair_transition,
        },
    }


def _build_canary(*, seed: int, case_index: int) -> dict[str, Any]:
    rng = random.Random(seed + 1800 + case_index)
    episode_id = _episode_id("canary", case_index)
    row_id = _row_id(episode_id)
    dim = _DIMS[(case_index - 1) % len(_DIMS)]

    if dim == "identity":
        key, initial, rumor, final = _identity_case(rng)
    elif dim == "timeline":
        key, initial, rumor, final = _timeline_case(rng)
    else:
        key, initial, rumor, final = _constraint_case(rng)
        if final is None:
            final = _pick(_RULES, rng, exclude=rumor)

    values = [initial, rumor, final]
    ledger_lines: list[str] = []
    episode_lines: list[str] = []
    prelatest_uid = ""
    prelatest_value: str | None = None
    for step in range(1, 17):
        uid = _uid(rng)
        if step in (2, 4, 6, 8, 10, 12):
            v = rng.choice(values)
            ledger_lines.append(f"- [{uid}] step={step} NOTE {key} = {v}")
            episode_lines.append(f"- [{uid}] UPDATE step={step} NOTE {key} = {v}")
            continue
        if step in (14,):
            pre = rng.choice([v for v in values if v != final])
            prelatest_uid = uid
            prelatest_value = pre
            ledger_lines.append(f"- [{uid}] step={step} SET {key} = {pre}")
            episode_lines.append(f"- [{uid}] UPDATE step={step} SET {key} = {pre}")
            continue
        if step == 15:
            ledger_lines.append(f"- [{uid}] step={step} SET {key} = {final}")
            episode_lines.append(f"- [{uid}] UPDATE step={step} SET {key} = {final}")
            continue
        v = rng.choice(values)
        ledger_lines.append(f"- [{uid}] step={step} SET {key} = {v}")
        episode_lines.append(f"- [{uid}] UPDATE step={step} SET {key} = {v}")

    noise_ledger, noise_episode = _noise_lines(rng=rng, step_start=20, count=10)
    ledger_lines.extend(noise_ledger)
    episode_lines.extend(noise_episode)

    book = (
        f"# Novel Continuity Long Horizon Episode {episode_id}\n\n"
        "## Reading rules\n"
        "- This canary intentionally stresses long callback and retcon chains.\n"
        "- State Ledger is authoritative.\n"
        "- NOTE lines are decoys.\n\n"
        "## Chapters\n"
        "Chapters contain contradictory narration and delayed repair cues.\n\n"
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
            f"For `{key}`, return the authoritative value immediately before the latest "
            "authoritative update. Return JSON with keys: value, support_ids."
        ),
        "gold": {
            "value": prelatest_value,
            "support_ids": [prelatest_uid] if prelatest_uid else [],
        },
        "meta": {
            "family": "novel_continuity_long_horizon",
            "split": "canary",
            "case_index": case_index,
            "dimension": dim,
            "key": key,
            "expected_fail": True,
            "canary_profile": "long_retcon_prelatest_lookup",
            "callback_gap_steps": 14,
            "contradiction_pressure_count": 6,
            "delayed_dependency": True,
            "repair_transition": True,
        },
    }


def main() -> int:
    ns = _parse_args()
    out_dir = Path(ns.out_dir)
    anchors_path = out_dir / "novel_continuity_long_horizon_anchors.jsonl"
    holdout_path = out_dir / "novel_continuity_long_horizon_holdout.jsonl"
    canary_path = out_dir / "novel_continuity_long_horizon_canary.jsonl"

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

    print("Wrote novel_continuity_long_horizon fixtures:")
    print(f"- {anchors_path}")
    print(f"- {holdout_path}")
    print(f"- {canary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
