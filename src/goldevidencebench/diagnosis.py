from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from goldevidencebench.baselines import parse_book_ledger
from goldevidencebench import schema_validation

Diagnosis = dict[str, Any]

SCHEMA_VERSION = "1"
HOLDOUT_NAMES = {"stale_tab_state", "focus_drift"}

DEFAULT_THRESHOLDS: dict[str, float] = {
    "unsafe_commit_rate": 0.05,
    "flip_rate": 0.1,
    "gold_present_rate": 0.9,
    "selection_rate_given_present": 0.9,
    "authority_violation_rate": 0.01,
    "answer_correct_given_selected": 0.9,
    "drift_step_rate_max": 0.25,
}


def load_thresholds(path: Path | None) -> dict[str, float]:
    if path is None:
        return DEFAULT_THRESHOLDS.copy()
    if not path.exists():
        return DEFAULT_THRESHOLDS.copy()
    data = json.loads(path.read_text(encoding="utf-8"))
    thresholds = DEFAULT_THRESHOLDS.copy()
    if isinstance(data, dict):
        for key, value in data.items():
            try:
                thresholds[key] = float(value)
            except (TypeError, ValueError):
                continue
    return thresholds


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _get_path(summary: dict[str, Any], path: str) -> Any:
    current: Any = summary
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _get_first_metric(summary: dict[str, Any], paths: list[str]) -> float | None:
    for path in paths:
        value = _as_float(_get_path(summary, path))
        if value is not None:
            return value
    return None


def _thresholds_version(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


def _norm_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text if text else None
    text = str(value).strip()
    return text if text else None


def infer_holdout_name(summary: dict[str, Any]) -> str | None:
    holdouts: set[str] = set()
    for entry in summary.get("by_group", []) or []:
        profile = entry.get("distractor_profile")
        if isinstance(profile, str) and profile in HOLDOUT_NAMES:
            holdouts.add(profile)
    if len(holdouts) == 1:
        return next(iter(holdouts))
    return None


def extract_metrics(summary: dict[str, Any]) -> dict[str, float | None]:
    metrics: dict[str, float | None] = {
        "unsafe_commit_rate": _get_first_metric(
            summary,
            [
                "retrieval.wrong_update_rate",
                "retrieval.selected_wrong_update_rate",
            ],
        ),
        "flip_rate": _get_first_metric(
            summary,
            [
                "overall.twin_flip_rate_mean",
                "overall_raw.twin_flip_rate_mean",
            ],
        ),
        "gold_present_rate": _get_first_metric(
            summary,
            [
                "retrieval.gold_present_rate",
                "retrieval.gold_in_context_rate",
            ],
        ),
        "selection_rate_given_present": _get_first_metric(
            summary,
            [
                "retrieval.selection_rate",
            ],
        ),
        "authority_violation_rate": _get_first_metric(
            summary,
            [
                "retrieval.selected_note_rate",
            ],
        ),
        "answer_correct_given_selected": _get_first_metric(
            summary,
            [
                "retrieval.answer_acc_given_gold_selected",
                "retrieval.value_acc_when_gold_selected",
            ],
        ),
        "drift_step_rate": _get_first_metric(
            summary,
            [
                "drift.step_rate",
            ],
        ),
    }
    return metrics


def _required_inputs(metrics: dict[str, float | None], *, is_drift_run: bool) -> list[str]:
    required_inputs: list[str] = []
    if metrics.get("unsafe_commit_rate") is None:
        required_inputs.append("emit unsafe_commit_rate (e.g., retrieval.wrong_update_rate).")
    if metrics.get("flip_rate") is None and not is_drift_run:
        required_inputs.append("run twin consistency to emit flip_rate.")
    if metrics.get("gold_present_rate") is None and not is_drift_run:
        required_inputs.append("enable retrieval stats to emit gold_present_rate.")
    if metrics.get("selection_rate_given_present") is None and not is_drift_run:
        required_inputs.append("enable retrieval stats to emit selection_rate_given_present.")
    if metrics.get("authority_violation_rate") is None:
        required_inputs.append("emit authority_violation_rate (e.g., selected_note_rate).")
    if metrics.get("answer_correct_given_selected") is None and not is_drift_run:
        required_inputs.append("emit answer_correct_given_selected (gold-selected accuracy).")
    if is_drift_run and metrics.get("drift_step_rate") is None:
        required_inputs.append("emit drift.step_rate (run drift holdout or drift wall).")
    return required_inputs


def _apply_drift_applicability(metrics: dict[str, float | None], *, is_drift_run: bool) -> None:
    if not is_drift_run:
        return
    for key in (
        "flip_rate",
        "gold_present_rate",
        "selection_rate_given_present",
        "answer_correct_given_selected",
    ):
        metrics[key] = None


def _triage_tuple(
    metrics: dict[str, float | None], thresholds: dict[str, float]
) -> dict[str, bool | None]:
    def _min_ok(value: float | None, threshold: float | None) -> bool | None:
        if value is None or threshold is None:
            return None
        return value >= threshold

    return {
        "retrieval_ok": _min_ok(
            metrics.get("gold_present_rate"), thresholds.get("gold_present_rate")
        ),
        "selection_ok": _min_ok(
            metrics.get("selection_rate_given_present"),
            thresholds.get("selection_rate_given_present"),
        ),
        "extraction_ok": _min_ok(
            metrics.get("answer_correct_given_selected"),
            thresholds.get("answer_correct_given_selected"),
        ),
    }


def classify_bottleneck(metrics: dict[str, float | None], thresholds: dict[str, float]) -> str:
    unsafe = metrics.get("unsafe_commit_rate")
    if unsafe is not None and unsafe > thresholds["unsafe_commit_rate"]:
        return "action_safety"
    flip = metrics.get("flip_rate")
    if flip is not None and flip > thresholds["flip_rate"]:
        return "instability"
    gold_present = metrics.get("gold_present_rate")
    if gold_present is not None and gold_present < thresholds["gold_present_rate"]:
        return "retrieval"
    selection = metrics.get("selection_rate_given_present")
    if selection is not None and selection < thresholds["selection_rate_given_present"]:
        return "selection"
    authority = metrics.get("authority_violation_rate")
    if authority is not None and authority > thresholds["authority_violation_rate"]:
        return "authority"
    answer = metrics.get("answer_correct_given_selected")
    if answer is not None and answer < thresholds["answer_correct_given_selected"]:
        return "answering"
    return "pass"


class LadderItem:
    def __init__(
        self,
        title: str,
        rationale: str,
        estimated_effort: str,
        expected_impact: str,
        applies: Callable[[dict[str, float | None]], bool],
    ) -> None:
        self.title = title
        self.rationale = rationale
        self.estimated_effort = estimated_effort
        self.expected_impact = expected_impact
        self.applies = applies

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "rationale": self.rationale,
            "estimated_effort": self.estimated_effort,
            "expected_impact": self.expected_impact,
            "next_steps": [],
        }


