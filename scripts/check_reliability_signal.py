from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate release-quality reliability signal from latest strict RAG "
            "plus orthogonal trap-family reliability summaries."
        )
    )
    parser.add_argument(
        "--strict",
        type=Path,
        default=Path("runs/latest_rag_strict"),
        help=(
            "Strict run selector: latest pointer file, strict run directory, or "
            "summary JSON path. Default: runs/latest_rag_strict"
        ),
    )
    parser.add_argument(
        "--compression-reliability",
        type=Path,
        default=Path("runs/compression_reliability_latest.json"),
        help="Path to compression reliability summary JSON.",
    )
    parser.add_argument(
        "--novel-reliability",
        type=Path,
        default=Path("runs/novel_continuity_reliability_latest.json"),
        help="Path to novel continuity reliability summary JSON.",
    )
    parser.add_argument(
        "--authority-interference-reliability",
        type=Path,
        default=Path("runs/authority_under_interference_reliability_latest.json"),
        help="Path to authority-under-interference reliability summary JSON.",
    )
    parser.add_argument(
        "--compression-roundtrip-reliability",
        type=Path,
        default=Path("runs/compression_roundtrip_generalization_reliability_latest.json"),
        help="Path to compression roundtrip generalization reliability summary JSON.",
    )
    parser.add_argument(
        "--require-compression-roundtrip",
        action="store_true",
        help="Require compression roundtrip generalization reliability summary to exist and PASS.",
    )
    parser.add_argument(
        "--novel-long-horizon-reliability",
        type=Path,
        default=Path("runs/novel_continuity_long_horizon_reliability_latest.json"),
        help="Path to novel continuity long-horizon reliability summary JSON.",
    )
    parser.add_argument(
        "--require-novel-long-horizon",
        action="store_true",
        help="Require novel continuity long-horizon reliability summary to exist and PASS.",
    )
    parser.add_argument(
        "--myopic-planning-reliability",
        type=Path,
        default=Path("runs/myopic_planning_traps_reliability_latest.json"),
        help="Path to myopic planning traps reliability summary JSON.",
    )
    parser.add_argument(
        "--require-myopic-planning",
        action="store_true",
        help="Require myopic planning traps reliability summary to exist and PASS.",
    )
    parser.add_argument(
        "--referential-indexing-reliability",
        type=Path,
        default=Path("runs/referential_indexing_suite_reliability_latest.json"),
        help="Path to referential indexing suite reliability summary JSON.",
    )
    parser.add_argument(
        "--require-referential-indexing",
        action="store_true",
        help="Require referential indexing suite reliability summary to exist and PASS.",
    )
    parser.add_argument(
        "--epistemic-reliability",
        type=Path,
        default=Path("runs/epistemic_calibration_suite_reliability_latest.json"),
        help="Path to epistemic calibration suite reliability summary JSON.",
    )
    parser.add_argument(
        "--require-epistemic",
        action="store_true",
        help="Require epistemic calibration suite reliability summary to exist and PASS.",
    )
    parser.add_argument(
        "--authority-hardening-reliability",
        type=Path,
        default=Path("runs/authority_under_interference_hardening_reliability_latest.json"),
        help="Path to authority-under-interference hardening reliability summary JSON.",
    )
    parser.add_argument(
        "--require-authority-hardening",
        action="store_true",
        help="Require authority-under-interference hardening reliability summary to exist and PASS.",
    )
    parser.add_argument(
        "--rpa-mode-switch-reliability",
        type=Path,
        default=Path("runs/rpa_mode_switch_reliability_latest.json"),
        help="Path to RPA mode-switch reliability summary JSON.",
    )
    parser.add_argument(
        "--require-rpa-mode-switch",
        action="store_true",
        help="Require RPA mode-switch reliability summary to exist and PASS.",
    )
    parser.add_argument(
        "--intent-spec-reliability",
        type=Path,
        default=Path("runs/intent_spec_layer_reliability_latest.json"),
        help="Path to intent-spec layer reliability summary JSON.",
    )
    parser.add_argument(
        "--require-intent-spec",
        action="store_true",
        help="Require intent-spec layer reliability summary to exist and PASS.",
    )
    parser.add_argument(
        "--noise-escalation-reliability",
        type=Path,
        default=Path("runs/noise_escalation_reliability_latest.json"),
        help="Path to noise-escalation reliability summary JSON.",
    )
    parser.add_argument(
        "--require-noise-escalation",
        action="store_true",
        help="Require noise-escalation reliability summary to exist and PASS.",
    )
    parser.add_argument("--min-value-acc", type=float, default=0.95)
    parser.add_argument("--min-exact-acc", type=float, default=0.95)
    parser.add_argument("--min-cite-f1", type=float, default=0.95)
    parser.add_argument("--min-instruction-acc", type=float, default=0.95)
    parser.add_argument("--min-state-integrity-rate", type=float, default=0.95)
    parser.add_argument(
        "--min-reasoning-score",
        type=float,
        default=None,
        help=(
            "Optional floor for derived reasoning score (0..1). "
            "Reasoning score is computed from strict/core, authority, "
            "referential indexing, compression roundtrip, and epistemic signals."
        ),
    )
    parser.add_argument(
        "--min-planning-score",
        type=float,
        default=None,
        help=(
            "Optional floor for derived planning score (0..1). "
            "Planning score is computed from myopic planning and "
            "novel continuity long-horizon signals."
        ),
    )
    parser.add_argument(
        "--min-intelligence-index",
        type=float,
        default=None,
        help=(
            "Optional floor for derived intelligence index (0..1), "
            "defined as sqrt(reasoning_score * planning_score)."
        ),
    )
    parser.add_argument(
        "--skip-domain-hard-checks",
        action="store_true",
        help="Skip domain_stale/domain_authority/domain_exception exact_acc == 1.0 checks.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("runs/reliability_signal_latest.json"),
        help="Output JSON path.",
    )
    return parser.parse_args()


