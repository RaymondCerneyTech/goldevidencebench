from __future__ import annotations

import argparse
import random
from pathlib import Path
from typing import Any

from goldevidencebench.util import write_jsonl

_FAMILIES = ("rpa_mode_switch", "intent_spec_layer", "noise_escalation")
_FAMILY_OUT_DIR = {
    "rpa_mode_switch": "data/rpa_mode_switch",
    "intent_spec_layer": "data/intent_spec_layer",
    "noise_escalation": "data/noise_escalation",
}
_NOISE_KEYS = (
    "sensor.drift",
    "queue.depth",
    "memory.cache",
    "authority.conflict",
    "intent.ambiguity",
    "signal.latency",
)

_RPA_SCENARIOS = (
    {
        "profile": "authority_conflict",
        "uncertainty": "medium",
        "horizon_depth": 3,
        "reversibility": "reversible",
        "authority_conflict": True,
    },
    {
        "profile": "high_horizon_uncertain",
        "uncertainty": "high",
        "horizon_depth": 5,
        "reversibility": "reversible",
        "authority_conflict": False,
    },
    {
        "profile": "irreversible_verify",
        "uncertainty": "medium",
        "horizon_depth": 3,
        "reversibility": "irreversible",
        "authority_conflict": False,
    },
    {
        "profile": "uncertain_ask",
        "uncertainty": "high",
        "horizon_depth": 2,
        "reversibility": "reversible",
        "authority_conflict": False,
    },
    {
        "profile": "straightforward_act",
        "uncertainty": "low",
        "horizon_depth": 2,
        "reversibility": "reversible",
        "authority_conflict": False,
    },
)

_INTENT_SCENARIOS = (
    {
        "profile": "ambiguous_budget",
        "ambiguous": True,
        "required_fields": ["budget", "deadline"],
        "next_action": "ask",
        "downstream_error_if_guess": 0.90,
    },
    {
        "profile": "ambiguous_risk",
        "ambiguous": True,
        "required_fields": ["risk_tolerance", "failure_policy"],
        "next_action": "ask",
        "downstream_error_if_guess": 0.85,
    },
    {
        "profile": "clear_request",
        "ambiguous": False,
        "required_fields": [],
        "next_action": "answer",
        "downstream_error_if_guess": 0.10,
    },
    {
        "profile": "clear_constrained",
        "ambiguous": False,
        "required_fields": [],
        "next_action": "answer",
        "downstream_error_if_guess": 0.05,
    },
    {
        "profile": "conflicting_preferences",
        "ambiguous": True,
        "required_fields": ["priority_order"],
        "next_action": "ask",
        "downstream_error_if_guess": 0.80,
    },
)

_NOISE_SCENARIOS = (
    {
        "profile": "recoverable_early",
        "target_action": "verify",
        "target_noise_slope": 0.14,
        "target_recovery_latency": 2.0,
        "irrecoverable_if_missed": False,
    },
    {
        "profile": "recoverable_late",
        "target_action": "retrieve",
        "target_noise_slope": 0.19,
        "target_recovery_latency": 2.5,
        "irrecoverable_if_missed": False,
    },
    {
        "profile": "irrecoverable_guard",
        "target_action": "rollback",
        "target_noise_slope": 0.10,
        "target_recovery_latency": 1.0,
        "irrecoverable_if_missed": True,
    },
    {
        "profile": "steady_state_continue",
        "target_action": "continue",
        "target_noise_slope": 0.06,
        "target_recovery_latency": 1.0,
        "irrecoverable_if_missed": False,
    },
    {
        "profile": "pause_then_verify",
        "target_action": "verify",
        "target_noise_slope": 0.12,
        "target_recovery_latency": 1.5,
        "irrecoverable_if_missed": False,
    },
)


