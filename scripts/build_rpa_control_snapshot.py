from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a runtime Reason-Plan-Act (RPA) controller snapshot from "
            "latest reliability artifacts."
        )
    )
    parser.add_argument(
        "--reliability-signal",
        type=Path,
        default=Path("runs/reliability_signal_latest.json"),
        help="Unified reliability signal JSON.",
    )
    parser.add_argument(
        "--epistemic-reliability",
        type=Path,
        default=Path("runs/epistemic_calibration_suite_reliability_latest.json"),
        help="Epistemic suite reliability JSON.",
    )
    parser.add_argument(
        "--authority-reliability",
        type=Path,
        default=Path("runs/authority_under_interference_hardening_reliability_latest.json"),
        help="Authority hardening reliability JSON.",
    )
    parser.add_argument(
        "--myopic-reliability",
        type=Path,
        default=Path("runs/myopic_planning_traps_reliability_latest.json"),
        help="Myopic planning reliability JSON.",
    )
    parser.add_argument(
        "--referential-reliability",
        type=Path,
        default=Path("runs/referential_indexing_suite_reliability_latest.json"),
        help="Referential indexing reliability JSON.",
    )
    parser.add_argument(
        "--novel-long-horizon-reliability",
        type=Path,
        default=Path("runs/novel_continuity_long_horizon_reliability_latest.json"),
        help="Novel continuity long-horizon reliability JSON.",
    )
    parser.add_argument(
        "--reversibility",
        choices=("reversible", "irreversible"),
        default="reversible",
        help="Action reversibility for current step.",
    )
    parser.add_argument(
        "--mode",
        choices=("auto", "reason", "plan", "act"),
        default="auto",
        help="Force mode or let controller choose automatically.",
    )
    parser.add_argument("--confidence-floor", type=float, default=0.70)
    parser.add_argument("--planning-floor", type=float, default=0.90)
    parser.add_argument("--reasoning-floor", type=float, default=0.90)
    parser.add_argument("--needed-info-floor", type=float, default=0.75)
    parser.add_argument("--risk-floor", type=float, default=0.50)
    parser.add_argument("--irreversible-confidence-floor", type=float, default=0.85)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("runs/rpa_control_latest.json"),
        help="Output RPA controller snapshot JSON.",
    )
    return parser.parse_args()


def _read_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid JSON object: {path}")
    return raw


