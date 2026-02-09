from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

_FAMILIES = ("rpa_mode_switch", "intent_spec_layer", "noise_escalation")


def _parse_args(argv: list[str] | None = None, *, forced_family: str | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check reliability across control-layer scaffold families with stage floors and jitter bounds."
    )
    if forced_family is None:
        parser.add_argument("--family", choices=_FAMILIES, required=True)
    else:
        parser.add_argument("--family", choices=_FAMILIES, default=forced_family)

    parser.add_argument("--run-dirs", nargs="+", required=True)
    parser.add_argument("--min-runs", type=int, default=2)
    parser.add_argument("--stage", choices=("observe", "ramp", "target", "custom"), default="observe")

    parser.add_argument("--min-value-acc", type=float, default=None)
    parser.add_argument("--min-exact-acc", type=float, default=None)
    parser.add_argument("--min-cite-f1", type=float, default=None)

    parser.add_argument("--min-mode-switch-accuracy", type=float, default=None)
    parser.add_argument("--max-premature-act-rate", type=float, default=None)
    parser.add_argument("--max-unnecessary-plan-rate", type=float, default=None)
    parser.add_argument("--min-verify-gate-rate", type=float, default=None)

    parser.add_argument("--min-clarification-precision", type=float, default=None)
    parser.add_argument("--min-clarification-recall", type=float, default=None)
    parser.add_argument("--min-clarification-f1", type=float, default=None)
    parser.add_argument("--max-user-burden-score", type=float, default=None)
    parser.add_argument("--min-downstream-error-reduction", type=float, default=None)

    parser.add_argument("--min-noise-control-accuracy", type=float, default=None)
    parser.add_argument("--max-noise-slope", type=float, default=None)
    parser.add_argument("--max-recovery-latency", type=float, default=None)
    parser.add_argument("--max-irrecoverable-drift-rate", type=float, default=None)

    parser.add_argument("--max-value-acc-jitter", type=float, default=0.05)
    parser.add_argument("--max-exact-acc-jitter", type=float, default=0.05)
    parser.add_argument("--max-cite-f1-jitter", type=float, default=0.05)
    parser.add_argument("--max-mode-switch-jitter", type=float, default=0.05)
    parser.add_argument("--max-premature-act-jitter", type=float, default=0.05)
    parser.add_argument("--max-unnecessary-plan-jitter", type=float, default=0.05)
    parser.add_argument("--max-clarification-precision-jitter", type=float, default=0.05)
    parser.add_argument("--max-clarification-recall-jitter", type=float, default=0.05)
    parser.add_argument("--max-user-burden-jitter", type=float, default=0.05)
    parser.add_argument("--max-noise-slope-jitter", type=float, default=0.05)
    parser.add_argument("--max-recovery-latency-jitter", type=float, default=0.05)
    parser.add_argument("--max-irrecoverable-drift-jitter", type=float, default=0.05)
    parser.add_argument("--max-canary-exact-rate", type=float, default=0.90)

    parser.add_argument(
        "--allow-latest-nontarget",
        action="store_true",
        help="Allow writing *_latest.json when stage is not target.",
    )
    parser.add_argument("--out", type=Path, default=None)
    return parser.parse_args(argv)


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


