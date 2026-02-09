from __future__ import annotations

import argparse
import random
from pathlib import Path
from typing import Any

from goldevidencebench.util import write_jsonl


_PROFILES = ("entry", "horizon", "recovery", "counterfactual")
_LOCAL_ACTIONS = (
    "rush_gate",
    "shortcut_lane",
    "loud_probe",
    "single_path_commit",
)
_GLOBAL_ACTIONS = (
    "secure_bridge",
    "safe_route",
    "staged_probe",
    "parallel_plan",
)
_RECOVERY_ACTIONS = (
    "cut_losses",
    "rollback_then_verify",
    "switch_to_safe_route",
    "checkpoint_restore",
)
_RECOVERY_CODES = {
    "cut_losses": "REC_CUT",
    "rollback_then_verify": "REC_ROLLBACK",
    "switch_to_safe_route": "REC_SWITCH",
    "checkpoint_restore": "REC_CHECKPOINT",
}
_NOISE_KEYS = (
    "sensor.drift",
    "queue.depth",
    "supply.batch",
    "weather.front",
    "watcher.alert",
    "ticket.channel",
)


def _json_value_support_question(*, key: str, allowed_values: tuple[str, ...] | None = None) -> str:
    allowed_clause = ""
    if allowed_values:
        allowed_clause = " Allowed values: " + ", ".join(allowed_values) + "."
    return (
        f"Return latest authoritative value for `{key}` from the State Ledger."
        f"{allowed_clause} Return strict JSON object with keys `value` and `support_ids` only."
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate myopic_planning_traps fixtures (anchors/holdout/canary) "
            "for deterministic long-horizon planning traps."
        )
    )
    parser.add_argument("--out-dir", default="data/myopic_planning_traps", help="Output directory.")
    parser.add_argument("--anchors", type=int, default=16, help="Anchor row count.")
    parser.add_argument("--holdout", type=int, default=48, help="Holdout row count.")
    parser.add_argument("--canary", type=int, default=8, help="Canary row count.")
    parser.add_argument("--seed", type=int, default=83, help="Deterministic RNG seed.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing files.")
    return parser.parse_args()