def _read_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid JSON object: {path}")
    return raw


def _resolve_strict_summary(strict_arg: Path) -> tuple[Path, dict[str, Any]]:
    candidate = strict_arg
    if candidate.is_file():
        # Could be pointer file or direct summary file.
        if candidate.suffix.lower() == ".json":
            summary_path = candidate
        else:
            target_text = candidate.read_text(encoding="utf-8-sig").strip()
            if not target_text:
                raise ValueError(f"Strict pointer is empty: {candidate}")
            target = Path(target_text)
            if not target.exists():
                raise ValueError(f"Strict pointer target does not exist: {target}")
            if target.is_file():
                summary_path = target
            else:
                summary_path = target / "summary_compact.json"
    else:
        # Directory path passed explicitly.
        summary_path = candidate / "summary_compact.json"

    if not summary_path.exists():
        # fallback
        fallback = summary_path.parent / "summary.json"
        if fallback.exists():
            summary_path = fallback
        else:
            raise ValueError(f"Could not find strict summary JSON at {summary_path} or {fallback}")

    return summary_path, _read_json(summary_path)


def _means(summary: dict[str, Any]) -> dict[str, float]:
    means_obj = summary.get("means")
    if not isinstance(means_obj, dict):
        return {}
    out: dict[str, float] = {}
    for key, value in means_obj.items():
        if isinstance(value, (int, float)):
            out[key] = float(value)
    return out