def _ladder_items() -> dict[str, list[LadderItem]]:
    return {
        "action_safety": [
            LadderItem(
                title="Tighten safety gate for unsafe commits",
                rationale="Unsafe commit rate exceeded threshold; block or abstain before risky actions.",
                estimated_effort="S",
                expected_impact="L",
                applies=lambda _m: True,
            ),
            LadderItem(
                title="Add abstain/escalation on unsafe signals",
                rationale="Route low-confidence actions to abstain or request confirmation.",
                estimated_effort="M",
                expected_impact="M",
                applies=lambda _m: True,
            ),
        ],
        "instability": [
            LadderItem(
                title="Stabilize consistency (twin flips)",
                rationale="High flip rate indicates unstable decisions across seeds.",
                estimated_effort="M",
                expected_impact="L",
                applies=lambda _m: True,
            ),
            LadderItem(
                title="Pin seeds / reduce nondeterminism",
                rationale="Make evaluations reproducible so regressions are explainable.",
                estimated_effort="S",
                expected_impact="M",
                applies=lambda _m: True,
            ),
        ],
        "retrieval": [
            LadderItem(
                title="Improve retrieval coverage (increase recall)",
                rationale="Gold present rate is below threshold; retrieval is dropping the right evidence.",
                estimated_effort="M",
                expected_impact="L",
                applies=lambda _m: True,
            ),
            LadderItem(
                title="Add retrieval diagnostics (gold-missing audit)",
                rationale="Surface which queries miss gold and why.",
                estimated_effort="S",
                expected_impact="M",
                applies=lambda _m: True,
            ),
        ],
        "selection": [
            LadderItem(
                title="Improve selection scoring (disambiguation)",
                rationale="Selection rate is below threshold with gold present.",
                estimated_effort="M",
                expected_impact="L",
                applies=lambda _m: True,
            ),
            LadderItem(
                title="Distill top decoy into a tiny gate",
                rationale="Turn the dominant failure pattern into a cheap reflex.",
                estimated_effort="M",
                expected_impact="M",
                applies=lambda _m: True,
            ),
        ],
        "authority": [
            LadderItem(
                title="Strengthen authority filter (NOTE/INFO rejection)",
                rationale="Authority violations remain; hard gate must dominate.",
                estimated_effort="S",
                expected_impact="L",
                applies=lambda _m: True,
            ),
            LadderItem(
                title="Add authority-focused fixtures",
                rationale="Pinpoint spoof and NOTE confusion to prevent regressions.",
                estimated_effort="S",
                expected_impact="M",
                applies=lambda _m: True,
            ),
        ],
        "answering": [
            LadderItem(
                title="Improve answer extraction / formatting",
                rationale="Answer correctness lags despite correct selection.",
                estimated_effort="M",
                expected_impact="M",
                applies=lambda _m: True,
            ),
            LadderItem(
                title="Add answer verification / post-check",
                rationale="Use deterministic checks to catch malformed answers.",
                estimated_effort="S",
                expected_impact="M",
                applies=lambda _m: True,
            ),
        ],
        "pass": [
            LadderItem(
                title="No bottleneck detected; expand coverage",
                rationale="All thresholds passed; add harder regimes to find the next gap.",
                estimated_effort="S",
                expected_impact="M",
                applies=lambda _m: True,
            ),
            LadderItem(
                title="Rotate holdouts or add new trap family",
                rationale="Keep an oracle gap alive for distillation.",
                estimated_effort="M",
                expected_impact="M",
                applies=lambda _m: True,
            ),
        ],
    }