def _parse_args(argv: list[str] | None = None, *, forced_family: str | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate deterministic fixtures for control-layer scaffold families."
    )
    if forced_family is None:
        parser.add_argument("--family", choices=_FAMILIES, required=True)
    else:
        parser.add_argument("--family", choices=_FAMILIES, default=forced_family)
    parser.add_argument("--out-dir", default="", help="Output directory (defaults per family).")
    parser.add_argument("--anchors", type=int, default=18, help="Anchor row count.")
    parser.add_argument("--holdout", type=int, default=54, help="Holdout row count.")
    parser.add_argument("--canary", type=int, default=9, help="Canary row count.")
    parser.add_argument("--seed", type=int, default=307, help="Deterministic RNG seed.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing files.")
    ns = parser.parse_args(argv)
    if not ns.out_dir:
        ns.out_dir = _FAMILY_OUT_DIR[ns.family]
    return ns


def _ensure_write(path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")


def _uid(rng: random.Random) -> str:
    return f"U{rng.randrange(16**6):06X}"


def _episode_id(family: str, split: str, index: int) -> str:
    prefix = {
        "rpa_mode_switch": "RPA",
        "intent_spec_layer": "INT",
        "noise_escalation": "NSE",
    }[family]
    return f"{prefix}-{split.upper()}-{index:04d}"


def _row_id(episode_id: str) -> str:
    return f"{episode_id}-Q001"


def _json_question(key: str, allowed_values: tuple[str, ...] | None = None) -> str:
    allowed_clause = ""
    if allowed_values:
        allowed_clause = " Allowed values: " + ", ".join(allowed_values) + "."
    return (
        f"Return latest authoritative value for `{key}` from the State Ledger."
        f"{allowed_clause} Return strict JSON object with keys `value` and `support_ids` only."
    )


def _scenario_pick(scenarios: tuple[dict[str, Any], ...], *, split: str, index: int, rng: random.Random) -> dict[str, Any]:
    if split == "holdout":
        return dict(rng.choice(scenarios))
    return dict(scenarios[(index - 1) % len(scenarios)])


def _noise_lines(rng: random.Random, start_step: int, count: int) -> tuple[list[str], list[str]]:
    ledger: list[str] = []
    episode: list[str] = []
    for i in range(count):
        step = start_step + i
        uid = _uid(rng)
        key = rng.choice(_NOISE_KEYS)
        value = f"n{rng.randint(100, 999)}"
        ledger.append(f"- [{uid}] step={step} NOTE {key} = {value}")
        episode.append(f"- [{uid}] UPDATE step={step} NOTE {key} = {value}")
    return ledger, episode


def _rpa_policy(*, uncertainty: str, horizon_depth: int, reversibility: str, authority_conflict: bool) -> tuple[str, str]:
    if authority_conflict:
        return "reason", "retrieve"
    if uncertainty == "high" and horizon_depth >= 4:
        return "plan", "verify"
    if reversibility == "irreversible" and uncertainty in ("medium", "high"):
        return "plan", "verify"
    if uncertainty == "high":
        return "reason", "ask"
    return "act", "answer"


def _build_rpa_row(*, split: str, index: int, rng: random.Random) -> dict[str, Any]:
    scenario = _scenario_pick(_RPA_SCENARIOS, split=split, index=index, rng=rng)
    uncertainty = str(scenario["uncertainty"])
    horizon_depth = int(scenario["horizon_depth"])
    reversibility = str(scenario["reversibility"])
    authority_conflict = bool(scenario["authority_conflict"])

    mode, decision = _rpa_policy(
        uncertainty=uncertainty,
        horizon_depth=horizon_depth,
        reversibility=reversibility,
        authority_conflict=authority_conflict,
    )
    contract = f"{mode}|{decision}"
    episode_id = _episode_id("rpa_mode_switch", split, index)

    uid_unc = _uid(rng)
    uid_h = _uid(rng)
    uid_rev = _uid(rng)
    uid_auth = _uid(rng)
    uid_mode = _uid(rng)
    uid_decision = _uid(rng)
    uid_contract = _uid(rng)

    ledger = [
        f"- [{uid_unc}] step=1 SET signal.uncertainty = {uncertainty}",
        f"- [{uid_h}] step=2 SET signal.horizon_depth = {horizon_depth}",
        f"- [{uid_rev}] step=3 SET signal.reversibility = {reversibility}",
        f"- [{uid_auth}] step=4 SET signal.authority_conflict = {str(authority_conflict).lower()}",
        f"- [{uid_mode}] step=5 SET policy.next_mode = {mode}",
        f"- [{uid_decision}] step=6 SET policy.next_decision = {decision}",
        f"- [{uid_contract}] step=7 SET policy.next_contract = {contract}",
    ]
    episode = [
        f"- [{uid_unc}] UPDATE step=1 SET signal.uncertainty = {uncertainty}",
        f"- [{uid_h}] UPDATE step=2 SET signal.horizon_depth = {horizon_depth}",
        f"- [{uid_rev}] UPDATE step=3 SET signal.reversibility = {reversibility}",
        f"- [{uid_auth}] UPDATE step=4 SET signal.authority_conflict = {str(authority_conflict).lower()}",
        f"- [{uid_mode}] UPDATE step=5 SET policy.next_mode = {mode}",
        f"- [{uid_decision}] UPDATE step=6 SET policy.next_decision = {decision}",
        f"- [{uid_contract}] UPDATE step=7 SET policy.next_contract = {contract}",
    ]
    noise_ledger, noise_episode = _noise_lines(rng, 8, 6)
    ledger.extend(noise_ledger)
    episode.extend(noise_episode)

    return {
        "id": _row_id(episode_id),
        "episode_id": episode_id,
        "schema_version": "0.1",
        "document": f"# RPA Episode {episode_id}\n\n" + "\n".join(episode),
        "book": (
            f"# RPA Episode {episode_id}\n\n"
            "## Rules\n"
            "- Switch modes based on uncertainty, horizon depth, and reversibility.\n"
            "- Authority conflict forces retrieval.\n"
            "- NOTE lines are non-authoritative distractors.\n\n"
            "## State Ledger\n"
            + "\n".join(ledger)
        ),
        "question": _json_question(
            "policy.next_contract",
            allowed_values=(
                "reason|retrieve",
                "reason|ask",
                "plan|verify",
                "act|answer",
            ),
        ),
        "gold": {"value": contract, "support_ids": [uid_contract]},
        "meta": {
            "family": "rpa_mode_switch",
            "split": split,
            "case_index": index,
            "profile": scenario["profile"],
            "uncertainty": uncertainty,
            "horizon_depth": horizon_depth,
            "reversibility": reversibility,
            "authority_conflict": authority_conflict,
            "gold_mode": mode,
            "gold_decision": decision,
            "requires_plan": mode == "plan",
            "act_allowed": mode == "act" and decision == "answer",
            "requires_citation": True,
        },
    }


def _build_intent_row(*, split: str, index: int, rng: random.Random) -> dict[str, Any]:
    scenario = _scenario_pick(_INTENT_SCENARIOS, split=split, index=index, rng=rng)
    next_action = str(scenario["next_action"])
    required_fields = list(scenario["required_fields"])
    ambiguous = bool(scenario["ambiguous"])
    error_if_guess = float(scenario["downstream_error_if_guess"])
    episode_id = _episode_id("intent_spec_layer", split, index)

    uid_request = _uid(rng)
    uid_ambiguous = _uid(rng)
    uid_required = _uid(rng)
    uid_action = _uid(rng)

    required_serialized = ",".join(required_fields) if required_fields else "none"
    ledger = [
        f"- [{uid_request}] step=1 SET intent.request_profile = {scenario['profile']}",
        f"- [{uid_ambiguous}] step=2 SET intent.is_ambiguous = {str(ambiguous).lower()}",
        f"- [{uid_required}] step=3 SET intent.required_fields = {required_serialized}",
        f"- [{uid_action}] step=4 SET intent.next_action = {next_action}",
    ]
    episode = [
        f"- [{uid_request}] UPDATE step=1 SET intent.request_profile = {scenario['profile']}",
        f"- [{uid_ambiguous}] UPDATE step=2 SET intent.is_ambiguous = {str(ambiguous).lower()}",
        f"- [{uid_required}] UPDATE step=3 SET intent.required_fields = {required_serialized}",
        f"- [{uid_action}] UPDATE step=4 SET intent.next_action = {next_action}",
    ]
    noise_ledger, noise_episode = _noise_lines(rng, 5, 5)
    ledger.extend(noise_ledger)
    episode.extend(noise_episode)

    return {
        "id": _row_id(episode_id),
        "episode_id": episode_id,
        "schema_version": "0.1",
        "document": f"# Intent Episode {episode_id}\n\n" + "\n".join(episode),
        "book": (
            f"# Intent Episode {episode_id}\n\n"
            "## Rules\n"
            "- If intent is ambiguous, ask before acting.\n"
            "- If intent is sufficiently specified, answer directly.\n"
            "- NOTE lines are non-authoritative distractors.\n\n"
            "## State Ledger\n"
            + "\n".join(ledger)
        ),
        "question": _json_question("intent.next_action", allowed_values=("ask", "answer")),
        "gold": {"value": next_action, "support_ids": [uid_action]},
        "meta": {
            "family": "intent_spec_layer",
            "split": split,
            "case_index": index,
            "profile": scenario["profile"],
            "ambiguous": ambiguous,
            "required_fields": required_fields,
            "downstream_error_if_guess": error_if_guess,
            "requires_citation": True,
        },
    }


def _build_noise_row(*, split: str, index: int, rng: random.Random) -> dict[str, Any]:
    scenario = _scenario_pick(_NOISE_SCENARIOS, split=split, index=index, rng=rng)
    target_action = str(scenario["target_action"])
    slope = float(scenario["target_noise_slope"])
    latency = float(scenario["target_recovery_latency"])
    irrecoverable = bool(scenario["irrecoverable_if_missed"])
    episode_id = _episode_id("noise_escalation", split, index)

    uid_slope = _uid(rng)
    uid_latency = _uid(rng)
    uid_irrec = _uid(rng)
    uid_action = _uid(rng)

    ledger = [
        f"- [{uid_slope}] step=1 SET noise.target_slope = {slope:.2f}",
        f"- [{uid_latency}] step=2 SET noise.target_recovery_latency = {latency:.2f}",
        f"- [{uid_irrec}] step=3 SET noise.irrecoverable_if_missed = {str(irrecoverable).lower()}",
        f"- [{uid_action}] step=4 SET control.next_action = {target_action}",
    ]
    episode = [
        f"- [{uid_slope}] UPDATE step=1 SET noise.target_slope = {slope:.2f}",
        f"- [{uid_latency}] UPDATE step=2 SET noise.target_recovery_latency = {latency:.2f}",
        f"- [{uid_irrec}] UPDATE step=3 SET noise.irrecoverable_if_missed = {str(irrecoverable).lower()}",
        f"- [{uid_action}] UPDATE step=4 SET control.next_action = {target_action}",
    ]
    noise_ledger, noise_episode = _noise_lines(rng, 5, 5)
    ledger.extend(noise_ledger)
    episode.extend(noise_episode)

    return {
        "id": _row_id(episode_id),
        "episode_id": episode_id,
        "schema_version": "0.1",
        "document": f"# Noise Episode {episode_id}\n\n" + "\n".join(episode),
        "book": (
            f"# Noise Episode {episode_id}\n\n"
            "## Rules\n"
            "- Choose control action that bounds compounding noise.\n"
            "- Prefer rollback/verify when irreversible drift risk is high.\n"
            "- NOTE lines are non-authoritative distractors.\n\n"
            "## State Ledger\n"
            + "\n".join(ledger)
        ),
        "question": _json_question(
            "control.next_action",
            allowed_values=("verify", "retrieve", "rollback", "continue"),
        ),
        "gold": {"value": target_action, "support_ids": [uid_action]},
        "meta": {
            "family": "noise_escalation",
            "split": split,
            "case_index": index,
            "profile": scenario["profile"],
            "target_noise_slope": slope,
            "target_recovery_latency": latency,
            "irrecoverable_if_missed": irrecoverable,
            "requires_citation": True,
        },
    }


def _build_canary_row(*, family: str, split: str, index: int, rng: random.Random) -> dict[str, Any]:
    episode_id = _episode_id(family, split, index)
    uid = _uid(rng)
    family_label = family.replace("_", " ")
    return {
        "id": _row_id(episode_id),
        "episode_id": episode_id,
        "schema_version": "0.1",
        "document": f"# Canary {episode_id}\n\n- [{uid}] UPDATE step=1 SET canary.token = C{index:03d}",
        "book": (
            f"# Canary {episode_id}\n\n"
            "## Rules\n"
            "- This row is intentionally adversarial and expected to fail exact matching.\n\n"
            "## State Ledger\n"
            f"- [{uid}] step=1 SET canary.token = C{index:03d}"
        ),
        "question": (
            f"For this {family_label} canary, return both primary and backup action as "
            "`primary|backup` in JSON (value, support_ids)."
        ),
        "gold": {"value": "__CANARY_EXPECTED_FAIL__", "support_ids": [uid]},
        "meta": {
            "family": family,
            "split": split,
            "case_index": index,
            "profile": "adversarial_dual_output",
            "expected_fail": True,
            "requires_citation": True,
        },
    }


def _build_row(*, family: str, split: str, index: int, rng: random.Random) -> dict[str, Any]:
    if split == "canary":
        return _build_canary_row(family=family, split=split, index=index, rng=rng)
    if family == "rpa_mode_switch":
        return _build_rpa_row(split=split, index=index, rng=rng)
    if family == "intent_spec_layer":
        return _build_intent_row(split=split, index=index, rng=rng)
    if family == "noise_escalation":
        return _build_noise_row(split=split, index=index, rng=rng)
    raise ValueError(f"Unsupported family: {family}")


def _write_family(ns: argparse.Namespace) -> int:
    family = ns.family
    out_dir = Path(ns.out_dir)
    anchors_path = out_dir / f"{family}_anchors.jsonl"
    holdout_path = out_dir / f"{family}_holdout.jsonl"
    canary_path = out_dir / f"{family}_canary.jsonl"

    try:
        _ensure_write(anchors_path, ns.overwrite)
        _ensure_write(holdout_path, ns.overwrite)
        _ensure_write(canary_path, ns.overwrite)
    except FileExistsError as exc:
        print(exc)
        print("Use --overwrite to replace generated files.")
        return 1

    rng = random.Random(ns.seed)
    anchors = [_build_row(family=family, split="anchors", index=i + 1, rng=rng) for i in range(ns.anchors)]
    holdout = [_build_row(family=family, split="holdout", index=i + 1, rng=rng) for i in range(ns.holdout)]
    canary = [_build_row(family=family, split="canary", index=i + 1, rng=rng) for i in range(ns.canary)]

    write_jsonl(anchors_path, anchors)
    write_jsonl(holdout_path, holdout)
    write_jsonl(canary_path, canary)

    print(f"Wrote {family} fixtures:")
    print(f"- {anchors_path}")
    print(f"- {holdout_path}")
    print(f"- {canary_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ns = _parse_args(argv)
    return _write_family(ns)


def main_for_family(family: str, argv: list[str] | None = None) -> int:
    ns = _parse_args(argv, forced_family=family)
    return _write_family(ns)


if __name__ == "__main__":
    raise SystemExit(main())
