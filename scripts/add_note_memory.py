from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Append a note and emit a citation-backed memory entry."
    )
    parser.add_argument("--note", required=True, help="Note text to store.")
    parser.add_argument(
        "--notes-path",
        default="data/memories/user_notes.txt",
        help="Repo-relative notes file path.",
    )
    parser.add_argument(
        "--memory-path",
        default="data/memories/user_notes_memory.jsonl",
        help="Repo-relative memory JSONL path.",
    )
    parser.add_argument("--id", default="", help="Optional memory id.")
    parser.add_argument("--confidence", type=float, default=0.6)
    parser.add_argument(
        "--tags",
        default="notes,project",
        help="Comma-separated tags to attach.",
    )
    parser.add_argument(
        "--unused",
        action="store_true",
        help="Mark the memory as unused (used=false).",
    )
    return parser.parse_args()


def normalize_note(note: str) -> str:
    return " ".join(note.strip().splitlines()).strip()


def resolve_repo_path(root: Path, path_value: str) -> tuple[Path, str]:
    path = Path(path_value)
    if not path.is_absolute():
        path = root / path
    try:
        rel = path.resolve().relative_to(root)
    except ValueError:
        raise ValueError(f"path must be under repo: {path}")
    return path, str(rel.as_posix())


def main() -> int:
    args = parse_args()
    note = normalize_note(args.note)
    if not note:
        print("Note is empty after normalization.", file=sys.stderr)
        return 2

    root = Path(__file__).resolve().parents[1]
    try:
        notes_path, notes_rel = resolve_repo_path(root, args.notes_path)
        memory_path, _ = resolve_repo_path(root, args.memory_path)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    notes_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if notes_path.exists():
        try:
            lines = notes_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            print(f"Unable to read notes file: {exc}", file=sys.stderr)
            return 1

    line_no = len(lines) + 1
    try:
        with notes_path.open("a", encoding="utf-8") as handle:
            handle.write(note + "\n")
    except OSError as exc:
        print(f"Unable to write notes file: {exc}", file=sys.stderr)
        return 1

    created_at = datetime.now(timezone.utc).isoformat()
    entry_id = args.id.strip() or f"note_{created_at.replace(':', '').replace('+', '')}"
    tag_list = [t.strip() for t in args.tags.split(",") if t.strip()]
    entry = {
        "id": entry_id,
        "claim_text": note,
        "citations": [
            {
                "type": "repo",
                "file_path": notes_rel.replace("\\", "/"),
                "line_start": line_no,
                "line_end": line_no,
                "snippet": note,
            }
        ],
        "confidence": args.confidence,
        "created_at": created_at,
        "tags": tag_list,
        "used": not args.unused,
    }

    memory_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with memory_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=True) + "\n")
    except OSError as exc:
        print(f"Unable to write memory file: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote note to {notes_rel} line {line_no}.")
    print(f"Appended memory entry to {memory_path.relative_to(root)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
