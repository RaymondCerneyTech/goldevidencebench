from __future__ import annotations

import argparse
import json
import math
import sys
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
        "--profile",
        choices=("fastlocal", "release"),
        default="release",
        help=(
            "Reliability policy profile. "
            "`release` enforces full family matrix when require flags are set by wrapper; "
            "`fastlocal` allows partial matrix for iteration."
        ),
    )
    parser.add_argument(
        "--allow-mock-canary-soft-fail",
        action="store_true",
        help=(
            "Downgrade canary-only family reliability FAIL statuses to WARN. "
            "Intended for fastlocal iteration with mock adapters."
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
    parser.add_argument(
        "--implication-coherence-reliability",
        type=Path,
        default=Path("runs/implication_coherence_reliability_latest.json"),
        help="Path to implication-coherence reliability summary JSON.",
    )
    parser.add_argument(
        "--require-implication-coherence",
        action="store_true",
        help="Require implication-coherence reliability summary to exist and PASS.",
    )
    parser.add_argument(
        "--agency-preserving-substitution-reliability",
        type=Path,
        default=Path("runs/agency_preserving_substitution_reliability_latest.json"),
        help="Path to agency-preserving-substitution reliability summary JSON.",
    )
    parser.add_argument(
        "--require-agency-preserving-substitution",
        action="store_true",
        help="Require agency-preserving-substitution reliability summary to exist and PASS.",
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


def _canary_only_reliability_failure(reliability_summary: dict[str, Any]) -> bool:
    status = str(reliability_summary.get("status", "")).upper()
    if status != "FAIL":
        return False
    raw_failures = reliability_summary.get("failures")
    if not isinstance(raw_failures, list) or not raw_failures:
        return False
    failures = [str(item).strip().lower() for item in raw_failures if str(item).strip()]
    if not failures:
        return False
    only_canary_or_hard_gate_fail = True
    has_canary_marker = False
    has_hard_gate_marker = False
    for message in failures:
        if "canary.exact_rate" in message:
            has_canary_marker = True
            continue
        if "hard_gate_status" in message and "!= pass" in message:
            has_hard_gate_marker = True
            continue
        only_canary_or_hard_gate_fail = False
        break
    if not only_canary_or_hard_gate_fail or (not has_canary_marker and not has_hard_gate_marker):
        return False

    runs = reliability_summary.get("runs")
    family_id = _reliability_benchmark_to_family(reliability_summary)
    if not isinstance(runs, list) or not runs or not family_id:
        return has_canary_marker
    latest_run = runs[-1]
    if not isinstance(latest_run, str) or not latest_run.strip():
        return has_canary_marker

    summary_path = Path(latest_run) / f"{family_id}_summary.json"
    if not summary_path.exists():
        return has_canary_marker
    try:
        run_summary = _read_json(summary_path)
    except Exception:  # noqa: BLE001
        return has_canary_marker

    anchors_status = str(run_summary.get("anchors", {}).get("status", "")).upper()
    holdout_status = str(run_summary.get("holdout", {}).get("status", "")).upper()
    hard_gate_status = str(run_summary.get("hard_gate_status", "")).upper()
    canary_status = str(run_summary.get("canary_status", "")).upper()
    if anchors_status == "PASS" and holdout_status == "PASS":
        if canary_status in {"WARN", "FAIL"}:
            return True
        if hard_gate_status == "FAIL" and canary_status in {"", "OK"}:
            return True
    return has_canary_marker


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
    implication_coherence_means: dict[str, float] | None,
    agency_preservation_means: dict[str, float] | None,
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
    implication_coherence_core = _average(
        [
            value
            for value in [
                _normalized_metric(implication_coherence_means, "ic_score"),
                _normalized_metric(implication_coherence_means, "implication_consistency_rate"),
                _normalized_metric(implication_coherence_means, "dependency_coverage"),
                _normalized_metric(implication_coherence_means, "contradiction_repair_rate"),
                _normalized_metric(implication_coherence_means, "causal_precision"),
                _normalized_metric(implication_coherence_means, "implication_break_rate", invert=True),
            ]
            if value is not None
        ]
    )
    agency_preservation_core = _average(
        [
            value
            for value in [
                _normalized_metric(agency_preservation_means, "substitution_transparency_rate"),
                _normalized_metric(agency_preservation_means, "unauthorized_substitution_rate", invert=True),
                _normalized_metric(agency_preservation_means, "intent_preservation_score"),
                _normalized_metric(agency_preservation_means, "agency_loss_error_rate", invert=True),
                _normalized_metric(agency_preservation_means, "recovery_success_rate"),
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
        "implication_coherence_core": implication_coherence_core,
        "agency_preservation_core": agency_preservation_core,
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
    lines.append(f"Profile: {ns.profile}")
    failures: list[str] = []
    cli_args = set(sys.argv[1:])

    def _arg_provided(flag: str) -> bool:
        return flag in cli_args

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
    probe_compression_roundtrip = ns.require_compression_roundtrip or _arg_provided(
        "--compression-roundtrip-reliability"
    )
    if probe_compression_roundtrip and ns.compression_roundtrip_reliability.exists():
        try:
            compression_roundtrip_summary = _read_json(ns.compression_roundtrip_reliability)
        except Exception as exc:  # noqa: BLE001
            compression_roundtrip_read_error = str(exc)
    elif ns.require_compression_roundtrip:
        compression_roundtrip_read_error = f"missing file: {ns.compression_roundtrip_reliability}"

    long_horizon_summary: dict[str, Any] | None = None
    long_horizon_read_error = ""
    probe_novel_long_horizon = ns.require_novel_long_horizon or _arg_provided(
        "--novel-long-horizon-reliability"
    )
    if probe_novel_long_horizon and ns.novel_long_horizon_reliability.exists():
        try:
            long_horizon_summary = _read_json(ns.novel_long_horizon_reliability)
        except Exception as exc:  # noqa: BLE001
            long_horizon_read_error = str(exc)
    elif ns.require_novel_long_horizon:
        long_horizon_read_error = f"missing file: {ns.novel_long_horizon_reliability}"

    myopic_planning_summary: dict[str, Any] | None = None
    myopic_planning_read_error = ""
    probe_myopic_planning = ns.require_myopic_planning or _arg_provided("--myopic-planning-reliability")
    if probe_myopic_planning and ns.myopic_planning_reliability.exists():
        try:
            myopic_planning_summary = _read_json(ns.myopic_planning_reliability)
        except Exception as exc:  # noqa: BLE001
            myopic_planning_read_error = str(exc)
    elif ns.require_myopic_planning:
        myopic_planning_read_error = f"missing file: {ns.myopic_planning_reliability}"

    referential_summary: dict[str, Any] | None = None
    referential_read_error = ""
    probe_referential_indexing = ns.require_referential_indexing or _arg_provided(
        "--referential-indexing-reliability"
    )
    if probe_referential_indexing and ns.referential_indexing_reliability.exists():
        try:
            referential_summary = _read_json(ns.referential_indexing_reliability)
        except Exception as exc:  # noqa: BLE001
            referential_read_error = str(exc)
    elif ns.require_referential_indexing:
        referential_read_error = f"missing file: {ns.referential_indexing_reliability}"

    epistemic_summary: dict[str, Any] | None = None
    epistemic_read_error = ""
    probe_epistemic = ns.require_epistemic or _arg_provided("--epistemic-reliability")
    if probe_epistemic and ns.epistemic_reliability.exists():
        try:
            epistemic_summary = _read_json(ns.epistemic_reliability)
        except Exception as exc:  # noqa: BLE001
            epistemic_read_error = str(exc)
    elif ns.require_epistemic:
        epistemic_read_error = f"missing file: {ns.epistemic_reliability}"

    authority_hardening_summary: dict[str, Any] | None = None
    authority_hardening_read_error = ""
    probe_authority_hardening = ns.require_authority_hardening or _arg_provided(
        "--authority-hardening-reliability"
    )
    if probe_authority_hardening and ns.authority_hardening_reliability.exists():
        try:
            authority_hardening_summary = _read_json(ns.authority_hardening_reliability)
        except Exception as exc:  # noqa: BLE001
            authority_hardening_read_error = str(exc)
    elif ns.require_authority_hardening:
        authority_hardening_read_error = f"missing file: {ns.authority_hardening_reliability}"

    rpa_mode_switch_summary: dict[str, Any] | None = None
    rpa_mode_switch_read_error = ""
    probe_rpa_mode_switch = ns.require_rpa_mode_switch or _arg_provided("--rpa-mode-switch-reliability")
    if probe_rpa_mode_switch and ns.rpa_mode_switch_reliability.exists():
        try:
            rpa_mode_switch_summary = _read_json(ns.rpa_mode_switch_reliability)
        except Exception as exc:  # noqa: BLE001
            rpa_mode_switch_read_error = str(exc)
    elif ns.require_rpa_mode_switch:
        rpa_mode_switch_read_error = f"missing file: {ns.rpa_mode_switch_reliability}"

    intent_spec_summary: dict[str, Any] | None = None
    intent_spec_read_error = ""
    probe_intent_spec = ns.require_intent_spec or _arg_provided("--intent-spec-reliability")
    if probe_intent_spec and ns.intent_spec_reliability.exists():
        try:
            intent_spec_summary = _read_json(ns.intent_spec_reliability)
        except Exception as exc:  # noqa: BLE001
            intent_spec_read_error = str(exc)
    elif ns.require_intent_spec:
        intent_spec_read_error = f"missing file: {ns.intent_spec_reliability}"

    noise_escalation_summary: dict[str, Any] | None = None
    noise_escalation_read_error = ""
    probe_noise_escalation = ns.require_noise_escalation or _arg_provided("--noise-escalation-reliability")
    if probe_noise_escalation and ns.noise_escalation_reliability.exists():
        try:
            noise_escalation_summary = _read_json(ns.noise_escalation_reliability)
        except Exception as exc:  # noqa: BLE001
            noise_escalation_read_error = str(exc)
    elif ns.require_noise_escalation:
        noise_escalation_read_error = f"missing file: {ns.noise_escalation_reliability}"

    implication_coherence_summary: dict[str, Any] | None = None
    implication_coherence_read_error = ""
    probe_implication_coherence = ns.require_implication_coherence or _arg_provided(
        "--implication-coherence-reliability"
    )
    if probe_implication_coherence and ns.implication_coherence_reliability.exists():
        try:
            implication_coherence_summary = _read_json(ns.implication_coherence_reliability)
        except Exception as exc:  # noqa: BLE001
            implication_coherence_read_error = str(exc)
    elif ns.require_implication_coherence:
        implication_coherence_read_error = f"missing file: {ns.implication_coherence_reliability}"

    agency_preserving_substitution_summary: dict[str, Any] | None = None
    agency_preserving_substitution_read_error = ""
    probe_agency_preserving_substitution = ns.require_agency_preserving_substitution or _arg_provided(
        "--agency-preserving-substitution-reliability"
    )
    if probe_agency_preserving_substitution and ns.agency_preserving_substitution_reliability.exists():
        try:
            agency_preserving_substitution_summary = _read_json(ns.agency_preserving_substitution_reliability)
        except Exception as exc:  # noqa: BLE001
            agency_preserving_substitution_read_error = str(exc)
    elif ns.require_agency_preserving_substitution:
        agency_preserving_substitution_read_error = (
            f"missing file: {ns.agency_preserving_substitution_reliability}"
        )

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
    lines.append(f"Implication-coherence reliability: {ns.implication_coherence_reliability}")
    lines.append(
        "Agency-preserving-substitution reliability: "
        f"{ns.agency_preserving_substitution_reliability}"
    )

    def _append_family_status(
        label: str,
        summary: dict[str, Any] | None,
        *,
        failure_key: str,
        required: bool,
        read_error: str = "",
    ) -> None:
        if summary is not None:
            status = str(summary.get("status", ""))
            ok = status == "PASS"
            if (
                not ok
                and ns.profile == "fastlocal"
                and ns.allow_mock_canary_soft_fail
                and _canary_only_reliability_failure(summary)
            ):
                lines.append(f"[WARN] {label}.status={status} (canary-only soft-fail in fastlocal profile)")
                return
            lines.append(f"[{'PASS' if ok else 'FAIL'}] {label}.status={status}")
            if not ok:
                failures.append(failure_key)
            return
        if required:
            lines.append(f"[FAIL] {label}.status=<missing> ({read_error})")
            failures.append(f"{failure_key} missing")
            return
        if read_error:
            lines.append(f"[SKIP] {label}.status - unreadable optional artifact ({read_error})")
        else:
            lines.append(f"[SKIP] {label}.status - optional artifact missing")

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

    _append_family_status(
        "compression",
        compression_summary,
        failure_key="compression_reliability.status != PASS",
        required=True,
    )
    _append_family_status(
        "novel_continuity",
        novel_summary,
        failure_key="novel_continuity_reliability.status != PASS",
        required=True,
    )
    _append_family_status(
        "authority_under_interference",
        authority_summary,
        failure_key="authority_under_interference_reliability.status != PASS",
        required=True,
    )
    _append_family_status(
        "compression_roundtrip_generalization",
        compression_roundtrip_summary,
        failure_key="compression_roundtrip_generalization_reliability.status != PASS",
        required=ns.require_compression_roundtrip,
        read_error=compression_roundtrip_read_error,
    )
    _append_family_status(
        "novel_continuity_long_horizon",
        long_horizon_summary,
        failure_key="novel_continuity_long_horizon_reliability.status != PASS",
        required=ns.require_novel_long_horizon,
        read_error=long_horizon_read_error,
    )
    _append_family_status(
        "myopic_planning_traps",
        myopic_planning_summary,
        failure_key="myopic_planning_traps_reliability.status != PASS",
        required=ns.require_myopic_planning,
        read_error=myopic_planning_read_error,
    )
    _append_family_status(
        "referential_indexing_suite",
        referential_summary,
        failure_key="referential_indexing_suite_reliability.status != PASS",
        required=ns.require_referential_indexing,
        read_error=referential_read_error,
    )
    _append_family_status(
        "epistemic_calibration_suite",
        epistemic_summary,
        failure_key="epistemic_calibration_suite_reliability.status != PASS",
        required=ns.require_epistemic,
        read_error=epistemic_read_error,
    )
    _append_family_status(
        "authority_under_interference_hardening",
        authority_hardening_summary,
        failure_key="authority_under_interference_hardening_reliability.status != PASS",
        required=ns.require_authority_hardening,
        read_error=authority_hardening_read_error,
    )
    _append_family_status(
        "rpa_mode_switch",
        rpa_mode_switch_summary,
        failure_key="rpa_mode_switch_reliability.status != PASS",
        required=ns.require_rpa_mode_switch,
        read_error=rpa_mode_switch_read_error,
    )
    _append_family_status(
        "intent_spec_layer",
        intent_spec_summary,
        failure_key="intent_spec_layer_reliability.status != PASS",
        required=ns.require_intent_spec,
        read_error=intent_spec_read_error,
    )
    _append_family_status(
        "noise_escalation",
        noise_escalation_summary,
        failure_key="noise_escalation_reliability.status != PASS",
        required=ns.require_noise_escalation,
        read_error=noise_escalation_read_error,
    )
    _append_family_status(
        "implication_coherence",
        implication_coherence_summary,
        failure_key="implication_coherence_reliability.status != PASS",
        required=ns.require_implication_coherence,
        read_error=implication_coherence_read_error,
    )
    _append_family_status(
        "agency_preserving_substitution",
        agency_preserving_substitution_summary,
        failure_key="agency_preserving_substitution_reliability.status != PASS",
        required=ns.require_agency_preserving_substitution,
        read_error=agency_preserving_substitution_read_error,
    )

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
    implication_holdout_means, implication_holdout_means_error = _holdout_means_from_family_reliability(
        implication_coherence_summary
    )
    agency_holdout_means, agency_holdout_means_error = _holdout_means_from_family_reliability(
        agency_preserving_substitution_summary
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
        implication_coherence_means=implication_holdout_means,
        agency_preservation_means=agency_holdout_means,
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
        "profile": ns.profile,
        "allow_mock_canary_soft_fail": ns.allow_mock_canary_soft_fail,
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
        "implication_coherence_reliability_path": str(ns.implication_coherence_reliability),
        "require_implication_coherence": ns.require_implication_coherence,
        "agency_preserving_substitution_reliability_path": str(
            ns.agency_preserving_substitution_reliability
        ),
        "require_agency_preserving_substitution": ns.require_agency_preserving_substitution,
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
                "implication_coherence": implication_holdout_means_error,
                "agency_preserving_substitution": agency_holdout_means_error,
            },
        },
    }
    ns.out.parent.mkdir(parents=True, exist_ok=True)
    ns.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {ns.out}")

    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
