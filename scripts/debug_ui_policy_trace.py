from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from goldevidencebench.ui_policy import preselect_candidates_with_trace
from goldevidencebench.util import read_jsonl


def _find_row(rows: list[dict[str, Any]], row_id: str) -> dict[str, Any] | None:
    for row in rows:
        if row.get("id") == row_id:
            return row
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Dump UI policy trace for a fixture row.")
    parser.add_argument("--fixture", required=True, help="Path to the UI fixture JSONL file.")
    parser.add_argument("--row-id", required=True, help="Row id to trace.")
    parser.add_argument("--no-overlay-filter", action="store_true", help="Disable overlay filter.")
    parser.add_argument("--no-rules", action="store_true", help="Disable deterministic rules.")
    parser.add_argument("--out", help="Optional path to write the trace JSON output.")
    args = parser.parse_args()

    fixture_path = Path(args.fixture)
    if not fixture_path.exists():
        print(f"Fixture not found: {fixture_path}")
        return 1

    rows = [row for row in read_jsonl(fixture_path) if isinstance(row, dict)]
    row = _find_row(rows, args.row_id)
    if row is None:
        available = [row.get("id") for row in rows if isinstance(row.get("id"), str)]
        print(f"Row id not found: {args.row_id}")
        if available:
            print("Available ids:")
            for row_id in available:
                print(f"- {row_id}")
        return 1

    candidates = row.get("candidates", [])
    if not isinstance(candidates, list):
        print("Row candidates must be a list.")
        return 1

    filtered, trace = preselect_candidates_with_trace(
        row,
        candidates,
        apply_overlay_filter=not args.no_overlay_filter,
        apply_rules=not args.no_rules,
    )
    final_ids = [
        candidate.get("candidate_id")
        for candidate in filtered
        if isinstance(candidate, dict)
        and isinstance(candidate.get("candidate_id"), str)
    ]
    trace["final_choice"] = final_ids[0] if len(final_ids) == 1 else None
    trace["final_candidates"] = final_ids

    payload = json.dumps(trace, indent=2)
    print(payload)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload, encoding="utf-8")
        print(f"Wrote trace: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
