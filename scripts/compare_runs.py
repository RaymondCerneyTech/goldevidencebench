from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

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
        "--benchmark",
        type=str,
        default=None,
        help="Optional summary benchmark name filter (for --latest-pair).",
    )
    parser.add_argument(
        "--run-name-prefix",
        type=str,
        default=None,
        help="Optional run directory name prefix filter (for --latest-pair).",
    )
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
    benchmark: str | None,
    run_name_prefix: str | None,
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
        if run_name_prefix and not path.parent.name.startswith(run_name_prefix):
            continue
        if benchmark:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            run_benchmark = payload.get("benchmark")
            if run_benchmark != benchmark:
                continue
        summary_paths.append(path)
    if len(summary_paths) < 2:
        return None
    summary_paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    other = summary_paths[0].parent
    base = summary_paths[1].parent
    return base, other


def _load_summary(path: Path) -> dict[str, Any]:
    summary_path = path / "summary.json"
    if not summary_path.exists():
        return {}
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _rag_mean_delta_section(*, base_dir: Path, other_dir: Path) -> str:
    base_summary = _load_summary(base_dir)
    other_summary = _load_summary(other_dir)
    base_means = base_summary.get("means")
    other_means = other_summary.get("means")
    if not isinstance(base_means, dict) or not isinstance(other_means, dict):
        return ""

    keys = (
        "value_acc",
        "exact_acc",
        "entailment",
        "answer_correct_given_selected",
        "cite_f1",
        "instruction_acc",
        "state_integrity_rate",
    )
    lines = ["## RAG mean deltas"]
    found = False
    for key in keys:
        base_val = base_means.get(key)
        other_val = other_means.get(key)
        if not isinstance(base_val, (int, float)) or not isinstance(other_val, (int, float)):
            continue
        delta = other_val - base_val
        lines.append(f"- {key}: {base_val:.6f} -> {other_val:.6f} ({delta:+.6f})")
        found = True
    if not found:
        return ""
    return "\n".join(lines)


def main() -> int:
    ns = _parse_args()
    require_diagnosis = not ns.allow_missing_diagnosis

    if ns.latest_pair:
        pair = _latest_pair(
            runs_root=ns.runs_root,
            require_diagnosis=require_diagnosis,
            require_compact_state=ns.require_compact_state,
            benchmark=ns.benchmark,
            run_name_prefix=ns.run_name_prefix,
        )
        if pair is None:
            filter_bits = []
            if ns.benchmark:
                filter_bits.append(f"benchmark={ns.benchmark}")
            if ns.run_name_prefix:
                filter_bits.append(f"run_name_prefix={ns.run_name_prefix}")
            suffix = f" with filters ({', '.join(filter_bits)})" if filter_bits else ""
            print(f"Could not find two runs to compare under runs/{suffix}.")
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
    if ns.benchmark == "rag_benchmark_strict":
        rag_section = _rag_mean_delta_section(base_dir=base_dir, other_dir=other_dir)
        if rag_section:
            report = report.rstrip() + "\n\n" + rag_section + "\n"

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
