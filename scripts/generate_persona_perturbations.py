from __future__ import annotations

import argparse
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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate deterministic persona-perturbed fixture sidecar rows by "
            "prepending persona directives to question text."
        )
    )
    parser.add_argument("--in", dest="input_path", required=True, type=Path)
    parser.add_argument("--out", dest="output_path", required=True, type=Path)
    parser.add_argument(
        "--profiles",
        default=",".join(DEFAULT_PROFILES),
        help=(
            "Comma-separated persona profile IDs. "
            f"Default: {','.join(DEFAULT_PROFILES)}"
        ),
    )
    return parser.parse_args()


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


def _persona_question(*, base_question: str, profile: str) -> str:
    directive = PROFILE_DIRECTIVES_V1[profile]
    return f"{directive}\n\n[ORIGINAL QUESTION]\n{base_question}"


def _persona_row(
    *,
    row: dict[str, Any],
    base_row_id: str,
    profile: str,
) -> dict[str, Any]:
    out = copy.deepcopy(row)
    out["id"] = f"{base_row_id}_persona_{profile}"
    out["question"] = _persona_question(base_question=_coerce_question(row), profile=profile)

    meta = out.get("meta")
    if not isinstance(meta, dict):
        meta = {}
        out["meta"] = meta
    meta["persona_profile"] = profile
    meta["persona_profile_version"] = PROFILE_VERSION
    meta["persona_variant"] = True
    meta["persona_base_row_id"] = base_row_id
    return out


def _build_rows(*, rows: list[dict[str, Any]], profiles: list[str]) -> list[dict[str, Any]]:
    out_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        base_row_id = str(row.get("id") or f"row_{index:06d}")
        for profile in profiles:
            out_rows.append(_persona_row(row=row, base_row_id=base_row_id, profile=profile))
    return out_rows


def main() -> int:
    ns = _parse_args()
    profiles = _parse_profiles(ns.profiles)
    base_rows = [row for row in read_jsonl(ns.input_path) if isinstance(row, dict)]
    persona_rows = _build_rows(rows=base_rows, profiles=profiles)
    write_jsonl(ns.output_path, persona_rows)
    print(
        "persona_perturbations:"
        f" in_rows={len(base_rows)}"
        f" profiles={len(profiles)}"
        f" out_rows={len(persona_rows)}"
        f" version={PROFILE_VERSION}"
    )
    print(f"Wrote {ns.output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
