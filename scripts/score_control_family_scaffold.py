from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from goldevidencebench.util import read_jsonl

_FAMILIES = (
    "rpa_mode_switch",
    "intent_spec_layer",
    "noise_escalation",
    "implication_coherence",
    "agency_preserving_substitution",
)


def _parse_args(argv: list[str] | None = None, *, forced_family: str | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score control-layer scaffold families with common and family-specific metrics."
    )
    if forced_family is None:
        parser.add_argument("--family", choices=_FAMILIES, required=True)
    else:
        parser.add_argument("--family", choices=_FAMILIES, default=forced_family)

    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--preds", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--rows-out", type=Path, default=None)

    parser.add_argument("--min-value-acc", type=float, default=None)
    parser.add_argument("--min-exact-acc", type=float, default=None)
    parser.add_argument("--min-cite-f1", type=float, default=None)

    # rpa_mode_switch thresholds
    parser.add_argument("--min-mode-switch-accuracy", type=float, default=None)
    parser.add_argument("--max-premature-act-rate", type=float, default=None)
    parser.add_argument("--max-unnecessary-plan-rate", type=float, default=None)
    parser.add_argument("--min-verify-gate-rate", type=float, default=None)

    # intent_spec_layer thresholds
    parser.add_argument("--min-clarification-precision", type=float, default=None)
    parser.add_argument("--min-clarification-recall", type=float, default=None)
    parser.add_argument("--min-clarification-f1", type=float, default=None)
    parser.add_argument("--max-user-burden-score", type=float, default=None)
    parser.add_argument("--min-downstream-error-reduction", type=float, default=None)

    # noise_escalation thresholds
    parser.add_argument("--min-noise-control-accuracy", type=float, default=None)
    parser.add_argument("--max-noise-slope", type=float, default=None)
    parser.add_argument("--max-recovery-latency", type=float, default=None)
    parser.add_argument("--max-irrecoverable-drift-rate", type=float, default=None)

    # implication_coherence thresholds
    parser.add_argument("--min-implication-consistency-rate", type=float, default=None)
    parser.add_argument("--min-dependency-coverage", type=float, default=None)
    parser.add_argument("--min-contradiction-repair-rate", type=float, default=None)
    parser.add_argument("--min-causal-precision", type=float, default=None)
    parser.add_argument("--max-propagation-latency-steps", type=float, default=None)
    parser.add_argument("--max-implication-break-rate", type=float, default=None)
    parser.add_argument("--min-ic-score", type=float, default=None)

    # agency_preserving_substitution thresholds
    parser.add_argument("--min-substitution-transparency-rate", type=float, default=None)
    parser.add_argument("--max-unauthorized-substitution-rate", type=float, default=None)
    parser.add_argument("--min-intent-preservation-score", type=float, default=None)
    parser.add_argument("--max-agency-loss-error-rate", type=float, default=None)
    parser.add_argument("--min-recovery-success-rate", type=float, default=None)

    return parser.parse_args(argv)