def _dataset_map(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = summary.get("datasets")
    if not isinstance(rows, list):
        rows = summary.get("results")
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_id = row.get("id")
        if isinstance(row_id, str) and row_id:
            out[row_id] = row
    return out


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / float(len(values))


def _normalized_metric(
    means: dict[str, float] | None,
    name: str,
    *,
    invert: bool = False,
) -> float | None:
    if means is None:
        return None
    value = means.get(name)
    if value is None:
        return None
    v = float(value)
    if invert:
        v = 1.0 - v
    return _clamp01(v)


def _reliability_benchmark_to_family(summary: dict[str, Any]) -> str | None:
    benchmark = summary.get("benchmark")
    if not isinstance(benchmark, str):
        return None
    suffix = "_reliability"
    if benchmark.endswith(suffix):
        return benchmark[: -len(suffix)]
    return None


def _holdout_means_from_family_reliability(
    reliability_summary: dict[str, Any] | None,
) -> tuple[dict[str, float] | None, str | None]:
    if reliability_summary is None:
        return None, "reliability summary missing"

    runs = reliability_summary.get("runs")
    if not isinstance(runs, list) or not runs:
        return None, "runs list missing in reliability summary"

    last_run = runs[-1]
    if not isinstance(last_run, str) or not last_run.strip():
        return None, "invalid latest run path in reliability summary"

    family_id = _reliability_benchmark_to_family(reliability_summary)
    if not family_id:
        return None, "could not infer family id from reliability benchmark"

    summary_path = Path(last_run) / f"{family_id}_summary.json"
    if not summary_path.exists():
        return None, f"missing family summary: {summary_path}"

    try:
        family_summary = _read_json(summary_path)
    except Exception as exc:  # noqa: BLE001
        return None, f"failed to read {summary_path}: {exc}"

    holdout_obj = family_summary.get("holdout")
    if not isinstance(holdout_obj, dict):
        return None, f"missing holdout object in {summary_path}"

    holdout_means = _means(holdout_obj)
    if not holdout_means:
        return None, f"missing holdout means in {summary_path}"

    return holdout_means, None


def _metric_check(
    *,
    name: str,
    value: float | None,
    minimum: float,
    lines: list[str],
    failures: list[str],
) -> None:
    if value is None:
        lines.append(f"[FAIL] strict.means.{name}=<missing> >= {minimum:.6f}")
        failures.append(f"strict.means.{name} missing")
        return
    ok = value >= minimum
    lines.append(f"[{'PASS' if ok else 'FAIL'}] strict.means.{name}={value:.6f} >= {minimum:.6f}")
    if not ok:
        failures.append(f"strict.means.{name} < {minimum}")


def _derive_scores(
    *,
    strict_means: dict[str, float],
    novel_means: dict[str, float] | None,
    long_horizon_means: dict[str, float] | None,
    myopic_means: dict[str, float] | None,
    referential_means: dict[str, float] | None,
    epistemic_means: dict[str, float] | None,
    authority_means: dict[str, float] | None,
    compression_roundtrip_means: dict[str, float] | None,
) -> dict[str, Any]:
    strict_core = _average(
        [
            value
            for value in [
                _normalized_metric(strict_means, "value_acc"),
                _normalized_metric(strict_means, "exact_acc"),
                _normalized_metric(strict_means, "cite_f1"),
                _normalized_metric(strict_means, "instruction_acc"),
                _normalized_metric(strict_means, "state_integrity_rate"),
            ]
            if value is not None
        ]
    )
    epistemic_core = _average(
        [
            value
            for value in [
                _normalized_metric(epistemic_means, "kkyi"),
                _normalized_metric(epistemic_means, "abstain_f1"),
                _normalized_metric(epistemic_means, "selective_accuracy_at_coverage"),
                _normalized_metric(epistemic_means, "needed_info_recall"),
                _normalized_metric(epistemic_means, "overclaim_rate", invert=True),
                _normalized_metric(epistemic_means, "ece", invert=True),
            ]
            if value is not None
        ]
    )
    authority_core = _average(
        [
            value
            for value in [
                _normalized_metric(authority_means, "latest_support_hit_rate"),
                _normalized_metric(authority_means, "cite_f1"),
                _normalized_metric(authority_means, "authority_violation_rate", invert=True),
            ]
            if value is not None
        ]
    )
    referential_core = _average(
        [
            value
            for value in [
                _normalized_metric(referential_means, "reassembly_fidelity"),
                _normalized_metric(referential_means, "part_coverage_recall"),
                _normalized_metric(referential_means, "pointer_precision"),
                _normalized_metric(referential_means, "pointer_recall"),
                _normalized_metric(referential_means, "hallucinated_expansion_rate", invert=True),
                _normalized_metric(referential_means, "stale_pointer_override_rate", invert=True),
            ]
            if value is not None
        ]
    )
    compression_roundtrip_core = _average(
        [
            value
            for value in [
                _normalized_metric(compression_roundtrip_means, "value_acc"),
                _normalized_metric(compression_roundtrip_means, "exact_acc"),
                _normalized_metric(compression_roundtrip_means, "cite_f1"),
                _normalized_metric(compression_roundtrip_means, "exception_acc"),
                _normalized_metric(compression_roundtrip_means, "tail_key_acc"),
                _normalized_metric(compression_roundtrip_means, "nonnull_target_acc"),
            ]
            if value is not None
        ]
    )

    reasoning_components = {
        "strict_core": strict_core,
        "epistemic_core": epistemic_core,
        "authority_core": authority_core,
        "referential_core": referential_core,
        "compression_roundtrip_core": compression_roundtrip_core,
    }
    reasoning_score = _average([v for v in reasoning_components.values() if v is not None])

    myopic_first_error_score: float | None = None
    if myopic_means is not None and isinstance(myopic_means.get("first_error_step_mean"), (int, float)):
        # 5.0 is an empirically useful normalization anchor for current fixtures.
        myopic_first_error_score = _clamp01(float(myopic_means["first_error_step_mean"]) / 5.0)

    myopic_core = _average(
        [
            value
            for value in [
                _normalized_metric(myopic_means, "horizon_success_rate"),
                _normalized_metric(myopic_means, "recovery_rate"),
                _normalized_metric(myopic_means, "trap_entry_rate", invert=True),
                myopic_first_error_score,
            ]
            if value is not None
        ]
    )
    long_horizon_core = _average(
        [
            value
            for value in [
                _normalized_metric(long_horizon_means, "identity_acc"),
                _normalized_metric(long_horizon_means, "timeline_acc"),
                _normalized_metric(long_horizon_means, "constraint_acc"),
                _normalized_metric(long_horizon_means, "long_gap_acc"),
                _normalized_metric(long_horizon_means, "high_contradiction_acc"),
                _normalized_metric(long_horizon_means, "delayed_dependency_acc"),
                _normalized_metric(long_horizon_means, "repair_transition_acc"),
            ]
            if value is not None
        ]
    )
    continuity_core = _average(
        [
            value
            for value in [
                _normalized_metric(novel_means, "identity_acc"),
                _normalized_metric(novel_means, "timeline_acc"),
                _normalized_metric(novel_means, "constraint_acc"),
            ]
            if value is not None
        ]
    )

    planning_components = {
        "myopic_core": myopic_core,
        "long_horizon_core": long_horizon_core,
        "continuity_core": continuity_core,
    }
    planning_score = _average([v for v in planning_components.values() if v is not None])

    intelligence_index: float | None = None
    if reasoning_score is not None and planning_score is not None:
        intelligence_index = math.sqrt(reasoning_score * planning_score)

    return {
        "reasoning_score": reasoning_score,
        "planning_score": planning_score,
        "intelligence_index": intelligence_index,
        "reasoning_components": reasoning_components,
        "planning_components": planning_components,
    }


def main() -> int:
    ns = _parse_args()
    lines: list[str] = ["Reliability signal check"]
    failures: list[str] = []

    try:
        strict_summary_path, strict_summary = _resolve_strict_summary(ns.strict)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 1

    try:
        compression_summary = _read_json(ns.compression_reliability)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: failed to read compression reliability summary: {exc}")
        return 1

    try:
        novel_summary = _read_json(ns.novel_reliability)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: failed to read novel continuity reliability summary: {exc}")
        return 1

    try:
        authority_summary = _read_json(ns.authority_interference_reliability)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: failed to read authority-under-interference reliability summary: {exc}")
        return 1

    compression_roundtrip_summary: dict[str, Any] | None = None
    compression_roundtrip_read_error = ""
    if ns.compression_roundtrip_reliability.exists():
        try:
            compression_roundtrip_summary = _read_json(ns.compression_roundtrip_reliability)
        except Exception as exc:  # noqa: BLE001
            compression_roundtrip_read_error = str(exc)
    elif ns.require_compression_roundtrip:
        compression_roundtrip_read_error = f"missing file: {ns.compression_roundtrip_reliability}"

    long_horizon_summary: dict[str, Any] | None = None
    long_horizon_read_error = ""
    if ns.novel_long_horizon_reliability.exists():
        try:
            long_horizon_summary = _read_json(ns.novel_long_horizon_reliability)
        except Exception as exc:  # noqa: BLE001
            long_horizon_read_error = str(exc)
    elif ns.require_novel_long_horizon:
        long_horizon_read_error = f"missing file: {ns.novel_long_horizon_reliability}"

    myopic_planning_summary: dict[str, Any] | None = None
    myopic_planning_read_error = ""
    if ns.myopic_planning_reliability.exists():
        try:
            myopic_planning_summary = _read_json(ns.myopic_planning_reliability)
        except Exception as exc:  # noqa: BLE001
            myopic_planning_read_error = str(exc)
    elif ns.require_myopic_planning:
        myopic_planning_read_error = f"missing file: {ns.myopic_planning_reliability}"

    referential_summary: dict[str, Any] | None = None
    referential_read_error = ""
    if ns.referential_indexing_reliability.exists():
        try:
            referential_summary = _read_json(ns.referential_indexing_reliability)
        except Exception as exc:  # noqa: BLE001
            referential_read_error = str(exc)
    elif ns.require_referential_indexing:
        referential_read_error = f"missing file: {ns.referential_indexing_reliability}"

    epistemic_summary: dict[str, Any] | None = None
    epistemic_read_error = ""
    if ns.epistemic_reliability.exists():
        try:
            epistemic_summary = _read_json(ns.epistemic_reliability)
        except Exception as exc:  # noqa: BLE001
            epistemic_read_error = str(exc)
    elif ns.require_epistemic:
        epistemic_read_error = f"missing file: {ns.epistemic_reliability}"

    authority_hardening_summary: dict[str, Any] | None = None
    authority_hardening_read_error = ""
    if ns.authority_hardening_reliability.exists():
        try:
            authority_hardening_summary = _read_json(ns.authority_hardening_reliability)
        except Exception as exc:  # noqa: BLE001
            authority_hardening_read_error = str(exc)
    elif ns.require_authority_hardening:
        authority_hardening_read_error = f"missing file: {ns.authority_hardening_reliability}"

    rpa_mode_switch_summary: dict[str, Any] | None = None
    rpa_mode_switch_read_error = ""
    if ns.rpa_mode_switch_reliability.exists():
        try:
            rpa_mode_switch_summary = _read_json(ns.rpa_mode_switch_reliability)
        except Exception as exc:  # noqa: BLE001
            rpa_mode_switch_read_error = str(exc)
    elif ns.require_rpa_mode_switch:
        rpa_mode_switch_read_error = f"missing file: {ns.rpa_mode_switch_reliability}"

    intent_spec_summary: dict[str, Any] | None = None
    intent_spec_read_error = ""
    if ns.intent_spec_reliability.exists():
        try:
            intent_spec_summary = _read_json(ns.intent_spec_reliability)
        except Exception as exc:  # noqa: BLE001
            intent_spec_read_error = str(exc)
    elif ns.require_intent_spec:
        intent_spec_read_error = f"missing file: {ns.intent_spec_reliability}"

    noise_escalation_summary: dict[str, Any] | None = None
    noise_escalation_read_error = ""
    if ns.noise_escalation_reliability.exists():
        try:
            noise_escalation_summary = _read_json(ns.noise_escalation_reliability)
        except Exception as exc:  # noqa: BLE001
            noise_escalation_read_error = str(exc)
    elif ns.require_noise_escalation:
        noise_escalation_read_error = f"missing file: {ns.noise_escalation_reliability}"

    lines.append(f"Strict summary: {strict_summary_path}")
    lines.append(f"Compression reliability: {ns.compression_reliability}")
    lines.append(f"Novel continuity reliability: {ns.novel_reliability}")
    lines.append(f"Authority-under-interference reliability: {ns.authority_interference_reliability}")
    lines.append(f"Compression roundtrip reliability: {ns.compression_roundtrip_reliability}")
    lines.append(f"Novel long-horizon reliability: {ns.novel_long_horizon_reliability}")
    lines.append(f"Myopic planning reliability: {ns.myopic_planning_reliability}")
    lines.append(f"Referential indexing reliability: {ns.referential_indexing_reliability}")
    lines.append(f"Epistemic reliability: {ns.epistemic_reliability}")
    lines.append(f"Authority hardening reliability: {ns.authority_hardening_reliability}")
    lines.append(f"RPA mode-switch reliability: {ns.rpa_mode_switch_reliability}")
    lines.append(f"Intent-spec reliability: {ns.intent_spec_reliability}")
    lines.append(f"Noise-escalation reliability: {ns.noise_escalation_reliability}")

    strict_status = strict_summary.get("status")
    strict_ok = strict_status == "PASS"
    lines.append(f"[{'PASS' if strict_ok else 'FAIL'}] strict.status={strict_status}")
    if not strict_ok:
        failures.append("strict.status != PASS")

    means = _means(strict_summary)
    _metric_check(
        name="value_acc",
        value=means.get("value_acc"),
        minimum=ns.min_value_acc,
        lines=lines,
        failures=failures,
    )
    _metric_check(
        name="exact_acc",
        value=means.get("exact_acc"),
        minimum=ns.min_exact_acc,
        lines=lines,
        failures=failures,
    )
    _metric_check(
        name="cite_f1",
        value=means.get("cite_f1"),
        minimum=ns.min_cite_f1,
        lines=lines,
        failures=failures,
    )
    _metric_check(
        name="instruction_acc",
        value=means.get("instruction_acc"),
        minimum=ns.min_instruction_acc,
        lines=lines,
        failures=failures,
    )
    _metric_check(
        name="state_integrity_rate",
        value=means.get("state_integrity_rate"),
        minimum=ns.min_state_integrity_rate,
        lines=lines,
        failures=failures,
    )

    if not ns.skip_domain_hard_checks:
        by_id = _dataset_map(strict_summary)
        for dataset_id in ("domain_stale", "domain_authority", "domain_exception"):
            row = by_id.get(dataset_id)
            exact: float | None = None
            if isinstance(row, dict):
                exact_raw = row.get("exact_acc")
                if isinstance(exact_raw, (int, float)):
                    exact = float(exact_raw)
            ok = exact is not None and exact >= 1.0
            if exact is None:
                lines.append(f"[FAIL] strict.{dataset_id}.exact_acc=<missing> == 1.000000")
                failures.append(f"strict.{dataset_id}.exact_acc missing")
            else:
                lines.append(
                    f"[{'PASS' if ok else 'FAIL'}] strict.{dataset_id}.exact_acc={exact:.6f} == 1.000000"
                )
                if not ok:
                    failures.append(f"strict.{dataset_id}.exact_acc != 1.0")

    comp_status = compression_summary.get("status")
    comp_ok = comp_status == "PASS"
    lines.append(f"[{'PASS' if comp_ok else 'FAIL'}] compression.status={comp_status}")
    if not comp_ok:
        failures.append("compression_reliability.status != PASS")

    novel_status = novel_summary.get("status")
    novel_ok = novel_status == "PASS"
    lines.append(f"[{'PASS' if novel_ok else 'FAIL'}] novel_continuity.status={novel_status}")
    if not novel_ok:
        failures.append("novel_continuity_reliability.status != PASS")

    authority_status = authority_summary.get("status")
    authority_ok = authority_status == "PASS"
    lines.append(
        f"[{'PASS' if authority_ok else 'FAIL'}] authority_under_interference.status={authority_status}"
    )
    if not authority_ok:
        failures.append("authority_under_interference_reliability.status != PASS")

    if compression_roundtrip_summary is not None:
        compression_roundtrip_status = compression_roundtrip_summary.get("status")
        compression_roundtrip_ok = compression_roundtrip_status == "PASS"
        lines.append(
            f"[{'PASS' if compression_roundtrip_ok else 'FAIL'}] compression_roundtrip_generalization.status={compression_roundtrip_status}"
        )
        if not compression_roundtrip_ok:
            failures.append("compression_roundtrip_generalization_reliability.status != PASS")
    elif ns.require_compression_roundtrip:
        lines.append(
            f"[FAIL] compression_roundtrip_generalization.status=<missing> ({compression_roundtrip_read_error})"
        )
        failures.append("compression_roundtrip_generalization_reliability missing")
    else:
        if compression_roundtrip_read_error:
            lines.append(
                "[SKIP] compression_roundtrip_generalization.status - "
                f"unreadable optional artifact ({compression_roundtrip_read_error})"
            )
        else:
            lines.append("[SKIP] compression_roundtrip_generalization.status - optional artifact missing")

    if long_horizon_summary is not None:
        long_horizon_status = long_horizon_summary.get("status")
        long_horizon_ok = long_horizon_status == "PASS"
        lines.append(
            f"[{'PASS' if long_horizon_ok else 'FAIL'}] novel_continuity_long_horizon.status={long_horizon_status}"
        )
        if not long_horizon_ok:
            failures.append("novel_continuity_long_horizon_reliability.status != PASS")
    elif ns.require_novel_long_horizon:
        lines.append(
            f"[FAIL] novel_continuity_long_horizon.status=<missing> ({long_horizon_read_error})"
        )
        failures.append("novel_continuity_long_horizon_reliability missing")
    else:
        if long_horizon_read_error:
            lines.append(
                f"[SKIP] novel_continuity_long_horizon.status - unreadable optional artifact ({long_horizon_read_error})"
            )
        else:
            lines.append("[SKIP] novel_continuity_long_horizon.status - optional artifact missing")

    if myopic_planning_summary is not None:
        myopic_planning_status = myopic_planning_summary.get("status")
        myopic_planning_ok = myopic_planning_status == "PASS"
        lines.append(
            f"[{'PASS' if myopic_planning_ok else 'FAIL'}] myopic_planning_traps.status={myopic_planning_status}"
        )
        if not myopic_planning_ok:
            failures.append("myopic_planning_traps_reliability.status != PASS")
    elif ns.require_myopic_planning:
        lines.append(
            f"[FAIL] myopic_planning_traps.status=<missing> ({myopic_planning_read_error})"
        )
        failures.append("myopic_planning_traps_reliability missing")
    else:
        if myopic_planning_read_error:
            lines.append(
                f"[SKIP] myopic_planning_traps.status - unreadable optional artifact ({myopic_planning_read_error})"
            )
        else:
            lines.append("[SKIP] myopic_planning_traps.status - optional artifact missing")

    if referential_summary is not None:
        referential_status = referential_summary.get("status")
        referential_ok = referential_status == "PASS"
        lines.append(
            f"[{'PASS' if referential_ok else 'FAIL'}] referential_indexing_suite.status={referential_status}"
        )
        if not referential_ok:
            failures.append("referential_indexing_suite_reliability.status != PASS")
    elif ns.require_referential_indexing:
        lines.append(
            f"[FAIL] referential_indexing_suite.status=<missing> ({referential_read_error})"
        )
        failures.append("referential_indexing_suite_reliability missing")
    else:
        if referential_read_error:
            lines.append(
                f"[SKIP] referential_indexing_suite.status - unreadable optional artifact ({referential_read_error})"
            )
        else:
            lines.append("[SKIP] referential_indexing_suite.status - optional artifact missing")

    if epistemic_summary is not None:
        epistemic_status = epistemic_summary.get("status")
        epistemic_ok = epistemic_status == "PASS"
        lines.append(
            f"[{'PASS' if epistemic_ok else 'FAIL'}] epistemic_calibration_suite.status={epistemic_status}"
        )
        if not epistemic_ok:
            failures.append("epistemic_calibration_suite_reliability.status != PASS")
    elif ns.require_epistemic:
        lines.append(
            f"[FAIL] epistemic_calibration_suite.status=<missing> ({epistemic_read_error})"
        )
        failures.append("epistemic_calibration_suite_reliability missing")
    else:
        if epistemic_read_error:
            lines.append(
                f"[SKIP] epistemic_calibration_suite.status - unreadable optional artifact ({epistemic_read_error})"
            )
        else:
            lines.append("[SKIP] epistemic_calibration_suite.status - optional artifact missing")

    if authority_hardening_summary is not None:
        authority_hardening_status = authority_hardening_summary.get("status")
        authority_hardening_ok = authority_hardening_status == "PASS"
        lines.append(
            f"[{'PASS' if authority_hardening_ok else 'FAIL'}] authority_under_interference_hardening.status={authority_hardening_status}"
        )
        if not authority_hardening_ok:
            failures.append("authority_under_interference_hardening_reliability.status != PASS")
    elif ns.require_authority_hardening:
        lines.append(
            f"[FAIL] authority_under_interference_hardening.status=<missing> ({authority_hardening_read_error})"
        )
        failures.append("authority_under_interference_hardening_reliability missing")
    else:
        if authority_hardening_read_error:
            lines.append(
                f"[SKIP] authority_under_interference_hardening.status - unreadable optional artifact ({authority_hardening_read_error})"
            )
        else:
            lines.append("[SKIP] authority_under_interference_hardening.status - optional artifact missing")

    if rpa_mode_switch_summary is not None:
        rpa_mode_switch_status = rpa_mode_switch_summary.get("status")
        rpa_mode_switch_ok = rpa_mode_switch_status == "PASS"
        lines.append(
            f"[{'PASS' if rpa_mode_switch_ok else 'FAIL'}] rpa_mode_switch.status={rpa_mode_switch_status}"
        )
        if not rpa_mode_switch_ok:
            failures.append("rpa_mode_switch_reliability.status != PASS")
    elif ns.require_rpa_mode_switch:
        lines.append(f"[FAIL] rpa_mode_switch.status=<missing> ({rpa_mode_switch_read_error})")
        failures.append("rpa_mode_switch_reliability missing")
    else:
        if rpa_mode_switch_read_error:
            lines.append(
                f"[SKIP] rpa_mode_switch.status - unreadable optional artifact ({rpa_mode_switch_read_error})"
            )
        else:
            lines.append("[SKIP] rpa_mode_switch.status - optional artifact missing")

    if intent_spec_summary is not None:
        intent_spec_status = intent_spec_summary.get("status")
        intent_spec_ok = intent_spec_status == "PASS"
        lines.append(f"[{'PASS' if intent_spec_ok else 'FAIL'}] intent_spec_layer.status={intent_spec_status}")
        if not intent_spec_ok:
            failures.append("intent_spec_layer_reliability.status != PASS")
    elif ns.require_intent_spec:
        lines.append(f"[FAIL] intent_spec_layer.status=<missing> ({intent_spec_read_error})")
        failures.append("intent_spec_layer_reliability missing")
    else:
        if intent_spec_read_error:
            lines.append(
                f"[SKIP] intent_spec_layer.status - unreadable optional artifact ({intent_spec_read_error})"
            )
        else:
            lines.append("[SKIP] intent_spec_layer.status - optional artifact missing")

    if noise_escalation_summary is not None:
        noise_escalation_status = noise_escalation_summary.get("status")
        noise_escalation_ok = noise_escalation_status == "PASS"
        lines.append(
            f"[{'PASS' if noise_escalation_ok else 'FAIL'}] noise_escalation.status={noise_escalation_status}"
        )
        if not noise_escalation_ok:
            failures.append("noise_escalation_reliability.status != PASS")
    elif ns.require_noise_escalation:
        lines.append(f"[FAIL] noise_escalation.status=<missing> ({noise_escalation_read_error})")
        failures.append("noise_escalation_reliability missing")
    else:
        if noise_escalation_read_error:
            lines.append(
                f"[SKIP] noise_escalation.status - unreadable optional artifact ({noise_escalation_read_error})"
            )
        else:
            lines.append("[SKIP] noise_escalation.status - optional artifact missing")

    novel_holdout_means, novel_holdout_means_error = _holdout_means_from_family_reliability(novel_summary)
    long_horizon_holdout_means, long_horizon_holdout_means_error = _holdout_means_from_family_reliability(
        long_horizon_summary
    )
    myopic_holdout_means, myopic_holdout_means_error = _holdout_means_from_family_reliability(
        myopic_planning_summary
    )
    referential_holdout_means, referential_holdout_means_error = _holdout_means_from_family_reliability(
        referential_summary
    )
    epistemic_holdout_means, epistemic_holdout_means_error = _holdout_means_from_family_reliability(
        epistemic_summary
    )
    compression_roundtrip_holdout_means, compression_roundtrip_holdout_means_error = (
        _holdout_means_from_family_reliability(compression_roundtrip_summary)
    )
    authority_holdout_means, authority_holdout_means_error = _holdout_means_from_family_reliability(
        authority_hardening_summary if authority_hardening_summary is not None else authority_summary
    )

    derived_scores = _derive_scores(
        strict_means=means,
        novel_means=novel_holdout_means,
        long_horizon_means=long_horizon_holdout_means,
        myopic_means=myopic_holdout_means,
        referential_means=referential_holdout_means,
        epistemic_means=epistemic_holdout_means,
        authority_means=authority_holdout_means,
        compression_roundtrip_means=compression_roundtrip_holdout_means,
    )

    reasoning_score = derived_scores["reasoning_score"]
    planning_score = derived_scores["planning_score"]
    intelligence_index = derived_scores["intelligence_index"]
    reasoning_components = derived_scores["reasoning_components"]
    planning_components = derived_scores["planning_components"]

    if reasoning_score is None:
        lines.append("[SKIP] derived.reasoning_score=<missing> (insufficient component metrics)")
    else:
        lines.append(f"[INFO] derived.reasoning_score={reasoning_score:.6f}")
        parts = ", ".join(
            f"{name}={value:.3f}" for name, value in reasoning_components.items() if value is not None
        )
        if parts:
            lines.append(f"[INFO] derived.reasoning_components: {parts}")

    if planning_score is None:
        lines.append("[SKIP] derived.planning_score=<missing> (insufficient component metrics)")
    else:
        lines.append(f"[INFO] derived.planning_score={planning_score:.6f}")
        parts = ", ".join(
            f"{name}={value:.3f}" for name, value in planning_components.items() if value is not None
        )
        if parts:
            lines.append(f"[INFO] derived.planning_components: {parts}")

    if intelligence_index is None:
        lines.append("[SKIP] derived.intelligence_index=<missing> (requires reasoning_score and planning_score)")
    else:
        lines.append(f"[INFO] derived.intelligence_index={intelligence_index:.6f}")

    if ns.min_reasoning_score is not None:
        if reasoning_score is None:
            lines.append(
                f"[FAIL] derived.reasoning_score=<missing> >= {ns.min_reasoning_score:.6f}"
            )
            failures.append("derived.reasoning_score missing")
        else:
            reasoning_ok = reasoning_score >= ns.min_reasoning_score
            lines.append(
                f"[{'PASS' if reasoning_ok else 'FAIL'}] derived.reasoning_score={reasoning_score:.6f} >= {ns.min_reasoning_score:.6f}"
            )
            if not reasoning_ok:
                failures.append(f"derived.reasoning_score < {ns.min_reasoning_score}")

    if ns.min_planning_score is not None:
        if planning_score is None:
            lines.append(
                f"[FAIL] derived.planning_score=<missing> >= {ns.min_planning_score:.6f}"
            )
            failures.append("derived.planning_score missing")
        else:
            planning_ok = planning_score >= ns.min_planning_score
            lines.append(
                f"[{'PASS' if planning_ok else 'FAIL'}] derived.planning_score={planning_score:.6f} >= {ns.min_planning_score:.6f}"
            )
            if not planning_ok:
                failures.append(f"derived.planning_score < {ns.min_planning_score}")

    if ns.min_intelligence_index is not None:
        if intelligence_index is None:
            lines.append(
                f"[FAIL] derived.intelligence_index=<missing> >= {ns.min_intelligence_index:.6f}"
            )
            failures.append("derived.intelligence_index missing")
        else:
            index_ok = intelligence_index >= ns.min_intelligence_index
            lines.append(
                f"[{'PASS' if index_ok else 'FAIL'}] derived.intelligence_index={intelligence_index:.6f} >= {ns.min_intelligence_index:.6f}"
            )
            if not index_ok:
                failures.append(f"derived.intelligence_index < {ns.min_intelligence_index}")

    overall = "PASS" if not failures else "FAIL"
    lines.append(f"RESULT: {overall}")
    print("\n".join(lines))

    payload = {
        "benchmark": "reliability_signal",
        "strict_summary_path": str(strict_summary_path),
        "compression_reliability_path": str(ns.compression_reliability),
        "novel_continuity_reliability_path": str(ns.novel_reliability),
        "authority_under_interference_reliability_path": str(ns.authority_interference_reliability),
        "compression_roundtrip_generalization_reliability_path": str(ns.compression_roundtrip_reliability),
        "require_compression_roundtrip": ns.require_compression_roundtrip,
        "novel_continuity_long_horizon_reliability_path": str(ns.novel_long_horizon_reliability),
        "require_novel_long_horizon": ns.require_novel_long_horizon,
        "myopic_planning_traps_reliability_path": str(ns.myopic_planning_reliability),
        "require_myopic_planning": ns.require_myopic_planning,
        "referential_indexing_suite_reliability_path": str(ns.referential_indexing_reliability),
        "require_referential_indexing": ns.require_referential_indexing,
        "epistemic_calibration_suite_reliability_path": str(ns.epistemic_reliability),
        "require_epistemic": ns.require_epistemic,
        "authority_under_interference_hardening_reliability_path": str(ns.authority_hardening_reliability),
        "require_authority_hardening": ns.require_authority_hardening,
        "rpa_mode_switch_reliability_path": str(ns.rpa_mode_switch_reliability),
        "require_rpa_mode_switch": ns.require_rpa_mode_switch,
        "intent_spec_layer_reliability_path": str(ns.intent_spec_reliability),
        "require_intent_spec": ns.require_intent_spec,
        "noise_escalation_reliability_path": str(ns.noise_escalation_reliability),
        "require_noise_escalation": ns.require_noise_escalation,
        "status": overall,
        "failures": failures,
        "thresholds": {
            "min_value_acc": ns.min_value_acc,
            "min_exact_acc": ns.min_exact_acc,
            "min_cite_f1": ns.min_cite_f1,
            "min_instruction_acc": ns.min_instruction_acc,
            "min_state_integrity_rate": ns.min_state_integrity_rate,
            "min_reasoning_score": ns.min_reasoning_score,
            "min_planning_score": ns.min_planning_score,
            "min_intelligence_index": ns.min_intelligence_index,
            "skip_domain_hard_checks": ns.skip_domain_hard_checks,
        },
        "derived": {
            "reasoning_score": reasoning_score,
            "planning_score": planning_score,
            "intelligence_index": intelligence_index,
            "reasoning_components": reasoning_components,
            "planning_components": planning_components,
            "component_source_diagnostics": {
                "novel_continuity": novel_holdout_means_error,
                "novel_continuity_long_horizon": long_horizon_holdout_means_error,
                "myopic_planning_traps": myopic_holdout_means_error,
                "referential_indexing_suite": referential_holdout_means_error,
                "epistemic_calibration_suite": epistemic_holdout_means_error,
                "compression_roundtrip_generalization": compression_roundtrip_holdout_means_error,
                "authority": authority_holdout_means_error,
            },
        },
    }
    ns.out.parent.mkdir(parents=True, exist_ok=True)
    ns.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {ns.out}")

    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