def _family_stage_floors(family: str, stage: str) -> dict[str, float]:
    by_family = {
        "rpa_mode_switch": {
            "observe": {
                "value_acc": 0.55,
                "exact_acc": 0.55,
                "cite_f1": 0.35,
                "mode_switch_accuracy": 0.55,
                "premature_act_rate": 0.45,
                "unnecessary_plan_rate": 0.45,
                "verify_gate_rate": 0.30,
            },
            "ramp": {
                "value_acc": 0.75,
                "exact_acc": 0.75,
                "cite_f1": 0.55,
                "mode_switch_accuracy": 0.75,
                "premature_act_rate": 0.25,
                "unnecessary_plan_rate": 0.25,
                "verify_gate_rate": 0.55,
            },
            "target": {
                "value_acc": 0.90,
                "exact_acc": 0.90,
                "cite_f1": 0.80,
                "mode_switch_accuracy": 0.90,
                "premature_act_rate": 0.10,
                "unnecessary_plan_rate": 0.10,
                "verify_gate_rate": 0.80,
            },
            "custom": {
                "value_acc": 0.0,
                "exact_acc": 0.0,
                "cite_f1": 0.0,
                "mode_switch_accuracy": 0.0,
                "premature_act_rate": 1.0,
                "unnecessary_plan_rate": 1.0,
                "verify_gate_rate": 0.0,
            },
        },
        "intent_spec_layer": {
            "observe": {
                "value_acc": 0.55,
                "exact_acc": 0.55,
                "cite_f1": 0.35,
                "clarification_precision": 0.50,
                "clarification_recall": 0.50,
                "clarification_f1": 0.45,
                "user_burden_score": 0.70,
                "downstream_error_reduction": 0.40,
            },
            "ramp": {
                "value_acc": 0.75,
                "exact_acc": 0.75,
                "cite_f1": 0.55,
                "clarification_precision": 0.70,
                "clarification_recall": 0.70,
                "clarification_f1": 0.70,
                "user_burden_score": 0.45,
                "downstream_error_reduction": 0.65,
            },
            "target": {
                "value_acc": 0.90,
                "exact_acc": 0.90,
                "cite_f1": 0.80,
                "clarification_precision": 0.90,
                "clarification_recall": 0.90,
                "clarification_f1": 0.90,
                "user_burden_score": 0.20,
                "downstream_error_reduction": 0.84,
            },
            "custom": {
                "value_acc": 0.0,
                "exact_acc": 0.0,
                "cite_f1": 0.0,
                "clarification_precision": 0.0,
                "clarification_recall": 0.0,
                "clarification_f1": 0.0,
                "user_burden_score": 1.0,
                "downstream_error_reduction": 0.0,
            },
        },
        "noise_escalation": {
            "observe": {
                "value_acc": 0.55,
                "exact_acc": 0.55,
                "cite_f1": 0.35,
                "noise_control_accuracy": 0.55,
                "noise_slope": 0.75,
                "recovery_latency": 5.0,
                "irrecoverable_drift_rate": 0.45,
            },
            "ramp": {
                "value_acc": 0.75,
                "exact_acc": 0.75,
                "cite_f1": 0.55,
                "noise_control_accuracy": 0.75,
                "noise_slope": 0.45,
                "recovery_latency": 3.5,
                "irrecoverable_drift_rate": 0.25,
            },
            "target": {
                "value_acc": 0.90,
                "exact_acc": 0.90,
                "cite_f1": 0.80,
                "noise_control_accuracy": 0.90,
                "noise_slope": 0.20,
                "recovery_latency": 2.0,
                "irrecoverable_drift_rate": 0.10,
            },
            "custom": {
                "value_acc": 0.0,
                "exact_acc": 0.0,
                "cite_f1": 0.0,
                "noise_control_accuracy": 0.0,
                "noise_slope": 1.0,
                "recovery_latency": 999.0,
                "irrecoverable_drift_rate": 1.0,
            },
        },
    }
    return dict(by_family[family][stage])


def _resolve_floors(ns: argparse.Namespace) -> dict[str, float]:
    floors = _family_stage_floors(ns.family, ns.stage)
    overrides = {
        "value_acc": ns.min_value_acc,
        "exact_acc": ns.min_exact_acc,
        "cite_f1": ns.min_cite_f1,
        "mode_switch_accuracy": ns.min_mode_switch_accuracy,
        "premature_act_rate": ns.max_premature_act_rate,
        "unnecessary_plan_rate": ns.max_unnecessary_plan_rate,
        "verify_gate_rate": ns.min_verify_gate_rate,
        "clarification_precision": ns.min_clarification_precision,
        "clarification_recall": ns.min_clarification_recall,
        "clarification_f1": ns.min_clarification_f1,
        "user_burden_score": ns.max_user_burden_score,
        "downstream_error_reduction": ns.min_downstream_error_reduction,
        "noise_control_accuracy": ns.min_noise_control_accuracy,
        "noise_slope": ns.max_noise_slope,
        "recovery_latency": ns.max_recovery_latency,
        "irrecoverable_drift_rate": ns.max_irrecoverable_drift_rate,
    }
    for key, value in overrides.items():
        if value is not None:
            floors[key] = float(value)
    return floors


def _metric_ops(family: str) -> list[tuple[str, str]]:
    common = [("value_acc", ">="), ("exact_acc", ">="), ("cite_f1", ">=")]
    if family == "rpa_mode_switch":
        return common + [
            ("mode_switch_accuracy", ">="),
            ("premature_act_rate", "<="),
            ("unnecessary_plan_rate", "<="),
            ("verify_gate_rate", ">="),
        ]
    if family == "intent_spec_layer":
        return common + [
            ("clarification_precision", ">="),
            ("clarification_recall", ">="),
            ("clarification_f1", ">="),
            ("user_burden_score", "<="),
            ("downstream_error_reduction", ">="),
        ]
    return common + [
        ("noise_control_accuracy", ">="),
        ("noise_slope", "<="),
        ("recovery_latency", "<="),
        ("irrecoverable_drift_rate", "<="),
    ]