def _norm(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value.strip().lower()
    return json.dumps(value, sort_keys=True, ensure_ascii=True)


def _support_set(value: Any) -> set[str]:
    if isinstance(value, list):
        return {str(v) for v in value if v is not None}
    if value is None:
        return set()
    return {str(value)}


def _citation_prf(pred: set[str], gold: set[str]) -> tuple[float, float, float]:
    inter = len(pred & gold)
    precision = inter / len(pred) if pred else (1.0 if not gold else 0.0)
    recall = inter / len(gold) if gold else 1.0
    f1 = (2.0 * precision * recall / (precision + recall)) if precision > 0 and recall > 0 else 0.0
    return precision, recall, f1


def _mean(values: list[float]) -> float:
    return (sum(values) / len(values)) if values else 0.0


def _split_contract(value: str) -> tuple[str, str]:
    parts = [p.strip().lower() for p in value.split("|")]
    if len(parts) >= 2:
        return parts[0], parts[1]
    if len(parts) == 1:
        return parts[0], ""
    return "", ""


def _score_rpa_rows(rows: list[dict[str, Any]]) -> tuple[dict[str, float], list[dict[str, Any]], Counter[str]]:
    mode_correct: list[float] = []
    decision_correct: list[float] = []
    premature_act: list[float] = []
    unnecessary_plan: list[float] = []
    verify_gate: list[float] = []
    verify_gate_den = 0
    failure_modes: Counter[str] = Counter()

    for row in rows:
        meta = row["meta"]
        pred_norm = row["pred_norm"]
        value_ok = row["value_ok"]
        gold_mode = str(meta.get("gold_mode", "")).strip().lower()
        gold_decision = str(meta.get("gold_decision", "")).strip().lower()
        pred_mode, pred_decision = _split_contract(pred_norm)
        requires_plan = bool(meta.get("requires_plan", False))
        act_allowed = bool(meta.get("act_allowed", False))

        mode_ok = float(pred_mode == gold_mode)
        decision_ok = float(pred_decision == gold_decision)
        prem = float(pred_mode == "act" and not act_allowed)
        unplan = float(pred_mode == "plan" and not requires_plan)
        verify_ok = float(pred_decision == "verify")

        mode_correct.append(mode_ok)
        decision_correct.append(decision_ok)
        premature_act.append(prem)
        unnecessary_plan.append(unplan)

        if requires_plan:
            verify_gate.append(verify_ok)
            verify_gate_den += 1

        if value_ok < 1.0:
            if prem > 0:
                failure_modes["premature_act"] += 1
                row["failure_mode_id"] = "premature_act"
            elif unplan > 0:
                failure_modes["unnecessary_plan"] += 1
                row["failure_mode_id"] = "unnecessary_plan"
            elif mode_ok < 1.0:
                failure_modes["mode_switch_error"] += 1
                row["failure_mode_id"] = "mode_switch_error"
            elif decision_ok < 1.0:
                failure_modes["decision_error"] += 1
                row["failure_mode_id"] = "decision_error"
            else:
                failure_modes["contract_error"] += 1
                row["failure_mode_id"] = "contract_error"
        else:
            row["failure_mode_id"] = None

    means = {
        "mode_switch_accuracy": _mean(mode_correct),
        "decision_accuracy": _mean(decision_correct),
        "premature_act_rate": _mean(premature_act),
        "unnecessary_plan_rate": _mean(unnecessary_plan),
        "verify_gate_rate": _mean(verify_gate),
        "verify_gate_count": float(verify_gate_den),
    }
    return means, rows, failure_modes


def _score_intent_rows(rows: list[dict[str, Any]]) -> tuple[dict[str, float], list[dict[str, Any]], Counter[str]]:
    tp = 0.0
    fp = 0.0
    fn = 0.0
    burdens: list[float] = []
    reductions: list[float] = []
    asks: list[float] = []
    failure_modes: Counter[str] = Counter()

    for row in rows:
        meta = row["meta"]
        pred_norm = row["pred_norm"]
        value_ok = row["value_ok"]
        ambiguous = bool(meta.get("ambiguous", False))
        error_if_guess = float(meta.get("downstream_error_if_guess", 0.0) or 0.0)
        pred_ask = pred_norm.startswith("ask")

        if pred_ask:
            asks.append(1.0)
            if ambiguous:
                tp += 1.0
            else:
                fp += 1.0
        else:
            asks.append(0.0)
            if ambiguous:
                fn += 1.0

        if pred_ask and ambiguous:
            burdens.append(0.25)
            reductions.append(error_if_guess)
        elif pred_ask and not ambiguous:
            burdens.append(1.0)
        else:
            burdens.append(0.0)
            if ambiguous:
                reductions.append(0.0)

        if value_ok < 1.0:
            if ambiguous and not pred_ask:
                failure_modes["missed_clarification"] += 1
                row["failure_mode_id"] = "missed_clarification"
            elif (not ambiguous) and pred_ask:
                failure_modes["unnecessary_clarification"] += 1
                row["failure_mode_id"] = "unnecessary_clarification"
            else:
                failure_modes["intent_action_error"] += 1
                row["failure_mode_id"] = "intent_action_error"
        else:
            row["failure_mode_id"] = None

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2.0 * precision * recall / (precision + recall)) if precision > 0 and recall > 0 else 0.0
    means = {
        "clarification_precision": precision,
        "clarification_recall": recall,
        "clarification_f1": f1,
        "clarification_rate": _mean(asks),
        "user_burden_score": _mean(burdens),
        "downstream_error_reduction": _mean(reductions),
    }
    return means, rows, failure_modes


