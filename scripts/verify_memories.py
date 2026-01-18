from __future__ import annotations

import argparse
import json
from pathlib import Path

from goldevidencebench.memory import verify_memory_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify cited memory entries against repo files."
    )
    parser.add_argument(
        "--in",
        dest="input_path",
        required=True,
        help="Path to memory JSONL.",
    )
    parser.add_argument(
        "--out",
        dest="output_path",
        default="runs/release_gates/memory_verify.json",
        help="Path to write summary JSON.",
    )
    parser.add_argument(
        "--out-details",
        dest="details_path",
        default=None,
        help="Optional path to write per-memory results JSON.",
    )
    parser.add_argument(
        "--root",
        dest="root_path",
        default=".",
        help="Repo root for resolving file_path in citations.",
    )
    args = parser.parse_args()

    root = Path(args.root_path).resolve()
    results, summary = verify_memory_path(args.input_path, root=root)

    out_path = Path(args.output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if args.details_path:
        details_path = Path(args.details_path)
        details_path.parent.mkdir(parents=True, exist_ok=True)
        details_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
