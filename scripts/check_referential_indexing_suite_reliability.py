from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check reliability across referential_indexing_suite runs using hard gate, "
            "holdout floors, and jitter bounds."
        )
    )
    parser.add_argument("--run-dirs", nargs="+", required=True)
    parser.add_argument("--min-runs", type=int, default=2)
    parser.add_argument("--stage", choices=("observe", "ramp", "target", "custom"), default="observe")
    parser.add_argument("--min-value-acc", type=float, default=None)
    parser.add_argument("--min-exact-acc", type=float, default=None)
    parser.add_argument("--min-cite-f1", type=float, default=None)
    parser.add_argument("--min-part-coverage-recall", type=float, default=None)
    parser.add_argument("--min-pointer-precision", type=float, default=None)
    parser.add_argument("--min-pointer-recall", type=float, default=None)
    parser.add_argument("--min-reassembly-fidelity", type=float, default=None)
    parser.add_argument("--max-hallucinated-expansion-rate", type=float, default=None)
    parser.add_argument("--max-stale-pointer-override-rate", type=float, default=None)
    parser.add_argument("--max-lookup-depth-cost", type=float, default=None)
    parser.add_argument("--max-value-acc-jitter", type=float, default=0.05)
    parser.add_argument("--max-exact-acc-jitter", type=float, default=0.05)
    parser.add_argument("--max-cite-f1-jitter", type=float, default=0.05)
    parser.add_argument("--max-canary-exact-rate", type=float, default=0.90)
    parser.add_argument(
        "--allow-latest-nontarget",
        action="store_true",
        help="Allow writing *_latest.json when stage is not target.",
    )
    parser.add_argument("--out", type=Path, default=None)
    return parser.parse_args()