def _score_noise_rows(rows: list[dict[str, Any]]) -> tuple[dict[str, float], list[dict[str, Any]], Counter[str]]:
    control_oks: list[float] = []
    slopes: list[float] = []
    recoveries: list[float] = []
    drifts: list[float] = []
    failure_modes: Counter[str] = Counter()

    for row in rows:
        meta = row["meta"]
        value_ok = row["value_ok"] >= 1.0
        target_slope = float(meta.get("target_noise_slope", 0.5) or 0.5)
        target_latency = float(meta.get("target_recovery_latency", 4.0) or 4.0)
        irrecoverable_if_missed = bool(meta.get("irrecoverable_if_missed", False))

        slope = target_slope if value_ok else min(1.0, target_slope + 0.6)
        latency = target_latency if value_ok else (target_latency + 2.0)
        drift = 1.0 if ((not value_ok) and irrecoverable_if_missed) else 0.0

        control_oks.append(1.0 if value_ok else 0.0)
        slopes.append(slope)
        recoveries.append(latency)
        drifts.append(drift)

        if not value_ok:
            if irrecoverable_if_missed:
                failure_modes["missed_irrecoverable_guard"] += 1
                row["failure_mode_id"] = "missed_irrecoverable_guard"
            else:
                failure_modes["recovery_delay_error"] += 1
                row["failure_mode_id"] = "recovery_delay_error"
        else:
            row["failure_mode_id"] = None

    means = {
        "noise_control_accuracy": _mean(control_oks),
        "noise_slope": _mean(slopes),
        "recovery_latency": _mean(recoveries),
        "irrecoverable_drift_rate": _mean(drifts),
        "recovery_success_rate": 1.0 - _mean(drifts),
    }
    return means, rows, failure_modes