def _select_prescriptions(primary: str, metrics: dict[str, float | None]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    ladder = _ladder_items().get(primary, [])
    applicable = [item for item in ladder if item.applies(metrics)]
    if not applicable:
        return None, None
    first = applicable[0].to_dict()
    second = applicable[1].to_dict() if len(applicable) > 1 else None
    return first, second


def _normalize_examples(examples: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not examples:
        return []
    normalized: list[dict[str, Any]] = []
    for example in examples:
        if not isinstance(example, dict):
            continue
        entry = dict(example)
        if "why_type" not in entry:
            entry["why_type"] = None
        normalized.append(entry)
    return normalized


def build_drift_examples(
    *,
    data_rows: list[dict[str, Any]],
    pred_by_id: dict[str, dict[str, Any]],
    retrieval_by_id: dict[str, dict[str, Any]],
    holdout_name: str,
    max_examples: int = 3,
) -> list[dict[str, Any]]:
    if holdout_name not in HOLDOUT_NAMES:
        return []
    if not data_rows:
        return []
    book = data_rows[0].get("book")
    uid_to_entry = {e.get("uid"): e for e in parse_book_ledger(book or "")}
    examples: list[dict[str, Any]] = []
    for row in data_rows:
        if len(examples) >= max_examples:
            break
        rid = row.get("id")
        if not rid:
            continue
        diag = retrieval_by_id.get(rid)
        if not diag or diag.get("gold_missing") is True:
            continue
        if diag.get("correct_included") is not True or diag.get("dropped_correct") is True:
            continue
        gold_value = _norm_text(row.get("gold", {}).get("value"))
        pred = pred_by_id.get(rid, {})
        pred_value = _norm_text(pred.get("value"))
        if gold_value is None or pred_value is None:
            continue
        if gold_value == pred_value:
            continue
        selected_uid = diag.get("selected_uid")
        selected_entry = uid_to_entry.get(selected_uid)
        reason = "drifted commit"
        if holdout_name == "focus_drift":
            reason = "focus drift to sibling field"
        elif selected_entry and str(selected_entry.get("op", "")).upper() == "NOTE":
            reason = "non-authoritative NOTE selected"
        examples.append(
            {
                "query_id": rid,
                "step_index": row.get("meta", {}).get("q_index"),
                "why_type": "commit_state",
                "committed": pred_value,
                "expected": gold_value,
                "reason": reason,
            }
        )
    return examples


def _holdout_prescriptions(holdout_name: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    def _entry(title: str, rationale: str, effort: str, impact: str) -> dict[str, Any]:
        return {
            "title": title,
            "rationale": rationale,
            "estimated_effort": effort,
            "expected_impact": impact,
            "next_steps": [],
        }

    if holdout_name == "stale_tab_state":
        return (
            _entry(
                "Enable authority filter (RETRIEVAL_AUTHORITY_FILTER=1)",
                "Holdout drift indicates NOTE lines are winning selection; filter NOTES before commit.",
                "S",
                "L",
            ),
            _entry(
                "Use prefer_set_latest with authority filter on holdouts",
                "Prefer_set_latest is evaluated with the authority filter enabled; keep NOTE lines filtered so recency favors authoritative SET updates.",
                "S",
                "M",
            ),
        )
    if holdout_name == "focus_drift":
        return (
            _entry(
                "Add target-identity/focus guard before commit",
                "Focus drift indicates the wrong target field is being updated despite correct evidence.",
                "M",
                "M",
            ),
            _entry(
                "Use prefer_set_latest with authority filter on holdouts",
                "Prefer_set_latest is evaluated with the authority filter enabled; filter NOTE lines so recency reduces sibling-value confusion.",
                "S",
                "M",
            ),
        )
    return (
        _entry(
            "Investigate drift root cause",
            "Drift exceeded the threshold; inspect commit traces to find the persistent error.",
            "M",
            "M",
        ),
        None,
    )


def build_diagnosis(
    *,
    summary: dict[str, Any],
    evidence_examples: list[dict[str, Any]] | None = None,
    thresholds: dict[str, float] | None = None,
    thresholds_path: Path | None = None,
    run_dir: Path | str | None = None,
    holdout_name: str | None = None,
    failure_case_id: str | None = None,
) -> Diagnosis:
    thresholds = thresholds or DEFAULT_THRESHOLDS.copy()
    metrics = extract_metrics(summary)
    if holdout_name is None:
        holdout_name = infer_holdout_name(summary)
    is_drift_run = bool(summary.get("drift")) or (holdout_name in HOLDOUT_NAMES)
    _apply_drift_applicability(metrics, is_drift_run=is_drift_run)
    required_inputs = _required_inputs(metrics, is_drift_run=is_drift_run)
    triage = _triage_tuple(metrics, thresholds)
    bottleneck = classify_bottleneck(metrics, thresholds)
    status = "FAIL"
    primary = bottleneck if bottleneck != "pass" else "answering"
    primary_for_ladder = primary if bottleneck != "pass" else "pass"
    drift_rate = metrics.get("drift_step_rate")
    drift_max = thresholds.get("drift_step_rate_max")
    if is_drift_run and drift_rate is not None and drift_max is not None:
        if drift_rate <= drift_max:
            if bottleneck in {"action_safety", "authority"}:
                status = "FAIL"
                primary = bottleneck
                primary_for_ladder = primary
            else:
                status = "PASS"
                primary = "answering"
                primary_for_ladder = "pass"
        else:
            if bottleneck == "action_safety":
                status = "FAIL"
                primary = "action_safety"
                primary_for_ladder = primary
            else:
                status = "FAIL"
                if holdout_name == "stale_tab_state":
                    primary = "authority"
                elif holdout_name == "focus_drift":
                    primary = "selection"
                elif bottleneck != "pass":
                    primary = bottleneck
                else:
                    primary = "selection"
                primary_for_ladder = primary
    else:
        if bottleneck == "action_safety":
            status = "FAIL"
            primary = "action_safety"
            primary_for_ladder = primary
        elif bottleneck == "instability":
            status = "UNSTABLE"
            primary = "instability"
            primary_for_ladder = primary
        elif bottleneck == "pass":
            status = "PASS"
            primary = "answering"
            primary_for_ladder = "pass"
        else:
            status = "FAIL"
            primary = bottleneck
            primary_for_ladder = primary

    if is_drift_run and drift_rate is not None and drift_max is not None and drift_rate > drift_max and bottleneck != "action_safety":
        prescription, second_best = _holdout_prescriptions(holdout_name or "")
    else:
        prescription, second_best = _select_prescriptions(primary_for_ladder, metrics)
    thresholds_version = _thresholds_version(thresholds_path)
    run_dir_value = str(run_dir) if run_dir is not None else None
    return {
        "schema_version": SCHEMA_VERSION,
        "run_dir": run_dir_value,
        "thresholds_version": thresholds_version,
        "holdout_name": holdout_name,
        "failure_case_id": failure_case_id,
        "status": status,
        "primary_bottleneck": primary,
        "triage": triage,
        "supporting_metrics": metrics,
        "evidence_examples": _normalize_examples(evidence_examples),
        "prescription": prescription,
        "second_best_prescription": second_best,
        "required_inputs_next_run": required_inputs,
    }


def write_diagnosis(path: Path, diagnosis: Diagnosis) -> None:
    schema_path = schema_validation.schema_path("diagnosis.schema.json")
    schema_validation.validate_or_raise(diagnosis, schema_path)
    path.write_text(json.dumps(diagnosis, indent=2), encoding="utf-8")


def format_diagnosis_summary(diagnosis: Diagnosis) -> list[str]:
    status = diagnosis.get("status", "UNKNOWN")
    bottleneck = diagnosis.get("primary_bottleneck", "unknown")
    lines = [f"Actionable Diagnosis: {status} - primary bottleneck = {bottleneck}"]
    prescription = diagnosis.get("prescription") or {}
    if prescription:
        lines.append(
            f"Top fix: {prescription.get('title')} (Effort: {prescription.get('estimated_effort')}, Impact: {prescription.get('expected_impact')})"
        )
    second = diagnosis.get("second_best_prescription") or {}
    if second:
        lines.append(
            f"Next: {second.get('title')} (Effort: {second.get('estimated_effort')}, Impact: {second.get('expected_impact')})"
        )
    return lines
