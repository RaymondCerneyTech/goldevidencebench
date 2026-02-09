from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check reliability across epistemic_calibration_suite runs using "
            "hard-gate pass, holdout floors, and jitter bounds."
        )
    )
    parser.add_argument("--run-dirs", nargs="+", required=True)
    parser.add_argument("--min-runs", type=int, default=2)
    parser.add_argument("--stage", choices=("observe", "ramp", "target", "custom"), default="observe")
    parser.add_argument("--min-kkyi", type=float, default=None)
    parser.add_argument("--max-overclaim-rate", type=float, default=None)
    parser.add_argument("--min-abstain-f1", type=float, default=None)
    parser.add_argument("--max-ece", type=float, default=None)
    parser.add_argument("--max-brier", type=float, default=None)
    parser.add_argument("--min-parse-rate", type=float, default=None)
    parser.add_argument("--min-confidence-provided-rate", type=float, default=None)
    parser.add_argument("--max-confidence-proxy-used-rate", type=float, default=None)
    parser.add_argument("--min-selective-accuracy-at-coverage", type=float, default=None)
    parser.add_argument("--min-needed-info-recall", type=float, default=None)
    parser.add_argument("--max-kkyi-jitter", type=float, default=0.05)
    parser.add_argument("--max-overclaim-jitter", type=float, default=0.05)
    parser.add_argument("--max-abstain-f1-jitter", type=float, default=0.05)
    parser.add_argument("--max-ece-jitter", type=float, default=0.05)
    parser.add_argument("--max-canary-kkyi", type=float, default=None)
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