def _jitter_specs(ns: argparse.Namespace) -> list[tuple[str, float, str]]:
    specs: list[tuple[str, float, str]] = [
        ("value_acc", ns.max_value_acc_jitter, "holdout.value_acc_jitter"),
        ("exact_acc", ns.max_exact_acc_jitter, "holdout.exact_acc_jitter"),
        ("cite_f1", ns.max_cite_f1_jitter, "holdout.cite_f1_jitter"),
    ]
    if ns.family == "rpa_mode_switch":
        specs.extend(
            [
                ("mode_switch_accuracy", ns.max_mode_switch_jitter, "holdout.mode_switch_accuracy_jitter"),
                ("premature_act_rate", ns.max_premature_act_jitter, "holdout.premature_act_rate_jitter"),
                ("unnecessary_plan_rate", ns.max_unnecessary_plan_jitter, "holdout.unnecessary_plan_rate_jitter"),
            ]
        )
    elif ns.family == "intent_spec_layer":
        specs.extend(
            [
                ("clarification_precision", ns.max_clarification_precision_jitter, "holdout.clarification_precision_jitter"),
                ("clarification_recall", ns.max_clarification_recall_jitter, "holdout.clarification_recall_jitter"),
                ("user_burden_score", ns.max_user_burden_jitter, "holdout.user_burden_score_jitter"),
            ]
        )
    elif ns.family == "noise_escalation":
        specs.extend(
            [
                ("noise_slope", ns.max_noise_slope_jitter, "holdout.noise_slope_jitter"),
                ("recovery_latency", ns.max_recovery_latency_jitter, "holdout.recovery_latency_jitter"),
                ("irrecoverable_drift_rate", ns.max_irrecoverable_drift_jitter, "holdout.irrecoverable_drift_rate_jitter"),
            ]
        )
    return specs


def _run_check(ns: argparse.Namespace) -> int:
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
    summary_name = f"{ns.family}_summary.json"
    for run_dir in run_dirs:
        summary_path = run_dir / summary_name
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

    floors = _resolve_floors(ns)
    checks = _metric_ops(ns.family)

    title = ns.family.replace("_", " ")
    lines: list[str] = [f"{title} reliability check", f"Runs: {len(summaries)}", f"Stage: {ns.stage}"]
    failures: list[str] = []

    for run_dir, summary in summaries:
        top = summary.get("hard_gate_status")
        top_ok = top == "PASS"
        lines.append(f"[{'PASS' if top_ok else 'FAIL'}] {run_dir}: hard_gate_status={top}")
        if not top_ok:
            failures.append(f"{run_dir}: hard_gate_status != PASS")

        for split in ("anchors", "holdout"):
            split_ok = _is_pass(summary, split)
            lines.append(f"[{'PASS' if split_ok else 'FAIL'}] {run_dir}: {split}.status={summary.get(split, {}).get('status')}")
            if not split_ok:
                failures.append(f"{run_dir}: {split}.status != PASS")

        canary_exact = _canary_exact(summary)
        canary_ok = (canary_exact == canary_exact) and (canary_exact <= ns.max_canary_exact_rate)
        lines.append(
            f"[{'PASS' if canary_ok else 'FAIL'}] {run_dir}: canary.exact_rate={canary_exact:.6f} <= {ns.max_canary_exact_rate:.6f}"
        )
        if not canary_ok:
            failures.append(f"{run_dir}: canary.exact_rate > {ns.max_canary_exact_rate}")

    for run_dir, summary in summaries:
        for metric, op in checks:
            threshold = floors[metric]
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

    jitter_payload: dict[str, float] = {}
    for metric, max_allowed, label in _jitter_specs(ns):
        values = [_metric(summary, "holdout", metric) for _, summary in summaries]
        jitter = _jitter(values)
        jitter_payload[label] = jitter
        ok = (jitter == jitter) and (jitter <= max_allowed)
        lines.append(f"[{'PASS' if ok else 'FAIL'}] {label}={jitter:.6f} <= {max_allowed:.6f}")
        if not ok:
            failures.append(f"{label} > {max_allowed}")

    status = "PASS" if not failures else "FAIL"
    lines.append(f"RESULT: {status}")
    print("\n".join(lines))

    payload = {
        "benchmark": f"{ns.family}_reliability",
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
        "jitter": jitter_payload,
        "max_canary_exact_rate": ns.max_canary_exact_rate,
    }
    if ns.out is not None:
        ns.out.parent.mkdir(parents=True, exist_ok=True)
        ns.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote {ns.out}")

    return 0 if status == "PASS" else 1


def main(argv: list[str] | None = None) -> int:
    ns = _parse_args(argv)
    return _run_check(ns)


def main_for_family(family: str, argv: list[str] | None = None) -> int:
    ns = _parse_args(argv, forced_family=family)
    return _run_check(ns)


if __name__ == "__main__":
    raise SystemExit(main())