def _read_json_if_exists(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, f"missing: {path}"
    try:
        return _read_json(path), None
    except Exception as exc:  # pragma: no cover - defensive
        return None, str(exc)


def _as_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / float(len(values))


def _latest_existing_run_dir(summary: dict[str, Any] | None) -> Path | None:
    if summary is None:
        return None
    runs = summary.get("runs")
    if not isinstance(runs, list):
        return None
    for run_dir in reversed(runs):
        if not isinstance(run_dir, str):
            continue
        run_path = Path(run_dir)
        if run_path.exists() and run_path.is_dir():
            return run_path
    return None


def _holdout_means_from_reliability(summary: dict[str, Any] | None) -> dict[str, float]:
    run_dir = _latest_existing_run_dir(summary)
    if run_dir is None:
        return {}
    holdout_path = run_dir / "holdout_summary.json"
    if not holdout_path.exists():
        return {}
    try:
        holdout_summary = _read_json(holdout_path)
    except Exception:
        return {}
    means = holdout_summary.get("means")
    if not isinstance(means, dict):
        return {}
    out: dict[str, float] = {}
    for key, value in means.items():
        if isinstance(value, (int, float)):
            out[key] = float(value)
    return out


def _push_risk(
    risk_terms: list[dict[str, Any]],
    condition: bool,
    weight: float,
    reason: str,
) -> None:
    if condition:
        risk_terms.append({"weight": float(weight), "reason": reason})


def _reason_list(risk_terms: list[dict[str, Any]]) -> list[str]:
    if not risk_terms:
        return ["All configured reliability/control signals are inside target floors."]
    return [str(item["reason"]) for item in risk_terms]


def _unique_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _controller_decision(
    *,
    force_mode: str,
    reversibility: str,
    confidence: float,
    risk: float,
    needed_info: list[str],
    authority_hot: bool,
    planning_hot: bool,
    confidence_floor: float,
    risk_floor: float,
    irreversible_confidence_floor: float,
    reliability_status: str | None,
) -> tuple[str, str]:
    if reliability_status != "PASS":
        if reversibility == "irreversible":
            return "reason", "defer"
        return "reason", "retrieve"

    if force_mode != "auto":
        mode = force_mode
    else:
        if confidence < confidence_floor or needed_info:
            mode = "reason"
        elif planning_hot:
            mode = "plan"
        else:
            mode = "act"

    if mode == "reason":
        if authority_hot:
            return mode, "retrieve"
        if needed_info:
            return mode, "ask"
        if confidence < confidence_floor:
            return mode, "abstain"
        return mode, "retrieve"

    if mode == "plan":
        if reversibility == "irreversible":
            return mode, "verify"
        return mode, "retrieve"

    # mode == "act"
    if reversibility == "irreversible" and (
        confidence < irreversible_confidence_floor or risk >= risk_floor
    ):
        return mode, "verify"
    return mode, "answer"


def main() -> int:
    ns = _parse_args()

    reliability_signal, reliability_err = _read_json_if_exists(ns.reliability_signal)
    epistemic_reliability, epistemic_err = _read_json_if_exists(ns.epistemic_reliability)
    authority_reliability, authority_err = _read_json_if_exists(ns.authority_reliability)
    myopic_reliability, myopic_err = _read_json_if_exists(ns.myopic_reliability)
    referential_reliability, referential_err = _read_json_if_exists(ns.referential_reliability)
    long_horizon_reliability, long_horizon_err = _read_json_if_exists(ns.novel_long_horizon_reliability)

    reliability_status = (
        str(reliability_signal.get("status")) if isinstance(reliability_signal, dict) else None
    )
    reasoning_score = _as_float(
        (reliability_signal or {}).get("derived", {}).get("reasoning_score")
    )
    planning_score = _as_float(
        (reliability_signal or {}).get("derived", {}).get("planning_score")
    )
    intelligence_index = _as_float(
        (reliability_signal or {}).get("derived", {}).get("intelligence_index")
    )

    epistemic_status = (
        str(epistemic_reliability.get("status")) if isinstance(epistemic_reliability, dict) else None
    )
    authority_status = (
        str(authority_reliability.get("status")) if isinstance(authority_reliability, dict) else None
    )
    myopic_status = str(myopic_reliability.get("status")) if isinstance(myopic_reliability, dict) else None
    referential_status = (
        str(referential_reliability.get("status")) if isinstance(referential_reliability, dict) else None
    )
    long_horizon_status = (
        str(long_horizon_reliability.get("status"))
        if isinstance(long_horizon_reliability, dict)
        else None
    )

    epistemic_means = _holdout_means_from_reliability(epistemic_reliability)
    authority_means = _holdout_means_from_reliability(authority_reliability)
    myopic_means = _holdout_means_from_reliability(myopic_reliability)
    referential_means = _holdout_means_from_reliability(referential_reliability)
    long_horizon_means = _holdout_means_from_reliability(long_horizon_reliability)

    overclaim_rate = epistemic_means.get("overclaim_rate")
    abstain_f1 = epistemic_means.get("abstain_f1")
    needed_info_recall = epistemic_means.get("needed_info_recall")
    parse_rate = epistemic_means.get("parse_rate")
    confidence_provided_rate = epistemic_means.get("confidence_provided_rate")
    confidence_proxy_used_rate = epistemic_means.get("confidence_proxy_used_rate")
    kkyi = epistemic_means.get("kkyi")

    authority_violation_rate = authority_means.get("authority_violation_rate")
    latest_support_hit_rate = authority_means.get("latest_support_hit_rate")

    trap_entry_rate = myopic_means.get("trap_entry_rate")
    horizon_success_rate = myopic_means.get("horizon_success_rate")
    recovery_rate = myopic_means.get("recovery_rate")
    first_error_step_mean = myopic_means.get("first_error_step_mean")

    stale_pointer_override_rate = referential_means.get("stale_pointer_override_rate")
    hallucinated_expansion_rate = referential_means.get("hallucinated_expansion_rate")
    reassembly_fidelity = referential_means.get("reassembly_fidelity")

    long_gap_acc = long_horizon_means.get("long_gap_acc")
    high_contradiction_acc = long_horizon_means.get("high_contradiction_acc")

    risk_terms: list[dict[str, Any]] = []
    _push_risk(
        risk_terms,
        reliability_status != "PASS",
        0.35,
        "Unified reliability signal is not PASS.",
    )
    _push_risk(
        risk_terms,
        reasoning_score is None,
        0.10,
        "Derived reasoning score is missing.",
    )
    _push_risk(
        risk_terms,
        planning_score is None,
        0.10,
        "Derived planning score is missing.",
    )
    _push_risk(
        risk_terms,
        reasoning_score is not None and reasoning_score < ns.reasoning_floor,
        0.20,
        f"reasoning_score below floor ({reasoning_score:.3f} < {ns.reasoning_floor:.3f})."
        if reasoning_score is not None
        else "reasoning_score below floor.",
    )
    _push_risk(
        risk_terms,
        planning_score is not None and planning_score < ns.planning_floor,
        0.20,
        f"planning_score below floor ({planning_score:.3f} < {ns.planning_floor:.3f})."
        if planning_score is not None
        else "planning_score below floor.",
    )
    _push_risk(
        risk_terms,
        epistemic_status not in (None, "PASS"),
        0.20,
        "Epistemic calibration reliability is not PASS.",
    )
    _push_risk(
        risk_terms,
        overclaim_rate is not None and overclaim_rate > 0.05,
        0.10,
        "Overclaim rate is above 0.05.",
    )
    _push_risk(
        risk_terms,
        abstain_f1 is not None and abstain_f1 < 0.70,
        0.08,
        "Abstain F1 is below 0.70.",
    )
    _push_risk(
        risk_terms,
        needed_info_recall is not None and needed_info_recall < ns.needed_info_floor,
        0.12,
        f"Needed-info recall below floor ({needed_info_recall:.3f} < {ns.needed_info_floor:.3f}).",
    )
    _push_risk(
        risk_terms,
        parse_rate is not None and parse_rate < 1.0,
        0.10,
        "Structured parse_rate is below 1.0.",
    )
    _push_risk(
        risk_terms,
        confidence_provided_rate is not None and confidence_provided_rate < 1.0,
        0.10,
        "Confidence provided rate is below 1.0.",
    )
    _push_risk(
        risk_terms,
        confidence_proxy_used_rate is not None and confidence_proxy_used_rate > 0.0,
        0.08,
        "Confidence proxy is still being used.",
    )
    _push_risk(
        risk_terms,
        authority_status not in (None, "PASS"),
        0.15,
        "Authority hardening reliability is not PASS.",
    )
    _push_risk(
        risk_terms,
        authority_violation_rate is not None and authority_violation_rate > 0.0,
        0.12,
        "Authority violation rate is non-zero.",
    )
    _push_risk(
        risk_terms,
        latest_support_hit_rate is not None and latest_support_hit_rate < 1.0,
        0.08,
        "Latest-support hit rate is below 1.0.",
    )
    _push_risk(
        risk_terms,
        myopic_status not in (None, "PASS"),
        0.15,
        "Myopic planning reliability is not PASS.",
    )
    _push_risk(
        risk_terms,
        trap_entry_rate is not None and trap_entry_rate > 0.0,
        0.10,
        "Trap-entry rate is non-zero.",
    )
    _push_risk(
        risk_terms,
        horizon_success_rate is not None and horizon_success_rate < 0.85,
        0.10,
        "Horizon success rate is below 0.85.",
    )
    _push_risk(
        risk_terms,
        recovery_rate is not None and recovery_rate < 0.80,
        0.10,
        "Recovery rate is below 0.80.",
    )
    _push_risk(
        risk_terms,
        referential_status not in (None, "PASS"),
        0.10,
        "Referential indexing reliability is not PASS.",
    )
    _push_risk(
        risk_terms,
        hallucinated_expansion_rate is not None and hallucinated_expansion_rate > 0.0,
        0.08,
        "Hallucinated expansion rate is non-zero.",
    )
    _push_risk(
        risk_terms,
        stale_pointer_override_rate is not None and stale_pointer_override_rate > 0.0,
        0.08,
        "Stale pointer override rate is non-zero.",
    )
    _push_risk(
        risk_terms,
        long_horizon_status not in (None, "PASS"),
        0.08,
        "Novel continuity long-horizon reliability is not PASS.",
    )
    _push_risk(
        risk_terms,
        long_gap_acc is not None and long_gap_acc < 0.80,
        0.06,
        "Long-gap continuity accuracy is below 0.80.",
    )
    _push_risk(
        risk_terms,
        high_contradiction_acc is not None and high_contradiction_acc < 0.80,
        0.06,
        "High-contradiction continuity accuracy is below 0.80.",
    )

    pre_confidence_components = [
        value
        for value in (
            intelligence_index,
            reasoning_score,
            planning_score,
            kkyi,
        )
        if value is not None
    ]
    base_confidence = _avg(pre_confidence_components)
    if base_confidence is None:
        base_confidence = 0.50

    _push_risk(
        risk_terms,
        ns.reversibility == "irreversible" and base_confidence < ns.irreversible_confidence_floor,
        0.15,
        (
            "Irreversible action requested while confidence is below floor "
            f"({base_confidence:.3f} < {ns.irreversible_confidence_floor:.3f})."
        ),
    )

    raw_risk = sum(float(item["weight"]) for item in risk_terms)
    risk = _clamp01(raw_risk)
    confidence = _clamp01(base_confidence - (0.35 * risk))

    needed_info: list[str] = []
    if needed_info_recall is not None and needed_info_recall < ns.needed_info_floor:
        needed_info.append("missing_dependency_specification")
    if latest_support_hit_rate is not None and latest_support_hit_rate < 1.0:
        needed_info.append("authoritative_source_ids")
    if parse_rate is not None and parse_rate < 1.0:
        needed_info.append("structured_decision_payload")
    if confidence_provided_rate is not None and confidence_provided_rate < 1.0:
        needed_info.append("confidence_score")
    if planning_score is not None and planning_score < ns.planning_floor:
        needed_info.append("multi_step_plan_constraints")
    needed_info = _unique_keep_order(needed_info)

    planning_hot = (
        (planning_score is not None and planning_score < ns.planning_floor)
        or (trap_entry_rate is not None and trap_entry_rate > 0.0)
        or (horizon_success_rate is not None and horizon_success_rate < 0.85)
    )
    authority_hot = (
        (authority_violation_rate is not None and authority_violation_rate > 0.0)
        or (latest_support_hit_rate is not None and latest_support_hit_rate < 1.0)
    )
    mode, decision = _controller_decision(
        force_mode=ns.mode,
        reversibility=ns.reversibility,
        confidence=confidence,
        risk=risk,
        needed_info=needed_info,
        authority_hot=authority_hot,
        planning_hot=planning_hot,
        confidence_floor=ns.confidence_floor,
        risk_floor=ns.risk_floor,
        irreversible_confidence_floor=ns.irreversible_confidence_floor,
        reliability_status=reliability_status,
    )

    horizon_depth = 4
    if first_error_step_mean is not None:
        horizon_depth = int(max(2, min(12, round(first_error_step_mean))))
    elif planning_score is not None:
        horizon_depth = 6 if planning_score < ns.planning_floor else 4

    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "decision": decision,
        "confidence": confidence,
        "risk": risk,
        "horizon_depth": horizon_depth,
        "needed_info": needed_info,
        "support_ids": [],
        "reversibility": ns.reversibility,
        "why": _reason_list(risk_terms),
        "signals": {
            "reliability_signal_status": reliability_status,
            "family_statuses": {
                "epistemic_calibration_suite": epistemic_status,
                "authority_under_interference_hardening": authority_status,
                "myopic_planning_traps": myopic_status,
                "referential_indexing_suite": referential_status,
                "novel_continuity_long_horizon": long_horizon_status,
            },
            "derived_scores": {
                "reasoning_score": reasoning_score,
                "planning_score": planning_score,
                "intelligence_index": intelligence_index,
            },
            "epistemic_means": epistemic_means,
            "authority_means": authority_means,
            "myopic_means": myopic_means,
            "referential_means": referential_means,
            "long_horizon_means": long_horizon_means,
        },
        "inputs": {
            "reliability_signal": str(ns.reliability_signal),
            "epistemic_reliability": str(ns.epistemic_reliability),
            "authority_reliability": str(ns.authority_reliability),
            "myopic_reliability": str(ns.myopic_reliability),
            "referential_reliability": str(ns.referential_reliability),
            "novel_long_horizon_reliability": str(ns.novel_long_horizon_reliability),
            "errors": {
                "reliability_signal": reliability_err,
                "epistemic": epistemic_err,
                "authority": authority_err,
                "myopic": myopic_err,
                "referential": referential_err,
                "novel_long_horizon": long_horizon_err,
            },
        },
        "thresholds": {
            "confidence_floor": ns.confidence_floor,
            "planning_floor": ns.planning_floor,
            "reasoning_floor": ns.reasoning_floor,
            "needed_info_floor": ns.needed_info_floor,
            "risk_floor": ns.risk_floor,
            "irreversible_confidence_floor": ns.irreversible_confidence_floor,
        },
    }

    ns.out.parent.mkdir(parents=True, exist_ok=True)
    ns.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(
        "RPA control snapshot: "
        f"mode={payload['mode']} decision={payload['decision']} "
        f"confidence={payload['confidence']:.3f} risk={payload['risk']:.3f}"
    )
    print(f"Wrote {ns.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
