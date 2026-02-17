from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from goldevidencebench.rpa_reason_codes import ReasonCode

Mode = Literal["reason", "plan", "act"]
Decision = Literal["answer", "abstain", "ask", "retrieve", "verify", "defer"]


@dataclass(frozen=True)
class PolicyReason:
    code: str
    severity: Literal["info", "warn", "error"]
    source: Literal["controller", "planner", "router", "scorer", "release_gate"]
    metric: str | None
    value: float | None
    threshold: float | None
    message: str


@dataclass(frozen=True)
class PolicyDecision:
    mode: Mode
    decision: Decision
    blocked: bool
    reasons: list[PolicyReason]
    required_actions: list[str]


@dataclass(frozen=True)
class RuntimePolicyThresholds:
    reason_confidence_floor: float = 0.60
    plan_score_floor: float = 0.70
    ic_floor_reason: float = 0.75
    implication_break_ceiling_reason: float = 0.10
    irreversible_confidence_floor: float = 0.85
    irreversible_risk_ceiling: float = 0.20
    irreversible_ic_floor: float = 0.80
    contradiction_repair_floor: float = 0.85
    intent_preservation_floor: float = 0.90


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return False


def _unique_ordered(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _normalize_needed_info(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str):
            text = item.strip()
            if text:
                out.append(text)
            continue
        if isinstance(item, dict):
            item_id = item.get("id")
            if isinstance(item_id, str) and item_id.strip():
                out.append(item_id.strip())
    return _unique_ordered(out)


def _reason(
    *,
    code: ReasonCode,
    severity: Literal["info", "warn", "error"],
    metric: str | None,
    value: float | None,
    threshold: float | None,
    message: str,
    source: Literal["controller", "planner", "router", "scorer", "release_gate"] = "controller",
) -> PolicyReason:
    return PolicyReason(
        code=code.value,
        severity=severity,
        source=source,
        metric=metric,
        value=value,
        threshold=threshold,
        message=message,
    )


def _get_thresholds(context: dict[str, Any]) -> RuntimePolicyThresholds:
    raw = context.get("thresholds")
    if not isinstance(raw, dict):
        return RuntimePolicyThresholds()
    base = RuntimePolicyThresholds()
    return RuntimePolicyThresholds(
        reason_confidence_floor=_as_float(raw.get("reason_confidence_floor"))
        or base.reason_confidence_floor,
        plan_score_floor=_as_float(raw.get("plan_score_floor")) or base.plan_score_floor,
        ic_floor_reason=_as_float(raw.get("ic_floor_reason")) or base.ic_floor_reason,
        implication_break_ceiling_reason=_as_float(raw.get("implication_break_ceiling_reason"))
        or base.implication_break_ceiling_reason,
        irreversible_confidence_floor=_as_float(raw.get("irreversible_confidence_floor"))
        or base.irreversible_confidence_floor,
        irreversible_risk_ceiling=_as_float(raw.get("irreversible_risk_ceiling"))
        or base.irreversible_risk_ceiling,
        irreversible_ic_floor=_as_float(raw.get("irreversible_ic_floor"))
        or base.irreversible_ic_floor,
        contradiction_repair_floor=_as_float(raw.get("contradiction_repair_floor"))
        or base.contradiction_repair_floor,
        intent_preservation_floor=_as_float(raw.get("intent_preservation_floor"))
        or base.intent_preservation_floor,
    )


def _append_reasons_for_mode_inputs(
    *,
    reasons: list[PolicyReason],
    confidence: float | None,
    needed_info: list[str],
    authority_conflict_high: bool,
    planning_score: float | None,
    contradiction_repair_pending: bool,
    thresholds: RuntimePolicyThresholds,
) -> None:
    if confidence is not None and confidence < thresholds.reason_confidence_floor:
        reasons.append(
            _reason(
                code=ReasonCode.LOW_CONFIDENCE,
                severity="warn",
                metric="confidence",
                value=confidence,
                threshold=thresholds.reason_confidence_floor,
                message="Confidence below reason-mode floor.",
            )
        )
    if needed_info:
        reasons.append(
            _reason(
                code=ReasonCode.MISSING_NEEDED_INFO,
                severity="warn",
                metric="needed_info",
                value=float(len(needed_info)),
                threshold=0.0,
                message="Required dependencies are missing.",
            )
        )
    if authority_conflict_high:
        reasons.append(
            _reason(
                code=ReasonCode.AUTHORITY_CONFLICT,
                severity="warn",
                metric="authority_conflict_high",
                value=1.0,
                threshold=0.0,
                message="Authority conflict risk is high.",
            )
        )
    if planning_score is not None and planning_score < thresholds.plan_score_floor:
        reasons.append(
            _reason(
                code=ReasonCode.PLANNING_SIGNAL_WEAK,
                severity="warn",
                metric="planning_score",
                value=planning_score,
                threshold=thresholds.plan_score_floor,
                message="Planning signal is below plan floor.",
            )
        )
    if contradiction_repair_pending:
        reasons.append(
            _reason(
                code=ReasonCode.CONTRADICTION_REPAIR_PENDING,
                severity="warn",
                metric="contradiction_repair_pending",
                value=1.0,
                threshold=0.0,
                message="Contradiction repair is pending.",
            )
        )


def _decide_mode(
    *,
    force_mode: str,
    confidence: float | None,
    needed_info: list[str],
    authority_conflict_high: bool,
    ic_score: float | None,
    implication_break_rate: float | None,
    planning_score: float | None,
    horizon_depth: int | None,
    weak_continuity_planning_support: bool,
    contradiction_repair_pending: bool,
    thresholds: RuntimePolicyThresholds,
) -> Mode:
    if force_mode in {"reason", "plan", "act"}:
        return force_mode  # type: ignore[return-value]

    reason_mode = False
    if confidence is not None and confidence < thresholds.reason_confidence_floor:
        reason_mode = True
    if needed_info:
        reason_mode = True
    if authority_conflict_high:
        reason_mode = True
    if ic_score is not None and ic_score < thresholds.ic_floor_reason:
        reason_mode = True
    if (
        implication_break_rate is not None
        and implication_break_rate > thresholds.implication_break_ceiling_reason
    ):
        reason_mode = True

    if reason_mode:
        return "reason"

    plan_mode = False
    if planning_score is not None and planning_score < thresholds.plan_score_floor:
        plan_mode = True
    if (horizon_depth or 0) >= 2 and weak_continuity_planning_support:
        plan_mode = True
    if contradiction_repair_pending:
        plan_mode = True

    if plan_mode:
        return "plan"
    return "act"


def evaluate_runtime_policy(snapshot: dict[str, Any], context: dict[str, Any]) -> PolicyDecision:
    thresholds = _get_thresholds(context)

    reversibility = str(
        context.get("reversibility") or snapshot.get("reversibility") or "reversible"
    ).strip().lower()
    force_mode = str(context.get("force_mode") or "auto").strip().lower()
    confidence = _as_float(snapshot.get("confidence"))
    risk = _as_float(snapshot.get("risk"))
    needed_info = _normalize_needed_info(context.get("needed_info") or snapshot.get("needed_info"))
    planning_score = _as_float(context.get("planning_score"))
    horizon_depth = int(_as_float(context.get("horizon_depth") or snapshot.get("horizon_depth")) or 0)

    authority_conflict_high = _as_bool(context.get("authority_conflict_high"))
    weak_continuity_planning_support = _as_bool(context.get("weak_continuity_planning_support"))
    contradiction_repair_pending = _as_bool(context.get("contradiction_repair_pending"))

    ic_score = _as_float(context.get("ic_score"))
    implication_break_rate = _as_float(context.get("implication_break_rate"))
    contradiction_repair_rate = _as_float(context.get("contradiction_repair_rate"))
    intent_preservation_score = _as_float(context.get("intent_preservation_score"))

    substitution = context.get("substitution")
    if not isinstance(substitution, dict):
        substitution = {}
    requested_option = substitution.get("requested_option")
    proposed_option = substitution.get("proposed_option")
    disclosed = _as_bool(substitution.get("disclosed"))
    authorized = _as_bool(substitution.get("authorized"))
    recoverable = _as_bool(substitution.get("recoverable"))
    policy_required = _as_bool(
        substitution.get("policy_required") or context.get("policy_required_substitution")
    )

    mode = _decide_mode(
        force_mode=force_mode,
        confidence=confidence,
        needed_info=needed_info,
        authority_conflict_high=authority_conflict_high,
        ic_score=ic_score,
        implication_break_rate=implication_break_rate,
        planning_score=planning_score,
        horizon_depth=horizon_depth,
        weak_continuity_planning_support=weak_continuity_planning_support,
        contradiction_repair_pending=contradiction_repair_pending,
        thresholds=thresholds,
    )

    reasons: list[PolicyReason] = []
    _append_reasons_for_mode_inputs(
        reasons=reasons,
        confidence=confidence,
        needed_info=needed_info,
        authority_conflict_high=authority_conflict_high,
        planning_score=planning_score,
        contradiction_repair_pending=contradiction_repair_pending,
        thresholds=thresholds,
    )
    required_actions: list[str] = []
    blocked = False

    # Default mode-specific action.
    if mode == "reason":
        if authority_conflict_high:
            decision: Decision = "retrieve"
        elif needed_info:
            decision = "ask"
        elif confidence is not None and confidence < thresholds.reason_confidence_floor:
            decision = "abstain"
        else:
            decision = "retrieve"
    elif mode == "plan":
        decision = "verify" if reversibility == "irreversible" else "retrieve"
    else:
        decision = "answer"

    # Hard block: unauthorized substitution.
    substitution_changed = (
        isinstance(requested_option, str)
        and isinstance(proposed_option, str)
        and requested_option != proposed_option
    )
    if substitution_changed and not (
        disclosed and (authorized or policy_required) and recoverable
    ):
        blocked = True
        reasons.append(
            _reason(
                code=ReasonCode.UNAUTHORIZED_SUBSTITUTION,
                severity="error",
                metric="substitution",
                value=1.0,
                threshold=0.0,
                message=(
                    "Substitution differs from requested option without "
                    "disclosure+authorization/policy+recoverability."
                ),
            )
        )
        if policy_required and not authorized:
            reasons.append(
                _reason(
                    code=ReasonCode.POLICY_REQUIRED_SUBSTITUTION,
                    severity="warn",
                    metric="policy_required_substitution",
                    value=1.0,
                    threshold=0.0,
                    message="Policy-required substitution path requires user-visible confirmation.",
                )
            )
        reasons.append(
            _reason(
                code=ReasonCode.BLOCKED_BY_RUNTIME_POLICY,
                severity="error",
                metric="runtime_policy_block",
                value=1.0,
                threshold=0.0,
                message="Runtime policy blocked execution.",
            )
        )
        required_actions.extend(["disclose_substitution", "request_authorization"])
        mode = "reason"
        decision = "defer" if reversibility == "irreversible" else "ask"

    # Hard block: implication coherence.
    ic_failed = False
    if ic_score is not None and ic_score < thresholds.ic_floor_reason:
        ic_failed = True
        reasons.append(
            _reason(
                code=ReasonCode.LOW_IC,
                severity="error",
                metric="ic_score",
                value=ic_score,
                threshold=thresholds.ic_floor_reason,
                message="Implication coherence score below floor.",
            )
        )
    if (
        implication_break_rate is not None
        and implication_break_rate > thresholds.implication_break_ceiling_reason
    ):
        ic_failed = True
        reasons.append(
            _reason(
                code=ReasonCode.HIGH_IMPLICATION_BREAK,
                severity="error",
                metric="implication_break_rate",
                value=implication_break_rate,
                threshold=thresholds.implication_break_ceiling_reason,
                message="Implication break rate above ceiling.",
            )
        )
    if ic_failed:
        blocked = True
        reasons.append(
            _reason(
                code=ReasonCode.BLOCKED_BY_RUNTIME_POLICY,
                severity="error",
                metric="runtime_policy_block",
                value=1.0,
                threshold=0.0,
                message="Runtime policy blocked execution.",
            )
        )
        required_actions.append("verify_implications")
        if reversibility == "irreversible":
            mode = "reason"
            decision = "defer"
        else:
            mode = "reason"
            decision = "retrieve"

    # Hard block: irreversible guard.
    if reversibility == "irreversible":
        irreversible_failed = False
        if confidence is not None and confidence < thresholds.irreversible_confidence_floor:
            irreversible_failed = True
            reasons.append(
                _reason(
                    code=ReasonCode.LOW_CONFIDENCE,
                    severity="error",
                    metric="confidence",
                    value=confidence,
                    threshold=thresholds.irreversible_confidence_floor,
                    message="Irreversible path requires higher confidence.",
                )
            )
        if risk is not None and risk > thresholds.irreversible_risk_ceiling:
            irreversible_failed = True
            reasons.append(
                _reason(
                    code=ReasonCode.HIGH_RISK,
                    severity="error",
                    metric="risk",
                    value=risk,
                    threshold=thresholds.irreversible_risk_ceiling,
                    message="Irreversible path risk exceeds ceiling.",
                )
            )
        if ic_score is not None and ic_score < thresholds.irreversible_ic_floor:
            irreversible_failed = True
            reasons.append(
                _reason(
                    code=ReasonCode.LOW_IC,
                    severity="error",
                    metric="ic_score",
                    value=ic_score,
                    threshold=thresholds.irreversible_ic_floor,
                    message="Irreversible path requires stronger implication coherence.",
                )
            )
        if (
            contradiction_repair_rate is not None
            and contradiction_repair_rate < thresholds.contradiction_repair_floor
        ):
            irreversible_failed = True
            reasons.append(
                _reason(
                    code=ReasonCode.CONTRADICTION_REPAIR_PENDING,
                    severity="error",
                    metric="contradiction_repair_rate",
                    value=contradiction_repair_rate,
                    threshold=thresholds.contradiction_repair_floor,
                    message="Contradiction repair rate below irreversible floor.",
                )
            )
        if (
            intent_preservation_score is not None
            and intent_preservation_score < thresholds.intent_preservation_floor
        ):
            irreversible_failed = True
            reasons.append(
                _reason(
                    code=ReasonCode.IRREVERSIBLE_UNVERIFIED,
                    severity="error",
                    metric="intent_preservation_score",
                    value=intent_preservation_score,
                    threshold=thresholds.intent_preservation_floor,
                    message="Intent preservation below irreversible floor.",
                )
            )
        if irreversible_failed:
            blocked = True
            reasons.append(
                _reason(
                    code=ReasonCode.BLOCKED_BY_RUNTIME_POLICY,
                    severity="error",
                    metric="runtime_policy_block",
                    value=1.0,
                    threshold=0.0,
                    message="Runtime policy blocked execution.",
                )
            )
            required_actions.append("verify_before_irreversible")
            mode = "plan"
            decision = "verify"

    if needed_info and "resolve_needed_info" not in required_actions:
        required_actions.append("resolve_needed_info")

    return PolicyDecision(
        mode=mode,
        decision=decision,
        blocked=blocked,
        reasons=reasons,
        required_actions=_unique_ordered(required_actions),
    )