def _read_summary(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid JSON object: {path}")
    return raw


def _metric(summary: dict[str, Any], split: str, metric: str) -> float:
    sec = summary.get(split)
    if not isinstance(sec, dict):
        return float("nan")
    means = sec.get("means")
    if not isinstance(means, dict):
        return float("nan")
    value = means.get(metric)
    if isinstance(value, (int, float)):
        return float(value)
    return float("nan")


def _is_pass(summary: dict[str, Any], split: str) -> bool:
    sec = summary.get(split)
    return isinstance(sec, dict) and sec.get("status") == "PASS"


def _jitter(values: list[float]) -> float:
    finite = [v for v in values if v == v]
    if not finite:
        return float("nan")
    return max(finite) - min(finite)


def _canary_exact(summary: dict[str, Any]) -> float:
    raw = summary.get("canary_exact_rate")
    if isinstance(raw, (int, float)):
        return float(raw)
    return _metric(summary, "canary", "exact_acc")


def _is_latest_output(path: Path | None) -> bool:
    if path is None:
        return False
    return path.name.lower().endswith("_latest.json")


def main() -> int:
    ns = _parse_args()
    release_stage_approved = ns.stage == "target"
    if _is_latest_output(ns.out) and (not release_stage_approved) and (not ns.allow_latest_nontarget):
        print(
            f"Refusing to write {ns.out}: stage '{ns.stage}' is not release-approved for latest promotion. "
            "Use --allow-latest-nontarget to override."
        )
        return 2
    run_dirs = [Path(p) for p in ns.run_dirs]
    if len(run_dirs) < ns.min_runs:
        print(f"Need at least {ns.min_runs} runs; got {len(run_dirs)}.")
        return 1

    summaries: list[tuple[Path, dict[str, Any]]] = []
    for run_dir in run_dirs:
        summary_path = run_dir / "referential_indexing_suite_summary.json"
        if not summary_path.exists():
            print(f"Missing summary file: {summary_path}")
            return 1
        summary = _read_summary(summary_path)
        summary_stage = summary.get("stage")
        if not isinstance(summary_stage, str):
            print(f"Missing stage provenance in summary: {summary_path}")
            return 1
        if summary_stage != ns.stage:
            print(
                f"Stage provenance mismatch for {summary_path}: summary.stage={summary_stage!r}, "
                f"checker --stage={ns.stage!r}"
            )
            return 1
        summaries.append((run_dir, summary))

    stage_floors = {
        "observe": {
            "value_acc": 0.55,
            "exact_acc": 0.55,
            "cite_f1": 0.35,
            "part_coverage_recall": 0.55,
            "pointer_precision": 0.35,
            "pointer_recall": 0.35,
            "reassembly_fidelity": 0.55,
            "hallucinated_expansion_rate": 0.55,
            "stale_pointer_override_rate": 0.45,
            "lookup_depth_cost": 8.0,
        },
        "ramp": {
            "value_acc": 0.70,
            "exact_acc": 0.70,
            "cite_f1": 0.55,
            "part_coverage_recall": 0.70,
            "pointer_precision": 0.55,
            "pointer_recall": 0.55,
            "reassembly_fidelity": 0.70,
            "hallucinated_expansion_rate": 0.30,
            "stale_pointer_override_rate": 0.25,
            "lookup_depth_cost": 6.0,
        },
        "target": {
            "value_acc": 0.85,
            "exact_acc": 0.85,
            "cite_f1": 0.85,
            "part_coverage_recall": 0.85,
            "pointer_precision": 0.85,
            "pointer_recall": 0.85,
            "reassembly_fidelity": 0.85,
            "hallucinated_expansion_rate": 0.10,
            "stale_pointer_override_rate": 0.10,
            "lookup_depth_cost": 4.0,
        },
        "custom": {
            "value_acc": 0.0,
            "exact_acc": 0.0,
            "cite_f1": 0.0,
            "part_coverage_recall": 0.0,
            "pointer_precision": 0.0,
            "pointer_recall": 0.0,
            "reassembly_fidelity": 0.0,
            "hallucinated_expansion_rate": 1.0,
            "stale_pointer_override_rate": 1.0,
            "lookup_depth_cost": 999.0,
        },
    }
    selected = stage_floors[ns.stage]
    floors = {
        "value_acc": ns.min_value_acc if ns.min_value_acc is not None else selected["value_acc"],
        "exact_acc": ns.min_exact_acc if ns.min_exact_acc is not None else selected["exact_acc"],
        "cite_f1": ns.min_cite_f1 if ns.min_cite_f1 is not None else selected["cite_f1"],
        "part_coverage_recall": (
            ns.min_part_coverage_recall if ns.min_part_coverage_recall is not None else selected["part_coverage_recall"]
        ),
        "pointer_precision": ns.min_pointer_precision if ns.min_pointer_precision is not None else selected["pointer_precision"],
        "pointer_recall": ns.min_pointer_recall if ns.min_pointer_recall is not None else selected["pointer_recall"],
        "reassembly_fidelity": (
            ns.min_reassembly_fidelity if ns.min_reassembly_fidelity is not None else selected["reassembly_fidelity"]
        ),
        "hallucinated_expansion_rate": (
            ns.max_hallucinated_expansion_rate
            if ns.max_hallucinated_expansion_rate is not None
            else selected["hallucinated_expansion_rate"]
        ),
        "stale_pointer_override_rate": (
            ns.max_stale_pointer_override_rate
            if ns.max_stale_pointer_override_rate is not None
            else selected["stale_pointer_override_rate"]
        ),
        "lookup_depth_cost": ns.max_lookup_depth_cost if ns.max_lookup_depth_cost is not None else selected["lookup_depth_cost"],
    }

    lines: list[str] = ["Referential indexing suite reliability check", f"Runs: {len(summaries)}", f"Stage: {ns.stage}"]
    failures: list[str] = []

    for run_dir, summary in summaries:
        top = summary.get("hard_gate_status")
        ok_top = top == "PASS"
        lines.append(f"[{'PASS' if ok_top else 'FAIL'}] {run_dir}: hard_gate_status={top}")
        if not ok_top:
            failures.append(f"{run_dir}: hard_gate_status != PASS")

        for split in ("anchors", "holdout"):
            ok_split = _is_pass(summary, split)
            lines.append(f"[{'PASS' if ok_split else 'FAIL'}] {run_dir}: {split}.status={summary.get(split, {}).get('status')}")
            if not ok_split:
                failures.append(f"{run_dir}: {split}.status != PASS")

        canary_exact = _canary_exact(summary)
        canary_ok = (canary_exact == canary_exact) and (canary_exact <= ns.max_canary_exact_rate)
        lines.append(f"[{'PASS' if canary_ok else 'FAIL'}] {run_dir}: canary.exact_rate={canary_exact:.6f} <= {ns.max_canary_exact_rate:.6f}")
        if not canary_ok:
            failures.append(f"{run_dir}: canary.exact_rate > {ns.max_canary_exact_rate}")

    floor_checks = [
        ("value_acc", floors["value_acc"], ">="),
        ("exact_acc", floors["exact_acc"], ">="),
        ("cite_f1", floors["cite_f1"], ">="),
        ("part_coverage_recall", floors["part_coverage_recall"], ">="),
        ("pointer_precision", floors["pointer_precision"], ">="),
        ("pointer_recall", floors["pointer_recall"], ">="),
        ("reassembly_fidelity", floors["reassembly_fidelity"], ">="),
        ("hallucinated_expansion_rate", floors["hallucinated_expansion_rate"], "<="),
        ("stale_pointer_override_rate", floors["stale_pointer_override_rate"], "<="),
        ("lookup_depth_cost", floors["lookup_depth_cost"], "<="),
    ]

    for run_dir, summary in summaries:
        for metric, threshold, op in floor_checks:
            value = _metric(summary, "holdout", metric)
            if value != value:
                ok = False
            elif op == ">=":
                ok = value >= threshold
            else:
                ok = value <= threshold
            lines.append(f"[{'PASS' if ok else 'FAIL'}] {run_dir}: holdout.{metric}={value:.6f} {op} {threshold:.6f}")
            if not ok:
                failures.append(f"{run_dir}: holdout.{metric} {op} {threshold}")

    value_vals = [_metric(s, "holdout", "value_acc") for _, s in summaries]
    exact_vals = [_metric(s, "holdout", "exact_acc") for _, s in summaries]
    cite_vals = [_metric(s, "holdout", "cite_f1") for _, s in summaries]
    jitter_checks = [
        ("holdout.value_acc_jitter", _jitter(value_vals), ns.max_value_acc_jitter),
        ("holdout.exact_acc_jitter", _jitter(exact_vals), ns.max_exact_acc_jitter),
        ("holdout.cite_f1_jitter", _jitter(cite_vals), ns.max_cite_f1_jitter),
    ]
    for name, value, max_allowed in jitter_checks:
        ok = (value == value) and (value <= max_allowed)
        lines.append(f"[{'PASS' if ok else 'FAIL'}] {name}={value:.6f} <= {max_allowed:.6f}")
        if not ok:
            failures.append(f"{name} > {max_allowed}")

    status = "PASS" if not failures else "FAIL"
    lines.append(f"RESULT: {status}")
    print("\n".join(lines))

    payload = {
        "benchmark": "referential_indexing_suite_reliability",
        "runs": [str(r) for r in run_dirs],
        "stage": ns.stage,
        "provenance": {
            "release_stage_required": "target",
            "release_stage_approved": release_stage_approved,
            "allow_latest_nontarget": bool(ns.allow_latest_nontarget),
        },
        "floors": floors,
        "status": status,
        "failures": failures,
        "jitter": {
            "holdout_value_acc": _jitter(value_vals),
            "holdout_exact_acc": _jitter(exact_vals),
            "holdout_cite_f1": _jitter(cite_vals),
        },
    }
    if ns.out is not None:
        ns.out.parent.mkdir(parents=True, exist_ok=True)
        ns.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote {ns.out}")

    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
