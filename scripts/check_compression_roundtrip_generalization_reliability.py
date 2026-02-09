from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check reliability across multiple compression_roundtrip_generalization runs "
            "by enforcing hard-gate pass, holdout floors, and bounded jitter."
        )
    )
    parser.add_argument(
        "--run-dirs",
        nargs="+",
        required=True,
        help="Run dirs with compression_roundtrip_generalization_summary.json.",
    )
    parser.add_argument("--min-runs", type=int, default=2)
    parser.add_argument(
        "--stage",
        choices=("observe", "ramp", "target", "custom"),
        default="observe",
        help="Threshold rollout stage for compression_roundtrip_generalization.",
    )
    parser.add_argument("--min-value-acc", type=float, default=None)
    parser.add_argument("--min-exact-acc", type=float, default=None)
    parser.add_argument("--min-cite-f1", type=float, default=None)
    parser.add_argument("--min-direct-acc", type=float, default=None)
    parser.add_argument("--min-aggregate-acc", type=float, default=None)
    parser.add_argument("--min-exception-acc", type=float, default=None)
    parser.add_argument("--min-negation-acc", type=float, default=None)
    parser.add_argument("--min-tail-key-acc", type=float, default=None)
    parser.add_argument("--min-null-target-acc", type=float, default=None)
    parser.add_argument("--min-nonnull-target-acc", type=float, default=None)
    parser.add_argument("--min-large-snapshot-acc", type=float, default=None)
    parser.add_argument("--max-value-acc-jitter", type=float, default=0.05)
    parser.add_argument("--max-exact-acc-jitter", type=float, default=0.05)
    parser.add_argument("--max-cite-f1-jitter", type=float, default=0.05)
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
    finite = [x for x in values if x == x]
    if not finite:
        return float("nan")
    return max(finite) - min(finite)


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
        summary_path = run_dir / "compression_roundtrip_generalization_summary.json"
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

    failures: list[str] = []
    lines: list[str] = ["Compression roundtrip generalization reliability check", f"Runs: {len(summaries)}"]

    stage_floors = {
        "observe": {
            "value_acc": 0.65,
            "exact_acc": 0.65,
            "cite_f1": 0.50,
            "direct_acc": 0.75,
            "aggregate_acc": 0.70,
            "exception_acc": 0.20,
            "negation_acc": 0.85,
            "tail_key_acc": 0.70,
            "null_target_acc": 0.85,
            "nonnull_target_acc": 0.55,
            "large_snapshot_acc": 0.00,
        },
        "ramp": {
            "value_acc": 0.75,
            "exact_acc": 0.75,
            "cite_f1": 0.65,
            "direct_acc": 0.78,
            "aggregate_acc": 0.75,
            "exception_acc": 0.45,
            "negation_acc": 0.90,
            "tail_key_acc": 0.75,
            "null_target_acc": 0.90,
            "nonnull_target_acc": 0.70,
            "large_snapshot_acc": 0.35,
        },
        "target": {
            "value_acc": 0.85,
            "exact_acc": 0.85,
            "cite_f1": 0.85,
            "direct_acc": 0.80,
            "aggregate_acc": 0.80,
            "exception_acc": 0.80,
            "negation_acc": 0.80,
            "tail_key_acc": 0.80,
            "null_target_acc": 0.80,
            "nonnull_target_acc": 0.80,
            "large_snapshot_acc": 0.80,
        },
        "custom": {
            "value_acc": 0.00,
            "exact_acc": 0.00,
            "cite_f1": 0.00,
            "direct_acc": 0.00,
            "aggregate_acc": 0.00,
            "exception_acc": 0.00,
            "negation_acc": 0.00,
            "tail_key_acc": 0.00,
            "null_target_acc": 0.00,
            "nonnull_target_acc": 0.00,
            "large_snapshot_acc": 0.00,
        },
    }
    selected_stage = stage_floors[ns.stage]
    floors = {
        "value_acc": ns.min_value_acc if ns.min_value_acc is not None else selected_stage["value_acc"],
        "exact_acc": ns.min_exact_acc if ns.min_exact_acc is not None else selected_stage["exact_acc"],
        "cite_f1": ns.min_cite_f1 if ns.min_cite_f1 is not None else selected_stage["cite_f1"],
        "direct_acc": ns.min_direct_acc if ns.min_direct_acc is not None else selected_stage["direct_acc"],
        "aggregate_acc": ns.min_aggregate_acc if ns.min_aggregate_acc is not None else selected_stage["aggregate_acc"],
        "exception_acc": ns.min_exception_acc if ns.min_exception_acc is not None else selected_stage["exception_acc"],
        "negation_acc": ns.min_negation_acc if ns.min_negation_acc is not None else selected_stage["negation_acc"],
        "tail_key_acc": ns.min_tail_key_acc if ns.min_tail_key_acc is not None else selected_stage["tail_key_acc"],
        "null_target_acc": ns.min_null_target_acc if ns.min_null_target_acc is not None else selected_stage["null_target_acc"],
        "nonnull_target_acc": ns.min_nonnull_target_acc if ns.min_nonnull_target_acc is not None else selected_stage["nonnull_target_acc"],
        "large_snapshot_acc": ns.min_large_snapshot_acc if ns.min_large_snapshot_acc is not None else selected_stage["large_snapshot_acc"],
    }
    lines.append(f"Stage: {ns.stage}")

    for run_dir, summary in summaries:
        top = summary.get("hard_gate_status")
        ok_top = top == "PASS"
        lines.append(f"[{'PASS' if ok_top else 'FAIL'}] {run_dir}: hard_gate_status={top}")
        if not ok_top:
            failures.append(f"{run_dir}: hard_gate_status != PASS")
        for split in ("anchors", "holdout"):
            ok_split = _is_pass(summary, split)
            lines.append(
                f"[{'PASS' if ok_split else 'FAIL'}] {run_dir}: {split}.status={summary.get(split, {}).get('status')}"
            )
            if not ok_split:
                failures.append(f"{run_dir}: {split}.status != PASS")

    floor_checks = [
        ("value_acc", floors["value_acc"]),
        ("exact_acc", floors["exact_acc"]),
        ("cite_f1", floors["cite_f1"]),
        ("direct_acc", floors["direct_acc"]),
        ("aggregate_acc", floors["aggregate_acc"]),
        ("exception_acc", floors["exception_acc"]),
        ("negation_acc", floors["negation_acc"]),
        ("tail_key_acc", floors["tail_key_acc"]),
        ("null_target_acc", floors["null_target_acc"]),
        ("nonnull_target_acc", floors["nonnull_target_acc"]),
        ("large_snapshot_acc", floors["large_snapshot_acc"]),
    ]
    for run_dir, summary in summaries:
        for metric, floor in floor_checks:
            value = _metric(summary, "holdout", metric)
            ok = (value == value) and (value >= floor)
            lines.append(f"[{'PASS' if ok else 'FAIL'}] {run_dir}: holdout.{metric}={value:.6f} >= {floor:.6f}")
            if not ok:
                failures.append(f"{run_dir}: holdout.{metric} < {floor}")

    value_vals = [_metric(summary, "holdout", "value_acc") for _, summary in summaries]
    exact_vals = [_metric(summary, "holdout", "exact_acc") for _, summary in summaries]
    cite_vals = [_metric(summary, "holdout", "cite_f1") for _, summary in summaries]
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
        "benchmark": "compression_roundtrip_generalization_reliability",
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
