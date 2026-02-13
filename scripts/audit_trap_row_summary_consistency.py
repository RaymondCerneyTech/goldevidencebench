from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
from typing import Any

from goldevidencebench.util import read_jsonl


CONTROL_FAMILIES = {
    "rpa_mode_switch",
    "intent_spec_layer",
    "noise_escalation",
    "implication_coherence",
    "agency_preserving_substitution",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit trap-family run artifacts by recomputing split metrics from rows and "
            "verifying consistency with summary.means."
        )
    )
    parser.add_argument(
        "--run-dirs",
        nargs="+",
        required=True,
        help="Run directories containing family summary + *_rows.jsonl artifacts.",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=1e-6,
        help="Absolute tolerance for row-vs-summary metric comparisons.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail when a split cannot be audited (missing rows or unsupported schema).",
    )
    parser.add_argument("--out", type=Path, default=None)
    return parser.parse_args()


def _read_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid JSON object: {path}")
    return raw


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        as_float = float(value)
        if math.isfinite(as_float):
            return as_float
    return None


def _mean(values: list[float]) -> float:
    return (sum(values) / len(values)) if values else 0.0


def _mean_field(rows: list[dict[str, Any]], key: str) -> float | None:
    vals: list[float] = []
    for row in rows:
        value = _to_float(row.get(key))
        if value is not None:
            vals.append(value)
    return _mean(vals) if vals else None


def _subset_mean(rows: list[dict[str, Any]], *, include: Any, value_key: str) -> float:
    vals: list[float] = []
    for row in rows:
        if include(row):
            value = _to_float(row.get(value_key))
            if value is not None:
                vals.append(value)
    return _mean(vals)


def _common_metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    out: dict[str, float] = {}
    value_acc = _mean_field(rows, "value_ok")
    if value_acc is not None:
        out["value_acc"] = value_acc
    exact = _mean_field(rows, "value_exact_ok")
    if exact is None:
        exact = _mean_field(rows, "exact_ok")
    if exact is not None:
        out["value_exact_acc"] = exact
        out["exact_acc"] = exact
    parse_rate = _mean_field(rows, "parse_ok")
    if parse_rate is None:
        parse_rate = _mean_field(rows, "parsed_json")
    if parse_rate is not None:
        out["parse_rate"] = parse_rate
    for metric in ("cite_p", "cite_r", "cite_f1"):
        value = _mean_field(rows, metric)
        if value is not None:
            out[metric] = value
    return out


def _control_metrics(benchmark: str, rows: list[dict[str, Any]]) -> tuple[dict[str, float], list[str]]:
    notes: list[str] = []
    if not rows:
        return {}, notes
    if not all(isinstance(row.get("meta"), dict) and "pred_norm" in row for row in rows):
        notes.append(
            "control-family rows missing meta/pred_norm; only common metrics can be audited "
            "(re-run scorer to emit full row diagnostics)."
        )
        return {}, notes

    import score_control_family_scaffold as control  # Local script module.

    rows_copy = copy.deepcopy(rows)
    if benchmark == "rpa_mode_switch":
        means, _, _ = control._score_rpa_rows(rows_copy)
    elif benchmark == "intent_spec_layer":
        means, _, _ = control._score_intent_rows(rows_copy)
    elif benchmark == "noise_escalation":
        means, _, _ = control._score_noise_rows(rows_copy)
    elif benchmark == "implication_coherence":
        means, _, _ = control._score_ic_rows(rows_copy)
    elif benchmark == "agency_preserving_substitution":
        means, _, _ = control._score_aps_rows(rows_copy)
    else:
        means = {}
    return {k: float(v) for k, v in means.items() if isinstance(v, (int, float))}, notes


def _authority_metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for metric in (
        "latest_support_hit_rate",
        "note_citation_rate",
        "stale_citation_rate",
        "authority_violation_rate",
    ):
        source = metric.replace("_rate", "")
        value = _mean_field(rows, source)
        if value is not None:
            out[metric] = value
    return out


