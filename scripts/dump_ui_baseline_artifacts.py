from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from goldevidencebench.ui_policy import preselect_candidates_with_trace
from goldevidencebench.util import read_jsonl


def _trace_row(
    row: dict[str, Any],
    *,
    apply_overlay_filter: bool,
    apply_rules: bool,
) -> dict[str, Any]:
    candidates = row.get("candidates", [])
    if not isinstance(candidates, list):
        candidates = []
    filtered, trace = preselect_candidates_with_trace(
        row,
        candidates,
        apply_overlay_filter=apply_overlay_filter,
        apply_rules=apply_rules,
    )
    final_ids = [
        candidate.get("candidate_id")
        for candidate in filtered
        if isinstance(candidate, dict)
        and isinstance(candidate.get("candidate_id"), str)
    ]
    trace["final_choice"] = final_ids[0] if len(final_ids) == 1 else None
    trace["final_candidates"] = final_ids
    if "requires_state" in row:
        trace["requires_state"] = row.get("requires_state")
    if "abstain_expected" in row:
        trace["abstain_expected"] = row.get("abstain_expected")
    return trace


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dump UI baseline artifacts (policy traces + SA diffs)."
    )
    parser.add_argument("--fixture", required=True, help="Path to the UI fixture JSONL file.")
    parser.add_argument("--baseline", required=True, help="Path to the baseline JSON output.")
    parser.add_argument("--out-dir", required=True, help="Output directory for artifacts.")
    parser.add_argument(
        "--max-diffs",
        type=int,
        default=10,
        help="Maximum number of SA diffs to write.",
    )
    parser.add_argument(
        "--overlay-filter",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Apply overlay filtering in the policy trace.",
    )
    parser.add_argument(
        "--rules",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Apply deterministic rules in the policy trace.",
    )
    args = parser.parse_args()

    fixture_path = Path(args.fixture)
    if not fixture_path.exists():
        print(f"Fixture not found: {fixture_path}")
        return 1
    baseline_path = Path(args.baseline)
    if not baseline_path.exists():
        print(f"Baseline output not found: {baseline_path}")
        return 1

    rows = [row for row in read_jsonl(fixture_path) if isinstance(row, dict)]
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    seed_runs = baseline.get("seed_runs", [])
    if not isinstance(seed_runs, list):
        seed_runs = []

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    traces_path = out_dir / "policy_traces.jsonl"
    with traces_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            trace = _trace_row(
                row,
                apply_overlay_filter=args.overlay_filter,
                apply_rules=args.rules,
            )
            handle.write(json.dumps(trace, ensure_ascii=True) + "\n")

    sa_diffs = []
    for run in seed_runs:
        if not isinstance(run, dict):
            continue
        diff = run.get("sa_diff")
        if isinstance(diff, dict):
            sa_diffs.append(diff)
    if args.max_diffs >= 0:
        sa_diffs = sa_diffs[: args.max_diffs]
    if sa_diffs:
        diffs_path = out_dir / "sa_diffs.json"
        diffs_path.write_text(json.dumps(sa_diffs, indent=2), encoding="utf-8")
    else:
        diffs_path = None

    meta = {
        "fixture": str(fixture_path),
        "baseline": str(baseline_path),
        "rows": len(rows),
        "seed_runs": len(seed_runs),
        "sa_diffs": len(sa_diffs),
        "traces_path": str(traces_path),
        "sa_diffs_path": str(diffs_path) if diffs_path else "",
    }
    meta_path = out_dir / "meta.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