def _score_ic_rows(rows: list[dict[str, Any]]) -> tuple[dict[str, float], list[dict[str, Any]], Counter[str]]:
    consistency: list[float] = []
    dep_coverage_values: list[float] = []
    contradiction_repair_values: list[float] = []
    causal_precision_values: list[float] = []
    propagation_latencies: list[float] = []
    implication_break_values: list[float] = []
    failure_modes: Counter[str] = Counter()

    for row in rows:
        meta = row["meta"]
        value_ok = row["value_ok"] >= 1.0

        dependency_required = bool(meta.get("dependency_required", False))
        contradiction_detected = bool(meta.get("contradiction_detected", False))
        causal_precision_required = bool(meta.get("causal_precision_required", False))
        propagation_required = bool(meta.get("propagation_required", False))
        target_latency = float(meta.get("target_propagation_latency_steps", 3.0) or 3.0)
        implication_break_if_missed = bool(meta.get("implication_break_if_missed", False))

        consistency.append(1.0 if value_ok else 0.0)
        if dependency_required:
            dep_coverage_values.append(1.0 if value_ok else 0.0)
        if contradiction_detected:
            contradiction_repair_values.append(1.0 if value_ok else 0.0)
        if causal_precision_required:
            causal_precision_values.append(1.0 if value_ok else 0.0)

        propagation_latencies.append(target_latency if value_ok else min(12.0, target_latency + 3.0))
        implication_break_values.append(
            1.0 if ((not value_ok) and implication_break_if_missed) else 0.0
        )

        if value_ok:
            row["failure_mode_id"] = None
            continue
        if dependency_required:
            failure_modes["dependency_omission"] += 1
            row["failure_mode_id"] = "dependency_omission"
        elif contradiction_detected:
            failure_modes["contradiction_not_repaired"] += 1
            row["failure_mode_id"] = "contradiction_not_repaired"
        elif causal_precision_required:
            failure_modes["causal_overclaim"] += 1
            row["failure_mode_id"] = "causal_overclaim"
        elif propagation_required:
            failure_modes["propagation_miss"] += 1
            row["failure_mode_id"] = "propagation_miss"
        else:
            failure_modes["implication_inconsistency"] += 1
            row["failure_mode_id"] = "implication_inconsistency"

    implication_consistency_rate = _mean(consistency)
    dependency_coverage = _mean(dep_coverage_values) if dep_coverage_values else 1.0
    contradiction_repair_rate = _mean(contradiction_repair_values) if contradiction_repair_values else 1.0
    causal_precision = _mean(causal_precision_values) if causal_precision_values else 1.0
    propagation_latency_steps = _mean(propagation_latencies)
    implication_break_rate = _mean(implication_break_values)
    ic_score = (
        0.30 * implication_consistency_rate
        + 0.20 * dependency_coverage
        + 0.20 * contradiction_repair_rate
        + 0.15 * causal_precision
        + 0.15 * (1.0 - implication_break_rate)
    )

    means = {
        "implication_consistency_rate": implication_consistency_rate,
        "dependency_coverage": dependency_coverage,
        "contradiction_repair_rate": contradiction_repair_rate,
        "causal_precision": causal_precision,
        "propagation_latency_steps": propagation_latency_steps,
        "implication_break_rate": implication_break_rate,
        "ic_score": ic_score,
    }
    return means, rows, failure_modes


def _score_aps_rows(rows: list[dict[str, Any]]) -> tuple[dict[str, float], list[dict[str, Any]], Counter[str]]:
    transparency_values: list[float] = []
    unauthorized_values: list[float] = []
    intent_preservation_values: list[float] = []
    agency_loss_error_values: list[float] = []
    recovery_success_values: list[float] = []
    failure_modes: Counter[str] = Counter()

    for row in rows:
        meta = row["meta"]
        value_ok = row["value_ok"] >= 1.0
        substitution_required = bool(meta.get("substitution_required", False))
        policy_mandated = bool(meta.get("policy_mandated", False))
        consent_required = bool(meta.get("consent_required", False))
        user_subdued = bool(meta.get("user_subdued", False))
        recovery_required = bool(meta.get("recovery_required", False))
        intent_target = float(meta.get("intent_preservation_target", 1.0) or 1.0)

        if substitution_required:
            transparency_values.append(1.0 if value_ok else 0.0)
        unauthorized_values.append(
            1.0
            if (
                substitution_required
                and (not policy_mandated)
                and consent_required
                and (not value_ok)
            )
            else 0.0
        )

        if value_ok:
            intent_preservation_values.append(intent_target)
        else:
            intent_preservation_values.append(max(0.0, intent_target - 0.55))

        if user_subdued:
            agency_loss_error_values.append(0.0 if value_ok else 1.0)
        if recovery_required:
            recovery_success_values.append(1.0 if value_ok else 0.0)

        if value_ok:
            row["failure_mode_id"] = None
            continue

        if substitution_required and user_subdued:
            failure_modes["substitution_under_subdual"] += 1
            row["failure_mode_id"] = "substitution_under_subdual"
        elif substitution_required and (not policy_mandated) and consent_required:
            failure_modes["silent_substitution"] += 1
            row["failure_mode_id"] = "silent_substitution"
        elif substitution_required and policy_mandated:
            failure_modes["policy_mask_misuse"] += 1
            row["failure_mode_id"] = "policy_mask_misuse"
        elif recovery_required:
            failure_modes["recovery_failure"] += 1
            row["failure_mode_id"] = "recovery_failure"
        else:
            failure_modes["intent_substitution_error"] += 1
            row["failure_mode_id"] = "intent_substitution_error"

    means = {
        "substitution_transparency_rate": _mean(transparency_values) if transparency_values else 1.0,
        "unauthorized_substitution_rate": _mean(unauthorized_values),
        "intent_preservation_score": _mean(intent_preservation_values),
        "agency_loss_error_rate": _mean(agency_loss_error_values) if agency_loss_error_values else 0.0,
        "recovery_success_rate": _mean(recovery_success_values) if recovery_success_values else 1.0,
    }
    return means, rows, failure_modes


