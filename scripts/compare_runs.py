from __future__ import annotations

import argparse
from pathlib import Path

from goldevidencebench import run_diff


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare two run folders and emit a delta report.")
    parser.add_argument("--base", type=Path, help="Base run directory (older).")
    parser.add_argument("--other", type=Path, help="Other run directory (newer).")
    parser.add_argument("--latest-pair", action="store_true", help="Use the two most recent runs.")
    parser.add_argument("--runs-root", type=Path, default=Path("runs"), help="Root folder to search.")
    parser.add_argument(
        "--require-compact-state",
        action="store_true",
        help="Only consider runs that include compact_state.json.",
    )
    parser.add_argument(
        "--allow-missing-diagnosis",
        action="store_true",
        help="Allow latest-pair selection when diagnosis.json is missing.",
    )
    parser.add_argument("--out", type=Path, default=None, help="Optional output markdown path.")
    parser.add_argument("--print", action="store_true", help="Print the delta report to stdout.")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Include unchanged metrics/fields in the delta report.",
    )
    return parser.parse_args()


def _latest_pair(
    *,
    runs_root: Path,
    require_diagnosis: bool,
    require_compact_state: bool,
) -> tuple[Path, Path] | None:
    if not runs_root.exists():
        return None
    summary_paths = []
    for path in runs_root.rglob("summary.json"):
        if path.parent == runs_root:
            continue
        if "release_gates" in path.parts:
            continue
        if require_compact_state and not (path.parent / "compact_state.json").exists():
            continue
        if require_diagnosis and not (path.parent / "diagnosis.json").exists():
            continue
        summary_paths.append(path)
    if len(summary_paths) < 2:
        return None
    summary_paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    other = summary_paths[0].parent
    base = summary_paths[1].parent
    return base, other


def main() -> int:
    ns = _parse_args()
    require_diagnosis = not ns.allow_missing_diagnosis

    if ns.latest_pair:
        pair = _latest_pair(
            runs_root=ns.runs_root,
            require_diagnosis=require_diagnosis,
            require_compact_state=ns.require_compact_state,
        )
        if pair is None:
            print("Could not find two runs to compare under runs/.")
            return 1
        base_dir, other_dir = pair
    else:
        if ns.base is None or ns.other is None:
            print("Set --base and --other, or use --latest-pair.")
            return 1
        base_dir = ns.base
        other_dir = ns.other

    if not base_dir.exists():
        print(f"Base run directory not found: {base_dir}")
        return 1
    if not other_dir.exists():
        print(f"Other run directory not found: {other_dir}")
        return 1
    delta = run_diff.compare_runs(base_dir=base_dir, other_dir=other_dir)
    report = run_diff.render_delta_report(delta, full=ns.full)

    out_path = ns.out
    if out_path is None:
        out_path = Path(delta["other_dir"]) / "delta_report.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"Wrote {out_path}")
    if ns.print:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