def _ensure_write(path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")


def _episode_id(split: str, index: int) -> str:
    return f"MPT-{split.upper()}-{index:04d}"


def _row_id(episode_id: str) -> str:
    return f"{episode_id}-Q001"


def _uid(rng: random.Random) -> str:
    return f"U{rng.randrange(16**6):06X}"


def _noise_lines(*, rng: random.Random, step_start: int, count: int) -> tuple[list[str], list[str]]:
    ledger: list[str] = []
    episode: list[str] = []
    for i in range(count):
        step = step_start + i
        uid = _uid(rng)
        key = rng.choice(_NOISE_KEYS)
        value = f"n{rng.randint(100, 999)}"
        ledger.append(f"- [{uid}] step={step} NOTE {key} = {value}")
        episode.append(f"- [{uid}] UPDATE step={step} NOTE {key} = {value}")
    return ledger, episode


def _profile_for(*, split: str, index: int, rng: random.Random) -> str:
    if split == "holdout":
        return rng.choice(_PROFILES)
    return _PROFILES[(index - 1) % len(_PROFILES)]


def _build_row(*, split: str, index: int, rng: random.Random) -> dict[str, Any]:
    episode_id = _episode_id(split, index)
    row_id = _row_id(episode_id)

    profile = _profile_for(split=split, index=index, rng=rng)
    local_action = rng.choice(_LOCAL_ACTIONS)
    global_action = rng.choice(_GLOBAL_ACTIONS)
    while global_action == local_action:
        global_action = rng.choice(_GLOBAL_ACTIONS)
    recovery_action = rng.choice(_RECOVERY_ACTIONS)
    recovery_code = _RECOVERY_CODES[recovery_action]

    horizon_steps = rng.choice((3, 4, 5))
    local_total = rng.randint(-4, 1)
    global_total = local_total + rng.randint(4, 9)
    local_recovery_total = local_total + rng.randint(2, 5)
    if local_recovery_total >= global_total:
        local_recovery_total = global_total - 1

    uid_local_action = _uid(rng)
    uid_global_action = _uid(rng)
    uid_local_total = _uid(rng)
    uid_global_total = _uid(rng)
    uid_recovery_action = _uid(rng)
    uid_recovery_total = _uid(rng)

    ledger_lines = [
        f"- [{uid_local_action}] step=1 SET plan.local_first = {local_action}",
        f"- [{uid_global_action}] step=2 SET plan.global_first = {global_action}",
        f"- [{uid_local_total}] step=3 SET reward.total_if_local = {local_total}",
        f"- [{uid_global_total}] step=4 SET reward.total_if_global = {global_total}",
        f"- [{uid_recovery_action}] step=5 SET plan.recovery_after_local = {recovery_action}",
        f"- [{uid_recovery_total}] step=6 SET reward.total_if_local_with_recovery = {local_recovery_total}",
    ]
    episode_lines = [
        f"- [{uid_local_action}] UPDATE step=1 SET plan.local_first = {local_action}",
        f"- [{uid_global_action}] UPDATE step=2 SET plan.global_first = {global_action}",
        f"- [{uid_local_total}] UPDATE step=3 SET reward.total_if_local = {local_total}",
        f"- [{uid_global_total}] UPDATE step=4 SET reward.total_if_global = {global_total}",
        f"- [{uid_recovery_action}] UPDATE step=5 SET plan.recovery_after_local = {recovery_action}",
        f"- [{uid_recovery_total}] UPDATE step=6 SET reward.total_if_local_with_recovery = {local_recovery_total}",
    ]

    noise_ledger, noise_episode = _noise_lines(rng=rng, step_start=7, count=6)
    ledger_lines.extend(noise_ledger)
    episode_lines.extend(noise_episode)

    # Derived decision keys keep the planning signal explicit while making the
    # authoritative output field deterministic for scoring/citation.
    uid_entry_first = _uid(rng)
    uid_horizon_first = _uid(rng)
    uid_best_recovery = _uid(rng)
    uid_best_recovery_code = _uid(rng)
    uid_counterfactual_local = _uid(rng)
    counterfactual_total: int = local_total
    ledger_lines.extend(
        [
            f"- [{uid_entry_first}] step=13 SET decision.entry_first_action = {global_action}",
            f"- [{uid_horizon_first}] step=14 SET decision.horizon_first_action = {global_action}",
            f"- [{uid_best_recovery}] step=15 SET decision.best_recovery_action = {recovery_action}",
            f"- [{uid_counterfactual_local}] step=16 SET decision.counterfactual_local_total = {counterfactual_total}",
            f"- [{uid_best_recovery_code}] step=17 SET decision.best_recovery_code = {recovery_code}",
        ]
    )
    episode_lines.extend(
        [
            f"- [{uid_entry_first}] UPDATE step=13 SET decision.entry_first_action = {global_action}",
            f"- [{uid_horizon_first}] UPDATE step=14 SET decision.horizon_first_action = {global_action}",
            f"- [{uid_best_recovery}] UPDATE step=15 SET decision.best_recovery_action = {recovery_action}",
            f"- [{uid_counterfactual_local}] UPDATE step=16 SET decision.counterfactual_local_total = {counterfactual_total}",
            f"- [{uid_best_recovery_code}] UPDATE step=17 SET decision.best_recovery_code = {recovery_code}",
        ]
    )

    if profile == "entry":
        query_key = "decision.entry_first_action"
        question = _json_value_support_question(
            key=query_key,
            allowed_values=_GLOBAL_ACTIONS,
        )
        gold_value: Any = global_action
        support_ids = [uid_entry_first]
    elif profile == "horizon":
        query_key = "decision.horizon_first_action"
        question = _json_value_support_question(
            key=query_key,
            allowed_values=_GLOBAL_ACTIONS,
        )
        gold_value = global_action
        support_ids = [uid_horizon_first]
    elif profile == "recovery":
        query_key = "decision.best_recovery_code"
        question = _json_value_support_question(
            key=query_key,
            allowed_values=tuple(_RECOVERY_CODES.values()),
        )
        gold_value = recovery_code
        support_ids = [uid_best_recovery_code]
    else:
        query_key = "decision.counterfactual_local_total"
        question = _json_value_support_question(key=query_key)
        gold_value = counterfactual_total
        support_ids = [uid_counterfactual_local]

    rules = [
        "- State Ledger is authoritative.",
        "- Optimize final reward, not immediate reward.",
        "- NOTE lines are non-authoritative distractors.",
        "- Recovery questions assume local-first already happened.",
    ]
    chapters = [
        "Phase 1: two plausible first actions are presented.",
        "Phase 2: immediate outcomes look attractive for the local action.",
        "Phase 3: long-horizon totals reveal local action is worse.",
        "Phase 4: recovery option exists but does not beat global-first path.",
    ]

    book = (
        f"# Myopic Planning Episode {episode_id}\n\n"
        "## Rules\n"
        + "\n".join(rules)
        + "\n\n## Narrative\n"
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
            "value": gold_value,
            "support_ids": support_ids,
        },
        "meta": {
            "family": "myopic_planning_traps",
            "split": split,
            "case_index": index,
            "key": query_key,
            "profile": profile,
            "horizon_steps": horizon_steps,
            "local_action": local_action,
            "global_action": global_action,
            "recovery_action": recovery_action,
            "local_total": local_total,
            "global_total": global_total,
            "local_recovery_total": local_recovery_total,
            "requires_citation": True,
        },
    }


