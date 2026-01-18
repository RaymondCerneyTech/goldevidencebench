from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from goldevidencebench.memory import verify_memory_entries
from goldevidencebench.util import read_jsonl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print verified notes from a memory JSONL file."
    )
    parser.add_argument(
        "--in",
        dest="input_path",
        default="data/memories/user_notes_memory.jsonl",
        help="Path to notes-backed memory JSONL.",
    )
    parser.add_argument(
        "--root",
        dest="root_path",
        default=".",
        help="Repo root for resolving file_path in citations.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum verified notes to print.",
    )
    parser.add_argument(
        "--query",
        default="",
        help="Case-insensitive substring to filter claim_text (optional).",
    )
    parser.add_argument(
        "--tag",
        action="append",
        default=[],
        help="Tag filter (repeatable or comma-separated).",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Return newest matches first.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    parser.add_argument(
        "--include-unused",
        action="store_true",
        help="Include entries marked used=false.",
    )
    return parser.parse_args()


def build_output(
    entries: list[dict[str, Any]],
    results: list[dict[str, Any]],
    limit: int,
    include_unused: bool,
    query: str,
    tags_filter: list[str],
    latest: bool,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    query_norm = query.strip().lower()
    pairs = list(zip(entries, results))
    if latest:
        pairs = list(reversed(pairs))
    tag_set = set(t.lower() for t in tags_filter if t)
    for entry, result in pairs:
        if not result.get("ok", False):
            continue
        if not include_unused and not bool(entry.get("used", True)):
            continue
        if query_norm:
            claim = str(entry.get("claim_text", "")).lower()
            if query_norm not in claim:
                continue
        if tag_set:
            entry_tags = entry.get("tags", [])
            if isinstance(entry_tags, list):
                entry_tag_set = set(str(t).lower() for t in entry_tags)
            else:
                entry_tag_set = set()
            if entry_tag_set.isdisjoint(tag_set):
                continue
        output.append(
            {
                "id": entry.get("id"),
                "claim_text": entry.get("claim_text"),
                "created_at": entry.get("created_at"),
                "tags": entry.get("tags", []),
                "confidence": entry.get("confidence"),
            }
        )
        if limit and len(output) >= limit:
            break
    return output


def main() -> int:
    args = parse_args()
    entries = list(read_jsonl(args.input_path))
    root = Path(args.root_path).resolve()
    results, _ = verify_memory_entries(entries, root=root)
    tags_filter: list[str] = []
    for value in args.tag:
        for raw in str(value).split(","):
            raw = raw.strip()
            if raw:
                tags_filter.append(raw)
    output = build_output(
        entries,
        results,
        args.limit,
        args.include_unused,
        args.query,
        tags_filter,
        args.latest,
    )

    if args.format == "json":
        print(json.dumps(output, indent=2))
    else:
        for item in output:
            claim = item.get("claim_text") or ""
            entry_id = item.get("id") or ""
            print(f"- {claim} (id={entry_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
