from __future__ import annotations

import argparse
import random
from pathlib import Path
from typing import Any

from goldevidencebench.util import write_jsonl

FAMILY_IDS = (
    "index_loss_bounded",
    "reassembly_recoverability",
    "minimal_pointer_set",
    "reconstruction_fidelity",
    "no_invention_expansion",
    "stale_pointer_conflict",
    "wrong_hub_attraction",
    "assembly_order_traps",
    "wrong_address_traps",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate referential_indexing_suite fixtures (anchors/holdout/canary) "
            "covering indexing/reassembly trap families."
        )
    )
    parser.add_argument("--out-dir", default="data/referential_indexing_suite")
    parser.add_argument("--anchors", type=int, default=18)
    parser.add_argument("--holdout", type=int, default=54)
    parser.add_argument("--canary", type=int, default=9)
    parser.add_argument("--seed", type=int, default=211)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _ensure_write(path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")


def _uid(rng: random.Random) -> str:
    return f"U{rng.randrange(16**6):06X}"


def _episode_id(split: str, index: int) -> str:
    return f"RIS-{split.upper()}-{index:04d}"


def _row_id(episode_id: str) -> str:
    return f"{episode_id}-Q001"


def _family_for(split: str, index: int, rng: random.Random) -> str:
    if split == "holdout":
        return rng.choice(FAMILY_IDS)
    return FAMILY_IDS[(index - 1) % len(FAMILY_IDS)]


def _value_pair(rng: random.Random) -> tuple[str, str]:
    a = f"v{rng.randint(100, 999)}"
    b = f"v{rng.randint(100, 999)}"
    while b == a:
        b = f"v{rng.randint(100, 999)}"
    return a, b


def _build_row(*, split: str, index: int, rng: random.Random) -> dict[str, Any]:
    family = _family_for(split, index, rng)
    episode_id = _episode_id(split, index)
    row_id = _row_id(episode_id)

    alpha_old, alpha_new = _value_pair(rng)
    beta_old, beta_new = _value_pair(rng)
    gamma_old, gamma_new = _value_pair(rng)

    uid_a_old = _uid(rng)
    uid_b_old = _uid(rng)
    uid_g_old = _uid(rng)
    uid_a_new = _uid(rng)
    uid_b_new = _uid(rng)
    uid_g_new = _uid(rng)
    uid_a_note = _uid(rng)

    key_alpha = "part.alpha"
    key_beta = "part.beta"
    key_gamma = "part.gamma"

    ledger = [
        f"- [{uid_a_old}] step=1 SET {key_alpha} = {alpha_old}",
        f"- [{uid_b_old}] step=2 SET {key_beta} = {beta_old}",
        f"- [{uid_g_old}] step=3 SET {key_gamma} = {gamma_old}",
        f"- [{uid_a_note}] step=4 NOTE {key_alpha} = {alpha_old}",
        f"- [{uid_a_new}] step=5 SET {key_alpha} = {alpha_new}",
        f"- [{uid_b_new}] step=6 SET {key_beta} = {beta_new}",
        f"- [{uid_g_new}] step=7 SET {key_gamma} = {gamma_new}",
    ]
    episode = [line.replace(" step=", " UPDATE step=") for line in ledger]

    for step in range(8, 15):
        uid = _uid(rng)
        noise_key = f"noise.metric_{step}"
        noise_val = f"n{rng.randint(1000, 9999)}"
        ledger.append(f"- [{uid}] step={step} NOTE {noise_key} = {noise_val}")
        episode.append(f"- [{uid}] UPDATE step={step} NOTE {noise_key} = {noise_val}")

    support_ids: list[str]
    value: Any
    stale_value = alpha_old
    lookup_depth_target = rng.randint(1, 4)
    query_target_type = "value"

    if family == "index_loss_bounded":
        question = (
            "For key `part.alpha`, return the latest authoritative value. "
            "Return JSON with keys: value, support_ids, lookup_depth."
        )
        value = alpha_new
        support_ids = [uid_a_new]
    elif family == "reassembly_recoverability":
        if split == "canary":
            question = (
                "Reassemble the tuple `part.alpha|part.beta|part.gamma` using latest authoritative values. "
                "Return JSON with keys: value, support_ids, lookup_depth."
            )
            value = f"{alpha_new}|{beta_new}|{gamma_new}"
            support_ids = [uid_a_new, uid_b_new, uid_g_new]
        else:
            uid_resolved = _uid(rng)
            resolved_value = f"{alpha_new}|{beta_new}|{gamma_new}"
            ledger.append(f"- [{uid_resolved}] step=15 SET resolved.bundle = {resolved_value}")
            episode.append(f"- [{uid_resolved}] UPDATE step=15 SET resolved.bundle = {resolved_value}")
            question = (
                "Return latest authoritative value for `resolved.bundle` "
                "(the reassembled `part.alpha|part.beta|part.gamma` tuple). "
                "Return JSON with keys: value, support_ids, lookup_depth."
            )
            value = resolved_value
            support_ids = [uid_resolved]
    elif family == "minimal_pointer_set":
        if split == "canary":
            question = (
                "Return the latest value for `part.beta` with the minimum sufficient pointer set. "
                "Return JSON with keys: value, support_ids, pointer_set_size, lookup_depth."
            )
            value = beta_new
            support_ids = [uid_b_new]
        else:
            uid_resolved = _uid(rng)
            ledger.append(f"- [{uid_resolved}] step=15 SET resolved.part.beta = {beta_new}")
            episode.append(f"- [{uid_resolved}] UPDATE step=15 SET resolved.part.beta = {beta_new}")
            question = (
                "Return latest authoritative value for `resolved.part.beta` "
                "(minimal pointer-set result). "
                "Return JSON with keys: value, support_ids, pointer_set_size, lookup_depth."
            )
            value = beta_new
            support_ids = [uid_resolved]
    elif family == "reconstruction_fidelity":
        if split == "canary":
            question = (
                "Reconstruct `alpha=<...>;beta=<...>` from latest authoritative values only. "
                "Return JSON with keys: value, support_ids, lookup_depth."
            )
            value = f"alpha={alpha_new};beta={beta_new}"
            support_ids = [uid_a_new, uid_b_new]
        else:
            uid_resolved = _uid(rng)
            resolved_value = f"alpha={alpha_new};beta={beta_new}"
            ledger.append(f"- [{uid_resolved}] step=15 SET resolved.alpha_beta = {resolved_value}")
            episode.append(f"- [{uid_resolved}] UPDATE step=15 SET resolved.alpha_beta = {resolved_value}")
            question = (
                "Return latest authoritative value for `resolved.alpha_beta` "
                "(reconstruction fidelity output). "
                "Return JSON with keys: value, support_ids, lookup_depth."
            )
            value = resolved_value
            support_ids = [uid_resolved]
    elif family == "no_invention_expansion":
        question = (
            "What is the latest value for `part.delta`? If absent, return null. "
            "Do not invent values. Return JSON with keys: value, support_ids, lookup_depth."
        )
        value = None
        support_ids = []
        query_target_type = "null"
    elif family == "stale_pointer_conflict":
        question = (
            "A stale snapshot says `part.alpha` was old. Return the latest authoritative `part.alpha`. "
            "Return JSON with keys: value, support_ids, lookup_depth."
        )
        value = alpha_new
        support_ids = [uid_a_new]
    elif family == "wrong_hub_attraction":
        hub_uid = _uid(rng)
        hub_key = "hub.popular"
        hub_val = alpha_old
        ledger.append(f"- [{hub_uid}] step=16 SET {hub_key} = {hub_val}")
        episode.append(f"- [{hub_uid}] UPDATE step=16 SET {hub_key} = {hub_val}")
        question = (
            "Do not be distracted by high-frequency hub keys. Return latest `part.alpha`. "
            "Return JSON with keys: value, support_ids, lookup_depth."
        )
        value = alpha_new
        support_ids = [uid_a_new]
    elif family == "assembly_order_traps":
        u1 = _uid(rng)
        u2 = _uid(rng)
        u3 = _uid(rng)
        s1 = f"s{rng.randint(1,9)}"
        s2 = f"s{rng.randint(1,9)}"
        s3 = f"s{rng.randint(1,9)}"
        base_lines = [
            f"- [{u1}] step=17 SET seq.step1 = {s1}",
            f"- [{u2}] step=18 SET seq.step2 = {s2}",
            f"- [{u3}] step=19 SET seq.step3 = {s3}",
        ]
        ledger.extend(base_lines)
        episode.extend([line.replace(" step=", " UPDATE step=") for line in base_lines])
        if split == "canary":
            question = (
                "Reassemble execution order as `step1>step2>step3` from authoritative entries. "
                "Return JSON with keys: value, support_ids, lookup_depth."
            )
            value = f"{s1}>{s2}>{s3}"
            support_ids = [u1, u2, u3]
        else:
            u4 = _uid(rng)
            resolved_value = f"{s1}>{s2}>{s3}"
            ledger.append(f"- [{u4}] step=20 SET resolved.seq = {resolved_value}")
            episode.append(f"- [{u4}] UPDATE step=20 SET resolved.seq = {resolved_value}")
            question = (
                "Return latest authoritative value for `resolved.seq` "
                "(execution order `step1>step2>step3`). "
                "Return JSON with keys: value, support_ids, lookup_depth."
            )
            value = resolved_value
            support_ids = [u4]
    else:  # wrong_address_traps
        ua = _uid(rng)
        ub = _uid(rng)
        a1 = f"addr-{rng.randint(1000,1999)}"
        a2 = f"addr-{rng.randint(2000,2999)}"
        ledger.extend(
            [
                f"- [{ua}] step=20 SET address.user_001 = {a1}",
                f"- [{ub}] step=21 SET address.user_010 = {a2}",
            ]
        )
        episode.extend(
            [
                f"- [{ua}] UPDATE step=20 SET address.user_001 = {a1}",
                f"- [{ub}] UPDATE step=21 SET address.user_010 = {a2}",
            ]
        )
        question = (
            "Return latest authoritative value for `address.user_010` (not `address.user_001`). "
            "Return JSON with keys: value, support_ids, lookup_depth."
        )
        value = a2
        support_ids = [ub]

    book = (
        f"# Referential Indexing Episode {episode_id}\n\n"
        "## Rules\n"
        "- State Ledger is authoritative.\n"
        "- NOTE lines are non-authoritative.\n"
        "- Prefer latest authoritative pointers.\n\n"
        "## State Ledger\n"
        + "\n".join(ledger)
    )
    document = f"# Episode Log {episode_id}\n\n" + "\n".join(episode)

    return {
        "id": row_id,
        "episode_id": episode_id,
        "schema_version": "0.1",
        "document": document,
        "book": book,
        "question": question,
        "gold": {"value": value, "support_ids": support_ids},
        "meta": {
            "family": "referential_indexing_suite",
            "family_id": family,
            "split": split,
            "case_index": index,
            "query_target_type": query_target_type,
            "stale_value": stale_value,
            "lookup_depth_target": lookup_depth_target,
            "all_support_ids": [uid_a_old, uid_b_old, uid_g_old, uid_a_new, uid_b_new, uid_g_new, uid_a_note],
            "expected_fail": split == "canary",
        },
    }


def main() -> int:
    ns = _parse_args()
    out_dir = Path(ns.out_dir)
    anchors_path = out_dir / "referential_indexing_suite_anchors.jsonl"
    holdout_path = out_dir / "referential_indexing_suite_holdout.jsonl"
    canary_path = out_dir / "referential_indexing_suite_canary.jsonl"

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
    canary = [_build_row(split="canary", index=i + 1, rng=rng) for i in range(ns.canary)]

    write_jsonl(anchors_path, anchors)
    write_jsonl(holdout_path, holdout)
    write_jsonl(canary_path, canary)

    print("Wrote referential_indexing_suite fixtures:")
    print(f"- {anchors_path}")
    print(f"- {holdout_path}")
    print(f"- {canary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