def _build_canary(*, seed: int, case_index: int) -> dict[str, Any]:
    rng = random.Random(seed + 2200 + case_index)
    episode_id = _episode_id("canary", case_index)
    row_id = _row_id(episode_id)

    local_action = rng.choice(_LOCAL_ACTIONS)
    global_action = rng.choice(_GLOBAL_ACTIONS)
    recovery_action = rng.choice(_RECOVERY_ACTIONS)
    horizon_steps = 6

    uid_local = _uid(rng)
    uid_global = _uid(rng)
    uid_local_total = _uid(rng)
    uid_global_total = _uid(rng)

    local_total = rng.randint(-6, -2)
    global_total = local_total + rng.randint(8, 14)

    ledger_lines = [
        f"- [{uid_local}] step=1 SET plan.local_first = {local_action}",
        f"- [{uid_global}] step=2 SET plan.global_first = {global_action}",
        f"- [{uid_local_total}] step=3 SET reward.total_if_local = {local_total}",
        f"- [{uid_global_total}] step=4 SET reward.total_if_global = {global_total}",
    ]
    episode_lines = [
        f"- [{uid_local}] UPDATE step=1 SET plan.local_first = {local_action}",
        f"- [{uid_global}] UPDATE step=2 SET plan.global_first = {global_action}",
        f"- [{uid_local_total}] UPDATE step=3 SET reward.total_if_local = {local_total}",
        f"- [{uid_global_total}] UPDATE step=4 SET reward.total_if_global = {global_total}",
    ]

    for i in range(14):
        uid = _uid(rng)
        decoy_value = rng.choice((local_action, global_action, recovery_action))
        step = 5 + i
        ledger_lines.append(f"- [{uid}] step={step} NOTE plan.decoy = {decoy_value}")
        episode_lines.append(f"- [{uid}] UPDATE step={step} NOTE plan.decoy = {decoy_value}")

    book = (
        f"# Myopic Planning Episode {episode_id}\n\n"
        "## Rules\n"
        "- This canary is intentionally adversarial.\n"
        "- Optimize final reward across full horizon.\n"
        "- NOTE lines are non-authoritative decoys.\n\n"
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
            "Return the first action that optimizes final reward, then also include the second-best action "
            "in value as `best|second_best` (JSON with value, support_ids)."
        ),
        "gold": {
            "value": f"{global_action}|{recovery_action}",
            "support_ids": [uid_global_total],
        },
        "meta": {
            "family": "myopic_planning_traps",
            "split": "canary",
            "case_index": case_index,
            "profile": "adversarial_dual_output",
            "horizon_steps": horizon_steps,
            "local_action": local_action,
            "global_action": global_action,
            "recovery_action": recovery_action,
            "expected_fail": True,
            "canary_profile": "dual_output_adversarial",
            "requires_citation": True,
        },
    }


def main() -> int:
    ns = _parse_args()
    out_dir = Path(ns.out_dir)
    anchors_path = out_dir / "myopic_planning_traps_anchors.jsonl"
    holdout_path = out_dir / "myopic_planning_traps_holdout.jsonl"
    canary_path = out_dir / "myopic_planning_traps_canary.jsonl"

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

    print("Wrote myopic_planning_traps fixtures:")
    print(f"- {anchors_path}")
    print(f"- {holdout_path}")
    print(f"- {canary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