def _apply_thresholds(summary: dict[str, Any], ns: argparse.Namespace) -> list[str]:
    means = summary.get("means", {})
    failures: list[str] = []

    common_checks = [
        ("value_acc", ns.min_value_acc, ">="),
        ("exact_acc", ns.min_exact_acc, ">="),
        ("cite_f1", ns.min_cite_f1, ">="),
    ]
    for metric, threshold, op in common_checks:
        if threshold is None:
            continue
        value = means.get(metric)
        ok = isinstance(value, (int, float)) and float(value) >= float(threshold)
        if op == "<=":
            ok = isinstance(value, (int, float)) and float(value) <= float(threshold)
        if not ok:
            failures.append(f"{metric} {op} {threshold}")

    family = ns.family
    family_checks: list[tuple[str, float | None, str]] = []
    if family == "rpa_mode_switch":
        family_checks = [
            ("mode_switch_accuracy", ns.min_mode_switch_accuracy, ">="),
            ("premature_act_rate", ns.max_premature_act_rate, "<="),
            ("unnecessary_plan_rate", ns.max_unnecessary_plan_rate, "<="),
            ("verify_gate_rate", ns.min_verify_gate_rate, ">="),
        ]
    elif family == "intent_spec_layer":
        family_checks = [
            ("clarification_precision", ns.min_clarification_precision, ">="),
            ("clarification_recall", ns.min_clarification_recall, ">="),
            ("clarification_f1", ns.min_clarification_f1, ">="),
            ("user_burden_score", ns.max_user_burden_score, "<="),
            ("downstream_error_reduction", ns.min_downstream_error_reduction, ">="),
        ]
    elif family == "noise_escalation":
        family_checks = [
            ("noise_control_accuracy", ns.min_noise_control_accuracy, ">="),
            ("noise_slope", ns.max_noise_slope, "<="),
            ("recovery_latency", ns.max_recovery_latency, "<="),
            ("irrecoverable_drift_rate", ns.max_irrecoverable_drift_rate, "<="),
        ]
    elif family == "implication_coherence":
        family_checks = [
            ("implication_consistency_rate", ns.min_implication_consistency_rate, ">="),
            ("dependency_coverage", ns.min_dependency_coverage, ">="),
            ("contradiction_repair_rate", ns.min_contradiction_repair_rate, ">="),
            ("causal_precision", ns.min_causal_precision, ">="),
            ("propagation_latency_steps", ns.max_propagation_latency_steps, "<="),
            ("implication_break_rate", ns.max_implication_break_rate, "<="),
            ("ic_score", ns.min_ic_score, ">="),
        ]
    elif family == "agency_preserving_substitution":
        family_checks = [
            ("substitution_transparency_rate", ns.min_substitution_transparency_rate, ">="),
            ("unauthorized_substitution_rate", ns.max_unauthorized_substitution_rate, "<="),
            ("intent_preservation_score", ns.min_intent_preservation_score, ">="),
            ("agency_loss_error_rate", ns.max_agency_loss_error_rate, "<="),
            ("recovery_success_rate", ns.min_recovery_success_rate, ">="),
        ]

    for metric, threshold, op in family_checks:
        if threshold is None:
            continue
        value = means.get(metric)
        if op == ">=":
            ok = isinstance(value, (int, float)) and float(value) >= float(threshold)
        else:
            ok = isinstance(value, (int, float)) and float(value) <= float(threshold)
        if not ok:
            failures.append(f"{metric} {op} {threshold}")

    return failures