def _compression_roundtrip_metrics(rows: list[dict[str, Any]], split_summary: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    min_large_keys = 64
    subset_policy = split_summary.get("subset_policy")
    if isinstance(subset_policy, dict):
        raw = _to_float(subset_policy.get("large_snapshot_min_keys"))
        if raw is not None:
            min_large_keys = int(raw)

    out["direct_acc"] = _subset_mean(
        rows,
        include=lambda row: str(row.get("query_type", "")).strip().lower() == "direct",
        value_key="value_ok",
    )
    out["aggregate_acc"] = _subset_mean(
        rows,
        include=lambda row: str(row.get("query_type", "")).strip().lower() == "aggregate",
        value_key="value_ok",
    )
    out["exception_acc"] = _subset_mean(
        rows,
        include=lambda row: str(row.get("query_type", "")).strip().lower() == "exception",
        value_key="value_ok",
    )
    out["negation_acc"] = _subset_mean(
        rows,
        include=lambda row: str(row.get("query_type", "")).strip().lower() == "negation",
        value_key="value_ok",
    )
    out["tail_key_acc"] = _subset_mean(
        rows,
        include=lambda row: str(row.get("query_position", "")).strip().lower() == "tail",
        value_key="value_ok",
    )
    out["null_target_acc"] = _subset_mean(
        rows,
        include=lambda row: str(row.get("query_target_type", "")).strip().lower() == "null",
        value_key="value_ok",
    )
    out["nonnull_target_acc"] = _subset_mean(
        rows,
        include=lambda row: str(row.get("query_target_type", "")).strip().lower() == "nonnull",
        value_key="value_ok",
    )
    out["large_snapshot_acc"] = _subset_mean(
        rows,
        include=lambda row: int(_to_float(row.get("snapshot_key_count")) or 0) >= min_large_keys,
        value_key="value_ok",
    )
    return out


def _myopic_metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    return {
        "entry_acc": _subset_mean(
            rows,
            include=lambda row: str(row.get("profile", "")).strip().lower() == "entry",
            value_key="value_ok",
        ),
        "horizon_success_rate": _subset_mean(
            rows,
            include=lambda row: str(row.get("profile", "")).strip().lower() == "horizon",
            value_key="value_ok",
        ),
        "recovery_rate": _subset_mean(
            rows,
            include=lambda row: str(row.get("profile", "")).strip().lower() == "recovery",
            value_key="value_ok",
        ),
        "counterfactual_acc": _subset_mean(
            rows,
            include=lambda row: str(row.get("profile", "")).strip().lower() == "counterfactual",
            value_key="value_ok",
        ),
        "trap_entry_rate": _mean(
            [_to_float(row.get("trap_entry")) or 0.0 for row in rows if "trap_entry" in row]
        ),
        "first_error_step_mean": _mean(
            [
                _to_float(row.get("first_error_step")) or 0.0
                for row in rows
                if _to_float(row.get("first_error_step")) is not None
            ]
        ),
        "entry_count": float(
            sum(1 for row in rows if str(row.get("profile", "")).strip().lower() == "entry")
        ),
        "horizon_count": float(
            sum(1 for row in rows if str(row.get("profile", "")).strip().lower() == "horizon")
        ),
        "recovery_count": float(
            sum(1 for row in rows if str(row.get("profile", "")).strip().lower() == "recovery")
        ),
        "counterfactual_count": float(
            sum(1 for row in rows if str(row.get("profile", "")).strip().lower() == "counterfactual")
        ),
    }


def _referential_metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    family_values: dict[str, list[float]] = {}
    for row in rows:
        family_id = str(row.get("family_id", "")).strip()
        if not family_id:
            continue
        family_values.setdefault(family_id, []).append(_to_float(row.get("value_ok")) or 0.0)

    out: dict[str, float] = {
        "pointer_set_size": _mean([float(len(row.get("pred_support_ids") or [])) for row in rows]),
        "part_coverage_recall": _mean(
            [_to_float(row.get("value_ok")) or 0.0 for row in rows if "value_ok" in row]
        ),
        "pointer_precision": _mean(
            [_to_float(row.get("cite_p")) or 0.0 for row in rows if _to_float(row.get("cite_p")) is not None]
        ),
        "pointer_recall": _mean(
            [_to_float(row.get("cite_r")) or 0.0 for row in rows if _to_float(row.get("cite_r")) is not None]
        ),
        "reassembly_fidelity": _mean(
            [_to_float(row.get("exact_ok")) or 0.0 for row in rows if "exact_ok" in row]
        ),
        "hallucinated_expansion_rate": _mean(
            [_to_float(row.get("hallucinated_expansion")) or 0.0 for row in rows if "hallucinated_expansion" in row]
        ),
        "stale_pointer_override_rate": _mean(
            [_to_float(row.get("stale_pointer_override")) or 0.0 for row in rows if "stale_pointer_override" in row]
        ),
        "lookup_depth_cost": _mean(
            [_to_float(row.get("lookup_depth_cost")) or 0.0 for row in rows if _to_float(row.get("lookup_depth_cost")) is not None]
        ),
    }
    stale_vals = family_values.get("stale_pointer_conflict", [])
    hub_vals = family_values.get("wrong_hub_attraction", [])
    out["exception_acc"] = _mean(stale_vals)
    out["large_snapshot_acc"] = _mean(hub_vals)
    for family_id, vals in sorted(family_values.items()):
        out[f"{family_id}_acc"] = _mean(vals)
        out[f"{family_id}_count"] = float(len(vals))
    return out


def _novel_continuity_metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    by_dim: dict[str, list[float]] = {"identity": [], "timeline": [], "constraint": []}
    for row in rows:
        dim = str(row.get("dimension", "")).strip().lower()
        if dim not in by_dim:
            continue
        by_dim[dim].append(_to_float(row.get("value_ok")) or 0.0)
    return {
        "identity_acc": _mean(by_dim["identity"]),
        "timeline_acc": _mean(by_dim["timeline"]),
        "constraint_acc": _mean(by_dim["constraint"]),
    }


def _novel_continuity_long_horizon_metrics(rows: list[dict[str, Any]], split_summary: dict[str, Any]) -> dict[str, float]:
    subset_policy = split_summary.get("subset_policy")
    long_gap_min_steps = 8
    high_contradiction_min_count = 4
    if isinstance(subset_policy, dict):
        raw_gap = _to_float(subset_policy.get("long_gap_min_steps"))
        raw_contra = _to_float(subset_policy.get("high_contradiction_min_count"))
        if raw_gap is not None:
            long_gap_min_steps = int(raw_gap)
        if raw_contra is not None:
            high_contradiction_min_count = int(raw_contra)

    long_gap_vals: list[float] = []
    high_contra_vals: list[float] = []
    delayed_vals: list[float] = []
    repair_vals: list[float] = []
    for row in rows:
        value_ok = _to_float(row.get("value_ok"))
        if value_ok is None:
            continue
        callback_gap = int(_to_float(row.get("callback_gap_steps")) or 0)
        contradiction_pressure = int(_to_float(row.get("contradiction_pressure_count")) or 0)
        if callback_gap >= long_gap_min_steps:
            long_gap_vals.append(value_ok)
        if contradiction_pressure >= high_contradiction_min_count:
            high_contra_vals.append(value_ok)
        if bool(row.get("delayed_dependency")):
            delayed_vals.append(value_ok)
        if bool(row.get("repair_transition")):
            repair_vals.append(value_ok)

    out = _novel_continuity_metrics(rows)
    out.update(
        {
            "long_gap_acc": _mean(long_gap_vals),
            "high_contradiction_acc": _mean(high_contra_vals),
            "delayed_dependency_acc": _mean(delayed_vals),
            "repair_transition_acc": _mean(repair_vals),
            "long_gap_count": float(len(long_gap_vals)),
            "high_contradiction_count": float(len(high_contra_vals)),
            "delayed_dependency_count": float(len(delayed_vals)),
            "repair_transition_count": float(len(repair_vals)),
        }
    )
    return out


def _compression_loss_bounded_metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for metric in ("precision", "recall", "f1", "bloat"):
        value = _mean_field(rows, metric)
        if value is not None:
            out[metric] = value
    exact = _mean_field(rows, "exact_match")
    if exact is not None:
        out["exact_match_rate"] = exact
    parse_rate = _mean_field(rows, "parse_ok")
    if parse_rate is not None:
        out["parse_rate"] = parse_rate
    return out


def _epistemic_metrics(rows: list[dict[str, Any],], split_summary: dict[str, Any]) -> dict[str, float]:
    import score_epistemic_calibration_suite as epi

    values = [1.0 if bool(row.get("row_correct")) else 0.0 for row in rows]
    parse_rates = [1.0 if bool(row.get("parsed_json")) else 0.0 for row in rows]
    confidence_provided = [1.0 if bool(row.get("confidence_provided")) else 0.0 for row in rows]
    overclaim = [1.0 if bool(row.get("overclaim")) else 0.0 for row in rows]

    abstain_pred_total = 0
    abstain_prec_hits = 0
    abstain_gold_total = 0
    abstain_recall_hits = 0
    needed_recalls: list[float] = []
    answer_confidences: list[float] = []
    answer_labels: list[float] = []
    all_probs: list[float] = []
    all_labels: list[float] = []
    family_hits: dict[str, int] = {}
    family_counts: dict[str, int] = {}

    for row in rows:
        family_id = str(row.get("family_id", "unknown"))
        family_counts[family_id] = family_counts.get(family_id, 0) + 1
        if bool(row.get("row_correct")):
            family_hits[family_id] = family_hits.get(family_id, 0) + 1

        decision = str(row.get("pred_decision", "")).strip().lower()
        is_answerable = bool(row.get("is_answerable"))
        decision_is_abstain = decision in epi.ABSTAIN_DECISIONS
        if decision_is_abstain:
            abstain_pred_total += 1
            if not is_answerable:
                abstain_prec_hits += 1
        if not is_answerable:
            abstain_gold_total += 1
            if decision_is_abstain:
                abstain_recall_hits += 1

        confidence = _to_float(row.get("confidence")) or 0.0
        row_correct = 1.0 if bool(row.get("row_correct")) else 0.0
        all_probs.append(confidence)
        all_labels.append(row_correct)

        if decision == "answer":
            answer_confidences.append(confidence)
            answer_labels.append(1.0 if bool(row.get("answer_correct")) else 0.0)

        expected_needed = epi._set_of_str(row.get("needed_info_expected"))
        pred_needed = epi._set_of_str(row.get("needed_info_pred"))
        if expected_needed:
            pred_needed_norm = epi._normalize_needed_info_items(pred_needed)
            hits = 0
            for expected_key in expected_needed:
                if epi._needed_info_matches(expected_key=expected_key, pred_items_norm=pred_needed_norm):
                    hits += 1
            needed_recalls.append(hits / len(expected_needed))

    abstain_precision = abstain_prec_hits / abstain_pred_total if abstain_pred_total > 0 else 1.0
    abstain_recall = abstain_recall_hits / abstain_gold_total if abstain_gold_total > 0 else 1.0
    abstain_f1 = (
        (2.0 * abstain_precision * abstain_recall / (abstain_precision + abstain_recall))
        if abstain_precision > 0 and abstain_recall > 0
        else 0.0
    )
    coverage = _to_float(split_summary.get("coverage"))
    if coverage is None:
        coverage = 0.5
    overclaim_rate = _mean(overclaim)
    ece = epi._ece(all_probs, all_labels, bins=10)
    brier = epi._brier(all_probs, all_labels)
    selective_acc = epi._selective_accuracy(answer_confidences, answer_labels, coverage)
    needed_info_recall = _mean(needed_recalls)
    value_acc = _mean(values)
    kkyi = (
        0.30 * (1.0 - ece)
        + 0.20 * (1.0 - overclaim_rate)
        + 0.20 * abstain_f1
        + 0.20 * selective_acc
        + 0.10 * needed_info_recall
    )

    out = {
        "value_acc": value_acc,
        "exact_acc": value_acc,
        "parse_rate": _mean(parse_rates),
        "confidence_provided_rate": _mean(confidence_provided),
        "confidence_proxy_used_rate": 1.0 - _mean(confidence_provided),
        "overclaim_rate": overclaim_rate,
        "abstain_precision": abstain_precision,
        "abstain_recall": abstain_recall,
        "abstain_f1": abstain_f1,
        "ece": ece,
        "brier": brier,
        "selective_accuracy_at_coverage": selective_acc,
        "needed_info_recall": needed_info_recall,
        "kkyi": kkyi,
    }
    for family_id, count in sorted(family_counts.items()):
        out[f"{family_id}_acc"] = (family_hits.get(family_id, 0) / count) if count > 0 else 0.0
        out[f"{family_id}_count"] = float(count)
    return out


def _compute_metrics_for_benchmark(
    *,
    benchmark: str,
    rows: list[dict[str, Any]],
    split_summary: dict[str, Any],
) -> tuple[dict[str, float], list[str]]:
    notes: list[str] = []
    computed = _common_metrics(rows)

    if benchmark in CONTROL_FAMILIES:
        family_means, control_notes = _control_metrics(benchmark, rows)
        computed.update(family_means)
        notes.extend(control_notes)
        return computed, notes
    if benchmark in {"authority_under_interference", "authority_under_interference_hardening"}:
        computed.update(_authority_metrics(rows))
        return computed, notes
    if benchmark == "compression_recoverability":
        return computed, notes
    if benchmark == "compression_roundtrip_generalization":
        computed.update(_compression_roundtrip_metrics(rows, split_summary))
        return computed, notes
    if benchmark == "compression_loss_bounded":
        computed.update(_compression_loss_bounded_metrics(rows))
        return computed, notes
    if benchmark == "referential_indexing_suite":
        computed.update(_referential_metrics(rows))
        return computed, notes
    if benchmark == "myopic_planning_traps":
        computed.update(_myopic_metrics(rows))
        return computed, notes
    if benchmark == "novel_continuity":
        computed.update(_novel_continuity_metrics(rows))
        return computed, notes
    if benchmark == "novel_continuity_long_horizon":
        computed.update(_novel_continuity_long_horizon_metrics(rows, split_summary))
        return computed, notes
    if benchmark == "epistemic_calibration_suite":
        computed.update(_epistemic_metrics(rows, split_summary))
        return computed, notes

    notes.append(f"unsupported benchmark '{benchmark}'; only common metrics audited")
    return computed, notes


def _compare_means(
    *,
    run_dir: Path,
    benchmark: str,
    split: str,
    summary_means: dict[str, Any],
    computed_means: dict[str, float],
    tolerance: float,
) -> tuple[list[dict[str, Any]], list[str]]:
    checks: list[dict[str, Any]] = []
    failures: list[str] = []

    for metric, observed in sorted(computed_means.items()):
        expected_raw = summary_means.get(metric)
        expected = _to_float(expected_raw)
        if expected is None:
            continue
        diff = abs(expected - observed)
        ok = diff <= tolerance
        checks.append(
            {
                "run_dir": str(run_dir),
                "benchmark": benchmark,
                "split": split,
                "metric": metric,
                "expected": expected,
                "observed": observed,
                "abs_diff": diff,
                "status": "PASS" if ok else "FAIL",
            }
        )
        if not ok:
            failures.append(
                f"{run_dir} {benchmark} {split}: {metric} mismatch "
                f"(expected={expected:.12f}, observed={observed:.12f}, diff={diff:.12f})"
            )
    return checks, failures


def _audit_split(
    *,
    run_dir: Path,
    benchmark: str,
    split: str,
    split_summary: dict[str, Any],
    rows_path: Path,
    tolerance: float,
    strict: bool,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    checks: list[dict[str, Any]] = []
    failures: list[str] = []
    notes: list[str] = []

    if not rows_path.exists():
        msg = f"{run_dir} {benchmark} {split}: missing rows file {rows_path}"
        if strict:
            failures.append(msg)
        else:
            notes.append(msg)
        return checks, failures, notes

    rows = [row for row in read_jsonl(rows_path) if isinstance(row, dict)]
    rows_scored = split_summary.get("rows_scored")
    rows_total = split_summary.get("rows_total")
    if isinstance(rows_scored, (int, float)) and int(rows_scored) != len(rows):
        failures.append(
            f"{run_dir} {benchmark} {split}: rows_scored={int(rows_scored)} but rows_file_count={len(rows)}"
        )
    if isinstance(rows_total, (int, float)) and int(rows_total) < len(rows):
        failures.append(
            f"{run_dir} {benchmark} {split}: rows_total={int(rows_total)} < rows_file_count={len(rows)}"
        )

    means = split_summary.get("means")
    if not isinstance(means, dict):
        msg = f"{run_dir} {benchmark} {split}: missing means object"
        if strict:
            failures.append(msg)
        else:
            notes.append(msg)
        return checks, failures, notes

    computed, compute_notes = _compute_metrics_for_benchmark(
        benchmark=benchmark,
        rows=rows,
        split_summary=split_summary,
    )
    formatted_compute_notes = [f"{run_dir} {benchmark} {split}: {note}" for note in compute_notes]
    if strict and formatted_compute_notes:
        failures.extend(formatted_compute_notes)
    else:
        notes.extend(formatted_compute_notes)
    split_checks, split_failures = _compare_means(
        run_dir=run_dir,
        benchmark=benchmark,
        split=split,
        summary_means=means,
        computed_means=computed,
        tolerance=tolerance,
    )
    checks.extend(split_checks)
    failures.extend(split_failures)
    return checks, failures, notes


def _audit_persona_invariance(
    *,
    run_dir: Path,
    benchmark: str,
    label: str,
    persona_summary: dict[str, Any] | None,
    rows_path: Path,
    tolerance: float,
    strict: bool,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    checks: list[dict[str, Any]] = []
    failures: list[str] = []
    notes: list[str] = []

    if not isinstance(persona_summary, dict):
        msg = f"{run_dir} {benchmark} {label}: missing persona_invariance block"
        if strict:
            failures.append(msg)
        else:
            notes.append(msg)
        return checks, failures, notes

    status = str(persona_summary.get("status", "")).strip().upper()
    if status == "SKIP":
        return checks, failures, notes

    if not rows_path.exists():
        msg = f"{run_dir} {benchmark} {label}: missing persona rows file {rows_path}"
        if strict:
            failures.append(msg)
        else:
            notes.append(msg)
        return checks, failures, notes

    rows = [row for row in read_jsonl(rows_path) if isinstance(row, dict)]
    rows_total = len(rows)
    rows_changed = sum(1 for row in rows if not bool(row.get("invariant")))
    row_invariance_rate = ((rows_total - rows_changed) / rows_total) if rows_total else 0.0
    expected_status = "PASS" if abs(row_invariance_rate - 1.0) <= 1e-12 else "FAIL"

    computed = {
        "row_invariance_rate": row_invariance_rate,
        "rows_total": float(rows_total),
        "rows_changed": float(rows_changed),
    }
    summary_means = {
        "row_invariance_rate": persona_summary.get("row_invariance_rate"),
        "rows_total": persona_summary.get("rows_total"),
        "rows_changed": persona_summary.get("rows_changed"),
    }
    split_checks, split_failures = _compare_means(
        run_dir=run_dir,
        benchmark=benchmark,
        split=f"{label}/persona_invariance",
        summary_means=summary_means,
        computed_means=computed,
        tolerance=tolerance,
    )
    checks.extend(split_checks)
    failures.extend(split_failures)

    status_ok = status == expected_status
    checks.append(
        {
            "run_dir": str(run_dir),
            "benchmark": benchmark,
            "split": f"{label}/persona_invariance",
            "metric": "status",
            "expected": expected_status,
            "observed": status,
            "abs_diff": 0.0 if status_ok else 1.0,
            "status": "PASS" if status_ok else "FAIL",
        }
    )
    if not status_ok:
        failures.append(
            f"{run_dir} {benchmark} {label}: persona_invariance status mismatch "
            f"(expected={expected_status}, observed={status})"
        )

    return checks, failures, notes


def _find_combined_summaries(run_dir: Path) -> list[Path]:
    summaries: list[Path] = []
    for path in sorted(run_dir.glob("*_summary.json")):
        name = path.name.lower()
        if name in {"anchors_summary.json", "holdout_summary.json", "canary_summary.json"}:
            continue
        if "manuscript_mode_summary" in name:
            continue
        summaries.append(path)
    return summaries


def _audit_combined_summary(
    *,
    run_dir: Path,
    summary_path: Path,
    tolerance: float,
    strict: bool,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    checks: list[dict[str, Any]] = []
    failures: list[str] = []
    notes: list[str] = []

    summary = _read_json(summary_path)
    benchmark = str(summary.get("benchmark", "")).strip().lower()
    if not benchmark:
        notes.append(f"{summary_path}: missing benchmark field; skipped")
        return checks, failures, notes

    if benchmark == "compression_families":
        families = summary.get("families")
        if not isinstance(families, dict):
            failures.append(f"{summary_path}: compression_families missing families object")
            return checks, failures, notes
        for family_name, family_summary in sorted(families.items()):
            if not isinstance(family_summary, dict):
                failures.append(f"{summary_path}: invalid family summary for {family_name}")
                continue
            family_dir = run_dir / family_name
            for split in ("anchors", "holdout", "canary"):
                split_summary = family_summary.get(split)
                if not isinstance(split_summary, dict):
                    continue
                rows_path = family_dir / f"{split}_rows.jsonl"
                split_checks, split_failures, split_notes = _audit_split(
                    run_dir=run_dir,
                    benchmark=family_name,
                    split=f"{family_name}/{split}",
                    split_summary=split_summary,
                    rows_path=rows_path,
                    tolerance=tolerance,
                    strict=strict,
                )
                checks.extend(split_checks)
                failures.extend(split_failures)
                notes.extend(split_notes)
            persona_checks, persona_failures, persona_notes = _audit_persona_invariance(
                run_dir=run_dir,
                benchmark=family_name,
                label=f"{family_name}",
                persona_summary=family_summary.get("persona_invariance"),
                rows_path=family_dir / "persona_invariance_rows.jsonl",
                tolerance=tolerance,
                strict=strict,
            )
            checks.extend(persona_checks)
            failures.extend(persona_failures)
            notes.extend(persona_notes)
        return checks, failures, notes

    for split in ("anchors", "holdout", "canary"):
        split_summary = summary.get(split)
        if not isinstance(split_summary, dict):
            continue
        rows_path = run_dir / f"{split}_rows.jsonl"
        split_checks, split_failures, split_notes = _audit_split(
            run_dir=run_dir,
            benchmark=benchmark,
            split=split,
            split_summary=split_summary,
            rows_path=rows_path,
            tolerance=tolerance,
            strict=strict,
        )
        checks.extend(split_checks)
        failures.extend(split_failures)
        notes.extend(split_notes)

    persona_checks, persona_failures, persona_notes = _audit_persona_invariance(
        run_dir=run_dir,
        benchmark=benchmark,
        label="holdout",
        persona_summary=summary.get("persona_invariance"),
        rows_path=run_dir / "persona_invariance_rows.jsonl",
        tolerance=tolerance,
        strict=strict,
    )
    checks.extend(persona_checks)
    failures.extend(persona_failures)
    notes.extend(persona_notes)

    return checks, failures, notes


def main() -> int:
    ns = _parse_args()
    run_dirs = [Path(item) for item in ns.run_dirs]
    checks: list[dict[str, Any]] = []
    failures: list[str] = []
    notes: list[str] = []
    audited_summaries = 0

    for run_dir in run_dirs:
        if not run_dir.exists():
            failures.append(f"Missing run dir: {run_dir}")
            continue
        summaries = _find_combined_summaries(run_dir)
        if not summaries:
            message = f"{run_dir}: no combined family summary files found"
            if ns.strict:
                failures.append(message)
            else:
                notes.append(message)
            continue

        for summary_path in summaries:
            audited_summaries += 1
            s_checks, s_failures, s_notes = _audit_combined_summary(
                run_dir=run_dir,
                summary_path=summary_path,
                tolerance=ns.tolerance,
                strict=ns.strict,
            )
            checks.extend(s_checks)
            failures.extend(s_failures)
            notes.extend(s_notes)

    status = "PASS" if not failures else "FAIL"
    report = {
        "benchmark": "trap_row_summary_consistency_audit",
        "status": status,
        "run_dirs": [str(path) for path in run_dirs],
        "audited_summaries": audited_summaries,
        "check_count": len(checks),
        "failure_count": len(failures),
        "note_count": len(notes),
        "tolerance": ns.tolerance,
        "checks": checks,
        "failures": failures,
        "notes": notes,
    }

    print("Trap row-summary consistency audit")
    print(f"Run dirs: {len(run_dirs)}")
    print(f"Audited summaries: {audited_summaries}")
    print(f"Checks: {len(checks)}")
    print(f"Notes: {len(notes)}")
    print(f"Failures: {len(failures)}")
    print(f"RESULT: {status}")
    for failure in failures[:20]:
        print(f"[FAIL] {failure}")
    if len(failures) > 20:
        print(f"... and {len(failures) - 20} more failures")

    if ns.out is not None:
        ns.out.parent.mkdir(parents=True, exist_ok=True)
        ns.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote {ns.out}")

    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