def _canary_kkyi(summary: dict[str, Any]) -> float:
    raw = summary.get("canary_kkyi")
    if isinstance(raw, (int, float)):
        return float(raw)
    return _metric(summary, "canary", "kkyi")


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
        summary_path = run_dir / "epistemic_calibration_suite_summary.json"
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
            "kkyi": 0.30,
            "overclaim_rate": 0.75,
            "abstain_f1": 0.10,
            "ece": 0.60,
            "brier": 0.60,
            "parse_rate": 0.00,
            "confidence_provided_rate": 0.00,
            "confidence_proxy_used_rate": 1.00,
            "selective_accuracy_at_coverage": 0.35,
            "needed_info_recall": 0.20,
            "canary_kkyi_max": 0.75,
        },
        "ramp": {
            "kkyi": 0.55,
            "overclaim_rate": 0.35,
            "abstain_f1": 0.45,
            "ece": 0.35,
            "brier": 0.40,
            "parse_rate": 0.00,
            "confidence_provided_rate": 0.00,
            "confidence_proxy_used_rate": 1.00,
            "selective_accuracy_at_coverage": 0.65,
            "needed_info_recall": 0.50,
            "canary_kkyi_max": 0.80,
        },
        "target": {
            "kkyi": 0.72,
            "overclaim_rate": 0.15,
            "abstain_f1": 0.70,
            "ece": 0.20,
            "brier": 0.25,
            "parse_rate": 1.00,
            "confidence_provided_rate": 1.00,
            "confidence_proxy_used_rate": 0.00,
            "selective_accuracy_at_coverage": 0.85,
            "needed_info_recall": 0.75,
            "canary_kkyi_max": 0.85,
        },
        "custom": {
            "kkyi": 0.0,
            "overclaim_rate": 1.0,
            "abstain_f1": 0.0,
            "ece": 1.0,
            "brier": 1.0,
            "parse_rate": 0.00,
            "confidence_provided_rate": 0.00,
            "confidence_proxy_used_rate": 1.00,
            "selective_accuracy_at_coverage": 0.0,
            "needed_info_recall": 0.0,
            "canary_kkyi_max": 0.75,
        },
    }
    selected = stage_floors[ns.stage]
    max_canary_kkyi = ns.max_canary_kkyi if ns.max_canary_kkyi is not None else selected["canary_kkyi_max"]
    floors = {
        "kkyi": ns.min_kkyi if ns.min_kkyi is not None else selected["kkyi"],
        "overclaim_rate": (
            ns.max_overclaim_rate if ns.max_overclaim_rate is not None else selected["overclaim_rate"]
        ),
        "abstain_f1": ns.min_abstain_f1 if ns.min_abstain_f1 is not None else selected["abstain_f1"],
        "ece": ns.max_ece if ns.max_ece is not None else selected["ece"],
        "brier": ns.max_brier if ns.max_brier is not None else selected["brier"],
        "parse_rate": ns.min_parse_rate if ns.min_parse_rate is not None else selected["parse_rate"],
        "confidence_provided_rate": (
            ns.min_confidence_provided_rate
            if ns.min_confidence_provided_rate is not None
            else selected["confidence_provided_rate"]
        ),
        "confidence_proxy_used_rate": (
            ns.max_confidence_proxy_used_rate
            if ns.max_confidence_proxy_used_rate is not None
            else selected["confidence_proxy_used_rate"]
        ),
        "selective_accuracy_at_coverage": (
            ns.min_selective_accuracy_at_coverage
            if ns.min_selective_accuracy_at_coverage is not None
            else selected["selective_accuracy_at_coverage"]
        ),
        "needed_info_recall": (
            ns.min_needed_info_recall if ns.min_needed_info_recall is not None else selected["needed_info_recall"]
        ),
    }

    lines: list[str] = ["Epistemic calibration reliability check", f"Runs: {len(summaries)}", f"Stage: {ns.stage}"]
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

        canary_kkyi = _canary_kkyi(summary)
        canary_ok = (canary_kkyi == canary_kkyi) and (canary_kkyi <= max_canary_kkyi)
        lines.append(f"[{'PASS' if canary_ok else 'FAIL'}] {run_dir}: canary.kkyi={canary_kkyi:.6f} <= {max_canary_kkyi:.6f}")
        if not canary_ok:
            failures.append(f"{run_dir}: canary.kkyi > {max_canary_kkyi}")

    floor_checks = [
        ("kkyi", floors["kkyi"], ">="),
        ("overclaim_rate", floors["overclaim_rate"], "<="),
        ("abstain_f1", floors["abstain_f1"], ">="),
        ("ece", floors["ece"], "<="),
        ("brier", floors["brier"], "<="),
        ("parse_rate", floors["parse_rate"], ">="),
        ("confidence_provided_rate", floors["confidence_provided_rate"], ">="),
        ("confidence_proxy_used_rate", floors["confidence_proxy_used_rate"], "<="),
        ("selective_accuracy_at_coverage", floors["selective_accuracy_at_coverage"], ">="),
        ("needed_info_recall", floors["needed_info_recall"], ">="),
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

    kkyi_vals = [_metric(s, "holdout", "kkyi") for _, s in summaries]
    overclaim_vals = [_metric(s, "holdout", "overclaim_rate") for _, s in summaries]
    abstain_f1_vals = [_metric(s, "holdout", "abstain_f1") for _, s in summaries]
    ece_vals = [_metric(s, "holdout", "ece") for _, s in summaries]
    jitter_checks = [
        ("holdout.kkyi_jitter", _jitter(kkyi_vals), ns.max_kkyi_jitter),
        ("holdout.overclaim_rate_jitter", _jitter(overclaim_vals), ns.max_overclaim_jitter),
        ("holdout.abstain_f1_jitter", _jitter(abstain_f1_vals), ns.max_abstain_f1_jitter),
        ("holdout.ece_jitter", _jitter(ece_vals), ns.max_ece_jitter),
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
        "benchmark": "epistemic_calibration_suite_reliability",
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
            "holdout_kkyi": _jitter(kkyi_vals),
            "holdout_overclaim_rate": _jitter(overclaim_vals),
            "holdout_abstain_f1": _jitter(abstain_f1_vals),
            "holdout_ece": _jitter(ece_vals),
        },
        "max_canary_kkyi": max_canary_kkyi,
    }
    if ns.out is not None:
        ns.out.parent.mkdir(parents=True, exist_ok=True)
        ns.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote {ns.out}")

    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
