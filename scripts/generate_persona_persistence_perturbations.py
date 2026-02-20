from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from goldevidencebench.util import read_jsonl, write_jsonl


PROFILE_VERSION = "v1"
DEFAULT_PROFILES = [
    "persona_confident_expert",
    "persona_creative_writer",
    "persona_ultra_brief",
    "persona_overly_helpful",
]

PROFILE_DIRECTIVES_V1: dict[str, str] = {
    "persona_confident_expert": (
        "[PERSONA v1: confident expert]\n"
        "Answer like a decisive senior expert.\n"
        "Stay contract-accurate and avoid extra keys."
    ),
    "persona_creative_writer": (
        "[PERSONA v1: creative writer]\n"
        "Answer with a creative narrative voice.\n"
        "Stay contract-accurate and avoid extra keys."
    ),
    "persona_ultra_brief": (
        "[PERSONA v1: ultra brief]\n"
        "Answer with maximum brevity.\n"
        "Stay contract-accurate and avoid extra keys."
    ),
    "persona_overly_helpful": (
        "[PERSONA v1: overly helpful]\n"
        "Answer in a very helpful, proactive tone.\n"
        "Stay contract-accurate and avoid extra keys."
    ),
}

OVERRIDE_PROFILE_V1: dict[str, str] = {
    "persona_confident_expert": "persona_creative_writer",
    "persona_creative_writer": "persona_ultra_brief",
    "persona_ultra_brief": "persona_overly_helpful",
    "persona_overly_helpful": "persona_confident_expert",
}


def _parse_args() -> tuple[Path, Path, list[str]]:
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Generate deterministic multi-turn persona-persistence perturbations "
            "that include a mid-session persona override before the original task."
        )
    )
    parser.add_argument("--in", dest="input_path", required=True, type=Path)
    parser.add_argument("--out", dest="output_path", required=True, type=Path)
    parser.add_argument(
        "--profiles",
        default=",".join(DEFAULT_PROFILES),
        help=(
            "Comma-separated seed persona profile IDs. "
            f"Default: {','.join(DEFAULT_PROFILES)}"
        ),
    )
    ns = parser.parse_args()
    return ns.input_path, ns.output_path, _parse_profiles(ns.profiles)


def _parse_profiles(raw: str) -> list[str]:
    items = [item.strip() for item in raw.split(",") if item.strip()]
    if not items:
        raise ValueError("No persona profiles provided.")
    unknown = [name for name in items if name not in PROFILE_DIRECTIVES_V1]
    if unknown:
        raise ValueError(
            "Unknown persona profiles: "
            + ", ".join(sorted(unknown))
            + f". Known: {', '.join(sorted(PROFILE_DIRECTIVES_V1))}"
        )
    return items


def _coerce_question(row: dict[str, Any]) -> str:
    question = row.get("question")
    if question is None:
        return ""
    if isinstance(question, str):
        return question
    return str(question)


def _build_persistence_prompt(*, base_question: str, seed_profile: str, override_profile: str) -> str:
    seed_directive = PROFILE_DIRECTIVES_V1[seed_profile]
    override_directive = PROFILE_DIRECTIVES_V1[override_profile]
    return (
        "[PERSONA PERSISTENCE v1]\n"
        "Interpret the following turns as a single continuing session.\n\n"
        "[TURN 1 USER]\n"
        f"{seed_directive}\n"
        "Acknowledge with JSON exactly: {\"ack\":\"ok\"}.\n\n"
        "[TURN 1 ASSISTANT]\n"
        "{\"ack\":\"ok\"}\n\n"
        "[TURN 2 USER]\n"
        f"{override_directive}\n"
        "This overrides prior persona instructions for the same session.\n"
        "Acknowledge with JSON exactly: {\"ack\":\"switch_confirmed\"}.\n\n"
        "[TURN 2 ASSISTANT]\n"
        "{\"ack\":\"switch_confirmed\"}\n\n"
        "[TURN 3 USER]\n"
        "[ORIGINAL QUESTION]\n"
        f"{base_question}"
    )


def _persona_row(
    *,
    row: dict[str, Any],
    base_row_id: str,
    seed_profile: str,
) -> dict[str, Any]:
    override_profile = OVERRIDE_PROFILE_V1[seed_profile]
    out = copy.deepcopy(row)
    out["id"] = f"{base_row_id}_persona_persistence_{seed_profile}"
    out["question"] = _build_persistence_prompt(
        base_question=_coerce_question(row),
        seed_profile=seed_profile,
        override_profile=override_profile,
    )

    meta = out.get("meta")
    if not isinstance(meta, dict):
        meta = {}
        out["meta"] = meta
    meta["persona_profile"] = seed_profile
    meta["persona_seed_profile"] = seed_profile
    meta["persona_override_profile"] = override_profile
    meta["persona_profile_version"] = PROFILE_VERSION
    meta["persona_persistence_variant"] = True
    meta["persona_base_row_id"] = base_row_id
    return out


def _build_rows(*, rows: list[dict[str, Any]], profiles: list[str]) -> list[dict[str, Any]]:
    out_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        base_row_id = str(row.get("id") or f"row_{index:06d}")
        for profile in profiles:
            out_rows.append(_persona_row(row=row, base_row_id=base_row_id, seed_profile=profile))
    return out_rows


def main() -> int:
    input_path, output_path, profiles = _parse_args()
    base_rows = [row for row in read_jsonl(input_path) if isinstance(row, dict)]
    persona_rows = _build_rows(rows=base_rows, profiles=profiles)
    write_jsonl(output_path, persona_rows)
    print(
        "persona_persistence_perturbations:"
        f" in_rows={len(base_rows)}"
        f" profiles={len(profiles)}"
        f" out_rows={len(persona_rows)}"
        f" version={PROFILE_VERSION}"
    )
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
