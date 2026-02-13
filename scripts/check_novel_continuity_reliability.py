from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check reliability across multiple novel_continuity runs by enforcing "
            "hard-gate pass, threshold floors, and bounded jitter."
        )
    )
    parser.add_argument("--run-dirs", nargs="+", required=True, help="Run dirs with novel_continuity_summary.json.")
    parser.add_argument("--min-runs", type=int, default=2)
    parser.add_argument("--min-value-acc", type=float, default=0.85)
    parser.add_argument(
        "--min-value-exact-acc",
        type=float,
        default=None,
        help="Minimum holdout value_exact_acc floor (preferred metric name).",
    )
    parser.add_argument(
        "--min-exact-acc",
        type=float,
        default=0.85,
        help="Deprecated alias for --min-value-exact-acc.",
    )
    parser.add_argument(
        "--cite-stage",
        choices=("observe", "ramp", "target", "custom"),
        default="observe",
        help="Citation rollout stage for novel continuity.",
    )
    parser.add_argument(
        "--min-cite-f1",
        type=float,
        default=None,
        help="Override cite_f1 floor (defaults to floor implied by --cite-stage).",
    )
    parser.add_argument("--min-identity-acc", type=float, default=0.80)
    parser.add_argument("--min-timeline-acc", type=float, default=0.80)
    parser.add_argument("--min-constraint-acc", type=float, default=0.80)
    parser.add_argument("--max-value-acc-jitter", type=float, default=0.05)
    parser.add_argument(
        "--max-value-exact-acc-jitter",
        type=float,
        default=None,
        help="Max allowed jitter for holdout.value_exact_acc (preferred metric name).",
    )
    parser.add_argument(
        "--max-exact-acc-jitter",
        type=float,
        default=0.05,
        help="Deprecated alias for --max-value-exact-acc-jitter.",
    )
    parser.add_argument("--max-cite-f1-jitter", type=float, default=0.05)
    parser.add_argument(
        "--require-canary-ok",
        action="store_true",
        help="Require canary_status=OK in each run summary. Target stage enforces this by default.",
    )
    parser.add_argument(
        "--allow-latest-nontarget",
        action="store_true",
        help="Allow writing *_latest.json when cite stage is not target.",
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
    keys = (metric,)
    if metric == "value_exact_acc":
        keys = ("value_exact_acc", "exact_acc")
    for key in keys:
        v = means.get(key)
        if isinstance(v, (int, float)):
            return float(v)
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


def _resolved_min_value_exact_acc(ns: argparse.Namespace) -> float:
    if ns.min_value_exact_acc is not None:
        return float(ns.min_value_exact_acc)
    return float(ns.min_exact_acc)


def _resolved_max_value_exact_acc_jitter(ns: argparse.Namespace) -> float:
    if ns.max_value_exact_acc_jitter is not None:
        return float(ns.max_value_exact_acc_jitter)
    return float(ns.max_exact_acc_jitter)


def main() -> int:
    ns = _parse_args()
    release_stage_approved = ns.cite_stage == "target"
    require_canary_ok = bool(ns.require_canary_ok) or release_stage_approved
    if _is_latest_output(ns.out) and (not release_stage_approved) and (not ns.allow_latest_nontarget):
        print(
            f"Refusing to write {ns.out}: cite stage '{ns.cite_stage}' is not release-approved for latest promotion. "
            "Use --allow-latest-nontarget to override."
        )
        return 2
    run_dirs = [Path(p) for p in ns.run_dirs]
    if len(run_dirs) < ns.min_runs:
        print(f"Need at least {ns.min_runs} runs; got {len(run_dirs)}.")
        return 1

    summaries: list[tuple[Path, dict[str, Any]]] = []
    for run_dir in run_dirs:
        p = run_dir / "novel_continuity_summary.json"
        if not p.exists():
            print(f"Missing summary file: {p}")
            return 1
        summary = _read_summary(p)
        summary_stage = summary.get("cite_stage")
        if not isinstance(summary_stage, str):
            print(f"Missing cite_stage provenance in summary: {p}")
            return 1
        if summary_stage != ns.cite_stage:
            print(
                f"Cite-stage provenance mismatch for {p}: summary.cite_stage={summary_stage!r}, "
                f"checker --cite-stage={ns.cite_stage!r}"
            )
            return 1
        summaries.append((run_dir, summary))

    failures: list[str] = []
    lines: list[str] = ["Novel continuity reliability check", f"Runs: {len(summaries)}"]

    cite_stage_floors = {
        "observe": 0.00,
        "ramp": 0.60,
        "target": 0.85,
        "custom": 0.00,
    }
    min_cite_f1 = ns.min_cite_f1
    if min_cite_f1 is None:
        min_cite_f1 = cite_stage_floors[ns.cite_stage]
    lines.append(f"Citation stage: {ns.cite_stage} (min_cite_f1={min_cite_f1:.6f})")
    lines.append(f"Canary gate required: {require_canary_ok}")

    for run_dir, summary in summaries:
        top = summary.get("hard_gate_status")
        ok_top = top == "PASS"
        lines.append(f"[{'PASS' if ok_top else 'FAIL'}] {run_dir}: hard_gate_status={top}")
        if not ok_top:
            failures.append(f"{run_dir}: hard_gate_status != PASS")
        canary_status = summary.get("canary_status")
        if require_canary_ok:
            canary_ok = canary_status == "OK"
            lines.append(f"[{'PASS' if canary_ok else 'FAIL'}] {run_dir}: canary_status={canary_status}")
            if not canary_ok:
                failures.append(f"{run_dir}: canary_status != OK")
        elif isinstance(canary_status, str):
            lines.append(f"[INFO] {run_dir}: canary_status={canary_status}")
        for split in ("anchors", "holdout"):
            ok_split = _is_pass(summary, split)
            lines.append(f"[{'PASS' if ok_split else 'FAIL'}] {run_dir}: {split}.status={summary.get(split, {}).get('status')}")
            if not ok_split:
                failures.append(f"{run_dir}: {split}.status != PASS")

    min_value_exact_acc = _resolved_min_value_exact_acc(ns)
    floor_checks = [
        ("value_acc", ns.min_value_acc),
        ("value_exact_acc", min_value_exact_acc),
        ("cite_f1", min_cite_f1),
        ("identity_acc", ns.min_identity_acc),
        ("timeline_acc", ns.min_timeline_acc),
        ("constraint_acc", ns.min_constraint_acc),
    ]
    for run_dir, summary in summaries:
        for metric, floor in floor_checks:
            value = _metric(summary, "holdout", metric)
            ok = (value == value) and (value >= floor)
            lines.append(f"[{'PASS' if ok else 'FAIL'}] {run_dir}: holdout.{metric}={value:.6f} >= {floor:.6f}")
            if not ok:
                failures.append(f"{run_dir}: holdout.{metric} < {floor}")

    value_vals = [_metric(summary, "holdout", "value_acc") for _, summary in summaries]
    value_exact_vals = [_metric(summary, "holdout", "value_exact_acc") for _, summary in summaries]
    cite_vals = [_metric(summary, "holdout", "cite_f1") for _, summary in summaries]
    max_value_exact_acc_jitter = _resolved_max_value_exact_acc_jitter(ns)
    jitter_checks = [
        ("holdout.value_acc_jitter", _jitter(value_vals), ns.max_value_acc_jitter),
        ("holdout.value_exact_acc_jitter", _jitter(value_exact_vals), max_value_exact_acc_jitter),
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
        "benchmark": "novel_continuity_reliability",
        "runs": [str(r) for r in run_dirs],
        "cite_stage": ns.cite_stage,
        "min_cite_f1": min_cite_f1,
        "provenance": {
            "release_stage_required": "target",
            "release_stage_approved": release_stage_approved,
            "allow_latest_nontarget": bool(ns.allow_latest_nontarget),
            "require_canary_ok": require_canary_ok,
        },
        "status": status,
        "failures": failures,
        "jitter": {
            "holdout_value_acc": _jitter(value_vals),
            "holdout_value_exact_acc": _jitter(value_exact_vals),
            "holdout_exact_acc": _jitter(value_exact_vals),
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
