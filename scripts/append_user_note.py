from __future__ import annotations

import argparse
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Append a user note and emit a citation-backed memory entry."
    )
    parser.add_argument("--claim", required=True, help="Note text to store.")
    parser.add_argument("--tags", default="notes,project")
    parser.add_argument("--confidence", type=float, default=0.6)
    parser.add_argument("--unused", action="store_true")
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    script = Path(__file__).resolve().parent / "add_note_memory.py"
    cmd = [
        sys.executable,
        str(script),
        "--note",
        args.claim,
        "--tags",
        args.tags,
        "--confidence",
        str(args.confidence),
        "--notes-path",
        args.notes_path,
        "--memory-path",
        args.memory_path,
    ]
    if args.unused:
        cmd.append("--unused")
    return int(__import__("subprocess").call(cmd))


if __name__ == "__main__":
    raise SystemExit(main())