def _score(ns: argparse.Namespace) -> int:
    out_path = ns.out or (ns.preds.parent / f"{ns.family}_summary.json")

    data_rows = [row for row in read_jsonl(ns.data) if isinstance(row, dict)]
    pred_rows = [row for row in read_jsonl(ns.preds) if isinstance(row, dict)]
    preds_by_id = {str(row.get("id")): row for row in pred_rows if row.get("id") is not None}

    value_accs: list[float] = []
    exact_accs: list[float] = []
    cite_ps: list[float] = []
    cite_rs: list[float] = []
    cite_f1s: list[float] = []
    parse_rates: list[float] = []

    rows: list[dict[str, Any]] = []
    for data_row in data_rows:
        rid = str(data_row.get("id"))
        pred = preds_by_id.get(rid, {})
        gold = data_row.get("gold") if isinstance(data_row.get("gold"), dict) else {}
        meta = data_row.get("meta") if isinstance(data_row.get("meta"), dict) else {}

        pred_value = pred.get("value")
        has_value = "value" in pred
        parse_ok = has_value and ("output" not in pred)
        gold_norm = _norm(gold.get("value"))
        pred_norm = _norm(pred_value)
        value_ok = float(gold_norm == pred_norm)
        exact_ok = float(gold.get("value") == pred_value)

        gold_support = _support_set(gold.get("support_ids"))
        pred_support = _support_set(pred.get("support_ids"))
        cite_p, cite_r, cite_f1 = _citation_prf(pred_support, gold_support)

        value_accs.append(value_ok)
        exact_accs.append(exact_ok)
        cite_ps.append(cite_p)
        cite_rs.append(cite_r)
        cite_f1s.append(cite_f1)
        parse_rates.append(1.0 if parse_ok else 0.0)

        rows.append(
            {
                "id": rid,
                "profile": str(meta.get("profile", "")),
                "gold_value": gold.get("value"),
                "pred_value": pred_value,
                "value_ok": value_ok,
                "value_exact_ok": exact_ok,
                "exact_ok": exact_ok,
                "cite_p": cite_p,
                "cite_r": cite_r,
                "cite_f1": cite_f1,
                "parse_ok": bool(parse_ok),
                "gold_support_ids": sorted(gold_support),
                "pred_support_ids": sorted(pred_support),
                "pred_norm": pred_norm,
                "meta": meta,
            }
        )

    family_means: dict[str, float]
    family_failure_modes: Counter[str]
    if ns.family == "rpa_mode_switch":
        family_means, rows, family_failure_modes = _score_rpa_rows(rows)
    elif ns.family == "intent_spec_layer":
        family_means, rows, family_failure_modes = _score_intent_rows(rows)
    elif ns.family == "noise_escalation":
        family_means, rows, family_failure_modes = _score_noise_rows(rows)
    elif ns.family == "implication_coherence":
        family_means, rows, family_failure_modes = _score_ic_rows(rows)
    elif ns.family == "agency_preserving_substitution":
        family_means, rows, family_failure_modes = _score_aps_rows(rows)
    else:
        raise ValueError(f"Unsupported family: {ns.family}")

    means = {
        "value_acc": _mean(value_accs),
        "value_exact_acc": _mean(exact_accs),
        "exact_acc": _mean(exact_accs),  # Legacy alias: use value_exact_acc for clarity.
        "entailment": _mean(value_accs),
        "cite_p": _mean(cite_ps),
        "cite_r": _mean(cite_rs),
        "cite_f1": _mean(cite_f1s),
        "parse_rate": _mean(parse_rates),
    }
    means.update(family_means)

    summary: dict[str, Any] = {
        "benchmark": ns.family,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_path": str(ns.data),
        "preds_path": str(ns.preds),
        "rows_total": len(data_rows),
        "rows_scored": len(rows),
        "means": means,
        "metric_aliases": {
            "exact_acc": "value_exact_acc",
        },
        "metric_semantics": {
            "value_acc": "normalized value match",
            "value_exact_acc": "raw value equality only",
            "exact_acc": "legacy alias of value_exact_acc",
        },
        "failure_mode_ids": sorted(family_failure_modes.keys()),
        "failure_mode_counts": dict(sorted(family_failure_modes.items())),
    }

    thresholds: dict[str, float] = {}
    for key, value in vars(ns).items():
        if key.startswith("min_") or key.startswith("max_"):
            if isinstance(value, (int, float)):
                thresholds[key] = float(value)
    if thresholds:
        summary["thresholds"] = thresholds

    failures = _apply_thresholds(summary, ns)
    summary["failures"] = failures
    summary["status"] = "PASS" if not failures else "FAIL"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")

    status_line = (
        f"{ns.family}: n={summary['rows_scored']}"
        f" value_acc={means['value_acc']:.3f}"
        f" value_exact_acc={means['value_exact_acc']:.3f}"
        f" cite_f1={means['cite_f1']:.3f}"
    )
    if ns.family == "rpa_mode_switch":
        status_line += (
            f" mode_switch_accuracy={means['mode_switch_accuracy']:.3f}"
            f" premature_act_rate={means['premature_act_rate']:.3f}"
            f" unnecessary_plan_rate={means['unnecessary_plan_rate']:.3f}"
        )
    elif ns.family == "intent_spec_layer":
        status_line += (
            f" clar_precision={means['clarification_precision']:.3f}"
            f" clar_recall={means['clarification_recall']:.3f}"
            f" user_burden={means['user_burden_score']:.3f}"
        )
    elif ns.family == "noise_escalation":
        status_line += (
            f" noise_slope={means['noise_slope']:.3f}"
            f" recovery_latency={means['recovery_latency']:.3f}"
            f" irrecoverable_drift_rate={means['irrecoverable_drift_rate']:.3f}"
        )
    elif ns.family == "implication_coherence":
        status_line += (
            f" implication_consistency={means['implication_consistency_rate']:.3f}"
            f" dependency_coverage={means['dependency_coverage']:.3f}"
            f" contradiction_repair={means['contradiction_repair_rate']:.3f}"
            f" implication_break_rate={means['implication_break_rate']:.3f}"
            f" ic_score={means['ic_score']:.3f}"
        )
    elif ns.family == "agency_preserving_substitution":
        status_line += (
            f" substitution_transparency={means['substitution_transparency_rate']:.3f}"
            f" unauthorized_substitution={means['unauthorized_substitution_rate']:.3f}"
            f" intent_preservation={means['intent_preservation_score']:.3f}"
            f" agency_loss_error={means['agency_loss_error_rate']:.3f}"
            f" recovery_success={means['recovery_success_rate']:.3f}"
        )
    status_line += f" status={summary['status']}"
    print(status_line)

    if ns.rows_out is not None:
        ns.rows_out.parent.mkdir(parents=True, exist_ok=True)
        with ns.rows_out.open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=True) + "\n")
        print(f"Wrote {ns.rows_out}")

    return 0 if not failures else 1


def main(argv: list[str] | None = None) -> int:
    ns = _parse_args(argv)
    return _score(ns)


def main_for_family(family: str, argv: list[str] | None = None) -> int:
    ns = _parse_args(argv, forced_family=family)
    return _score(ns)


if __name__ == "__main__":
    raise SystemExit(main())
