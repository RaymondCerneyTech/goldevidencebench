from __future__ import annotations

import argparse
from pathlib import Path

from goldevidencebench.reporting import generate_report


def _latest_run_dir(runs_root: Path) -> Path:
    if not runs_root.exists():
        raise FileNotFoundError(f"Runs root not found: {runs_root}")
    candidates: list[Path] = []
    candidates_with_diag: list[Path] = []
    for summary_path in runs_root.rglob("summary.json"):
        if summary_path.parent == runs_root:
            continue
        if "release_gates" in summary_path.parts:
            continue
        candidates.append(summary_path)
        if (summary_path.parent / "diagnosis.json").exists():
            candidates_with_diag.append(summary_path)
    if not candidates:
        raise FileNotFoundError(f"No summary.json files found under {runs_root}")
    preferred = candidates_with_diag if candidates_with_diag else candidates
    return max(preferred, key=lambda path: path.stat().st_mtime).parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a human-readable report for a run.")
    run_group = parser.add_mutually_exclusive_group()
    run_group.add_argument(
        "--run-dir",
        type=Path,
        help="Run directory containing summary.json/diagnosis.json/compact_state.json.",
    )
    run_group.add_argument(
        "--latest",
        action="store_true",
        help="Use the most recent run under runs/ (prefers runs with diagnosis.json).",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("runs/summary.json"),
        help="Path to summary.json.",
    )
    parser.add_argument(
        "--diagnosis",
        type=Path,
        default=Path("runs/diagnosis.json"),
        help="Path to diagnosis.json.",
    )
    parser.add_argument(
        "--compact",
        type=Path,
        default=Path("runs/compact_state.json"),
        help="Path to compact_state.json.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("runs/report.md"),
        help="Path to report.md output.",
    )
    parser.add_argument(
        "--thresholds",
        type=Path,
        default=Path("configs/diagnosis_thresholds.json"),
        help="Path to diagnosis thresholds JSON.",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        help="Print the report.md contents after writing.",
    )
    args = parser.parse_args()

    default_summary = Path("runs/summary.json")
    default_diagnosis = Path("runs/diagnosis.json")
    default_compact = Path("runs/compact_state.json")
    default_out = Path("runs/report.md")
    using_run_dir = args.run_dir is not None or args.latest
    if using_run_dir:
        explicit_paths = [
            args.summary != default_summary,
            args.diagnosis != default_diagnosis,
            args.compact != default_compact,
            args.out != default_out,
        ]
        if any(explicit_paths):
            parser.error("Use --run-dir/--latest OR explicit paths, not both.")
        run_dir = args.run_dir
        if args.latest:
            run_dir = _latest_run_dir(Path("runs"))
        if run_dir is None:
            parser.error("--run-dir is required when not using --latest.")
        args.summary = run_dir / "summary.json"
        args.diagnosis = run_dir / "diagnosis.json"
        args.compact = run_dir / "compact_state.json"
        args.out = run_dir / "report.md"

    generate_report(
        summary_path=args.summary,
        diagnosis_path=args.diagnosis,
        compact_state_path=args.compact,
        out_path=args.out,
        thresholds_path=args.thresholds,
    )
    print(f"Wrote {args.out}")
    if args.print:
        print(args.out.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
