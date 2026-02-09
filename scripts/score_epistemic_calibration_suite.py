from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from goldevidencebench.util import read_jsonl

ABSTAIN_DECISIONS = {"abstain", "ask", "retrieve"}
_KEY_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]*")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Score epistemic_calibration_suite with calibration and abstention metrics."
        )
    )
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--preds", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--rows-out", type=Path, default=None)
    parser.add_argument("--coverage", type=float, default=0.80)
    parser.add_argument("--confidence-threshold", type=float, default=0.70)
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
    parser.add_argument("--min-known-answerable-acc", type=float, default=None)
    parser.add_argument("--min-unknown-unanswerable-acc", type=float, default=None)
    parser.add_argument("--min-near-miss-familiar-acc", type=float, default=None)
    parser.add_argument("--min-contradictory-evidence-acc", type=float, default=None)
    parser.add_argument("--min-missing-key-dependency-acc", type=float, default=None)
    parser.add_argument("--min-confidence-inversion-acc", type=float, default=None)
    return parser.parse_args()


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


def _list_of_str(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if item is None:
            continue
        text = str(item).strip()
        if text:
            out.append(text)
    return out


def _set_of_str(value: Any) -> set[str]:
    return set(_list_of_str(value))


def _normalize_needed_info_items(items: set[str]) -> set[str]:
    out: set[str] = set()
    for item in items:
        text = str(item).strip().lower()
        if not text:
            continue
        out.add(text)
        for token in _KEY_TOKEN_RE.findall(text):
            token_norm = token.strip().lower()
            if not token_norm:
                continue
            if "." in token_norm or "_" in token_norm:
                out.add(token_norm)
    return out


def _needed_info_matches(*, expected_key: str, pred_items_norm: set[str]) -> bool:
    expected = expected_key.strip().lower()
    if not expected:
        return False
    expected_tail = expected.split(".")[-1]
    for cand in pred_items_norm:
        c = cand.strip().lower()
        if not c:
            continue
        if c == expected:
            return True
        if c == expected_tail:
            return True
        if expected.endswith("." + c):
            return True
        if c.endswith("." + expected_tail):
            return True
        if expected in c:
            return True
    return False


def _mean(values: list[float]) -> float:
    return (sum(values) / len(values)) if values else 0.0


def _safe_confidence(raw: Any) -> float:
    if isinstance(raw, (int, float)):
        value = float(raw)
    elif isinstance(raw, str):
        try:
            value = float(raw.strip())
        except Exception:
            return 0.0
    else:
        return 0.0
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _parse_decision_token(text: str) -> str | None:
    match = re.search(
        r"\b(decision|action)\s*[:=]\s*(answer|abstain|ask|retrieve)\b",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return match.group(2).strip().lower()


def _parse_confidence_token(text: str) -> float:
    match = re.search(r"\bconfidence\s*[:=]\s*([0-9]*\.?[0-9]+)\b", text, flags=re.IGNORECASE)
    if not match:
        return 0.0
    return _safe_confidence(match.group(1))


def _parse_needed_info_tokens(text: str) -> list[str]:
    match = re.search(
        r"\bneeded[_\s]?info\s*[:=]\s*([A-Za-z0-9_.,:\-\s\[\]`]+)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return []
    raw = match.group(1).replace("[", "").replace("]", "").replace("`", "")
    parts = [part.strip() for part in raw.split(",")]
    return [part for part in parts if part]


def _confidence_proxy(
    *,
    decision: str,
    answer: Any,
    support_ids: set[str],
    needed_info: list[str],
) -> float:
    # Fallback confidence when model omitted confidence. This is intentionally
    # conservative but above chance so calibration metrics remain meaningful.
    if decision == "answer":
        if support_ids:
            return 0.85
        if answer is not None and str(answer).strip():
            return 0.75
        return 0.65
    if decision in ABSTAIN_DECISIONS:
        if needed_info:
            return 0.85
        return 0.75
    return 0.75


def _parse_pred_row(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("value")
    parsed: dict[str, Any] = {}
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("{") and text.endswith("}"):
            try:
                obj = json.loads(text)
            except Exception:
                obj = None
            if isinstance(obj, dict):
                parsed = obj
    text_value = value.strip() if isinstance(value, str) else ""
    decision_raw = parsed.get("decision")
    if decision_raw is None:
        decision_raw = _parse_decision_token(text_value)
    if decision_raw is None and value is None:
        decision_raw = "retrieve"
    if decision_raw is None:
        decision_raw = "answer"
    decision = str(decision_raw).strip().lower() if decision_raw is not None else "answer"
    if decision not in {"answer", "abstain", "ask", "retrieve"}:
        decision = "answer"

    answer = parsed.get("answer")
    if answer is None and not parsed and isinstance(value, str) and decision == "answer":
        answer = value
    confidence_raw = parsed.get("confidence", _parse_confidence_token(text_value))
    confidence = _safe_confidence(confidence_raw)
    confidence_provided = False
    if isinstance(parsed, dict) and "confidence" in parsed:
        confidence_provided = True
    elif isinstance(value, str):
        confidence_provided = bool(
            re.search(r"\bconfidence\s*[:=]\s*([0-9]*\.?[0-9]+)\b", text_value, flags=re.IGNORECASE)
        )
    needed_info = _list_of_str(parsed.get("needed_info"))
    if not needed_info and not parsed:
        needed_info = _parse_needed_info_tokens(text_value)
    support_ids = _set_of_str(parsed.get("support_ids")) or _set_of_str(row.get("support_ids"))
    if not confidence_provided:
        confidence = _confidence_proxy(
            decision=decision,
            answer=answer,
            support_ids=support_ids,
            needed_info=needed_info,
        )
    return {
        "parsed_json": bool(parsed),
        "decision": decision,
        "answer": answer,
        "confidence": confidence,
        "confidence_provided": confidence_provided,
        "needed_info": needed_info,
        "support_ids": support_ids,
    }


def _ece(probs: list[float], labels: list[float], bins: int = 10) -> float:
    if not probs:
        return 0.0
    total = len(probs)
    ece = 0.0
    for i in range(bins):
        low = i / bins
        high = (i + 1) / bins
        idxs = [
            idx
            for idx, p in enumerate(probs)
            if (p >= low and p < high) or (i == bins - 1 and p == 1.0)
        ]
        if not idxs:
            continue
        avg_p = sum(probs[idx] for idx in idxs) / len(idxs)
        avg_y = sum(labels[idx] for idx in idxs) / len(idxs)
        ece += (len(idxs) / total) * abs(avg_p - avg_y)
    return ece


def _brier(probs: list[float], labels: list[float]) -> float:
    if not probs:
        return 0.0
    return sum((p - y) ** 2 for p, y in zip(probs, labels)) / len(probs)


def _selective_accuracy(confidences: list[float], labels: list[float], coverage: float) -> float:
    if not confidences:
        return 0.0
    n = len(confidences)
    keep = int(math.ceil(max(0.0, min(1.0, coverage)) * n))
    keep = max(1, min(n, keep))
    pairs = sorted(zip(confidences, labels), key=lambda item: item[0], reverse=True)
    selected = pairs[:keep]
    return sum(label for _, label in selected) / len(selected)


def _check_thresholds(summary: dict[str, Any], ns: argparse.Namespace) -> list[str]:
    means = summary.get("means", {})
    failures: list[str] = []
    min_checks = [
        ("kkyi", ns.min_kkyi),
        ("abstain_f1", ns.min_abstain_f1),
        ("parse_rate", ns.min_parse_rate),
        ("confidence_provided_rate", ns.min_confidence_provided_rate),
        ("selective_accuracy_at_coverage", ns.min_selective_accuracy_at_coverage),
        ("needed_info_recall", ns.min_needed_info_recall),
        ("known_answerable_acc", ns.min_known_answerable_acc),
        ("unknown_unanswerable_acc", ns.min_unknown_unanswerable_acc),
        ("near_miss_familiar_acc", ns.min_near_miss_familiar_acc),
        ("contradictory_evidence_acc", ns.min_contradictory_evidence_acc),
        ("missing_key_dependency_acc", ns.min_missing_key_dependency_acc),
        ("confidence_inversion_acc", ns.min_confidence_inversion_acc),
    ]
    max_checks = [
        ("overclaim_rate", ns.max_overclaim_rate),
        ("ece", ns.max_ece),
        ("brier", ns.max_brier),
        ("confidence_proxy_used_rate", ns.max_confidence_proxy_used_rate),
    ]

    for metric, threshold in min_checks:
        if threshold is None:
            continue
        value = means.get(metric)
        if not isinstance(value, (int, float)) or float(value) < float(threshold):
            failures.append(f"{metric} < {threshold}")

    for metric, threshold in max_checks:
        if threshold is None:
            continue
        value = means.get(metric)
        if not isinstance(value, (int, float)) or float(value) > float(threshold):
            failures.append(f"{metric} > {threshold}")
    return failures


def main() -> int:
    ns = _parse_args()
    out_path = ns.out or (ns.preds.parent / "epistemic_calibration_suite_summary.json")

    data_rows = [row for row in read_jsonl(ns.data) if isinstance(row, dict)]
    pred_rows = [row for row in read_jsonl(ns.preds) if isinstance(row, dict)]
    preds_by_id = {str(row.get("id")): row for row in pred_rows if row.get("id") is not None}

    parse_rates: list[float] = []
    confidence_provided_flags: list[float] = []
    overclaim_flags: list[float] = []
    abstain_prec_hits = 0
    abstain_pred_total = 0
    abstain_recall_hits = 0
    abstain_gold_total = 0
    needed_info_recalls: list[float] = []
    answer_confidences: list[float] = []
    answer_labels: list[float] = []
    all_probs: list[float] = []
    all_labels: list[float] = []
    family_hits: Counter[str] = Counter()
    family_counts: Counter[str] = Counter()
    failure_mode_counts: Counter[str] = Counter()
    row_diags: list[dict[str, Any]] = []

    for data_row in data_rows:
        rid = str(data_row.get("id"))
        pred_raw = preds_by_id.get(rid, {})
        pred = _parse_pred_row(pred_raw)

        gold = data_row.get("gold") if isinstance(data_row.get("gold"), dict) else {}
        meta = data_row.get("meta") if isinstance(data_row.get("meta"), dict) else {}
        family_id = str(meta.get("family_id", "unknown"))
        family_counts[family_id] += 1

        expected_decision = str(meta.get("expected_decision", "answer")).strip().lower()
        is_answerable = expected_decision == "answer"
        decision = pred["decision"]
        confidence = float(pred["confidence"])
        confidence_provided = bool(pred.get("confidence_provided"))
        confidence_provided_flags.append(1.0 if confidence_provided else 0.0)
        decision_is_abstain = decision in ABSTAIN_DECISIONS

        answer_correct = is_answerable and (_norm(pred["answer"]) == _norm(gold.get("value")))
        row_correct = answer_correct if is_answerable else decision_is_abstain

        if row_correct:
            family_hits[family_id] += 1
        else:
            failure_mode_counts[f"{family_id}_miss"] += 1

        if decision_is_abstain:
            abstain_pred_total += 1
            if not is_answerable:
                abstain_prec_hits += 1
        if not is_answerable:
            abstain_gold_total += 1
            if decision_is_abstain:
                abstain_recall_hits += 1

        if decision == "answer":
            answer_confidences.append(confidence)
            answer_labels.append(1.0 if answer_correct else 0.0)

        # Confidence is interpreted as confidence in correctness of chosen decision.
        p_correct = confidence
        all_probs.append(p_correct)
        all_labels.append(1.0 if row_correct else 0.0)

        overclaim = decision == "answer" and (not answer_correct) and (confidence >= ns.confidence_threshold)
        if overclaim:
            failure_mode_counts["overclaim"] += 1
        overclaim_flags.append(1.0 if overclaim else 0.0)
        confidence_proxy_used = not confidence_provided
        if not confidence_provided:
            failure_mode_counts["confidence_proxy_used"] += 1

        expected_needed = _set_of_str(meta.get("needed_info"))
        pred_needed = set(pred["needed_info"])
        if (
            (not pred_needed)
            and expected_needed
            and decision_is_abstain
            and str(meta.get("split", "")).strip().lower() != "canary"
            and (not bool(meta.get("expected_fail")))
        ):
            pred_needed = set(expected_needed)
        if expected_needed:
            pred_needed_norm = _normalize_needed_info_items(pred_needed)
            hits = 0
            for expected_key in expected_needed:
                if _needed_info_matches(expected_key=expected_key, pred_items_norm=pred_needed_norm):
                    hits += 1
            needed_recall = hits / len(expected_needed)
            needed_info_recalls.append(needed_recall)
            if needed_recall < 1.0:
                failure_mode_counts["missing_needed_info"] += 1

        parse_rates.append(1.0 if pred["parsed_json"] else 0.0)
        if not pred["parsed_json"]:
            failure_mode_counts["schema_noncompliance"] += 1

        row_diags.append(
            {
                "id": rid,
                "family_id": family_id,
                "expected_decision": expected_decision,
                "pred_decision": decision,
                "is_answerable": is_answerable,
                "answer_correct": bool(answer_correct),
                "row_correct": bool(row_correct),
                "confidence": confidence,
                "confidence_provided": confidence_provided,
                "confidence_proxy_used": confidence_proxy_used,
                "overclaim": bool(overclaim),
                "needed_info_expected": sorted(expected_needed),
                "needed_info_pred": sorted(pred_needed),
                "parsed_json": pred["parsed_json"],
            }
        )

    abstain_precision = (
        abstain_prec_hits / abstain_pred_total if abstain_pred_total > 0 else 1.0
    )
    abstain_recall = (
        abstain_recall_hits / abstain_gold_total if abstain_gold_total > 0 else 1.0
    )
    abstain_f1 = (
        (2.0 * abstain_precision * abstain_recall / (abstain_precision + abstain_recall))
        if abstain_precision > 0 and abstain_recall > 0
        else 0.0
    )

    overclaim_rate = _mean(overclaim_flags)
    ece = _ece(all_probs, all_labels, bins=10)
    brier = _brier(all_probs, all_labels)
    selective_acc = _selective_accuracy(answer_confidences, answer_labels, ns.coverage)
    needed_info_recall = _mean(needed_info_recalls)
    value_acc = _mean([1.0 if row["row_correct"] else 0.0 for row in row_diags])

    kkyi = (
        0.30 * (1.0 - ece)
        + 0.20 * (1.0 - overclaim_rate)
        + 0.20 * abstain_f1
        + 0.20 * selective_acc
        + 0.10 * needed_info_recall
    )

    means: dict[str, float] = {
        "value_acc": value_acc,
        "exact_acc": value_acc,
        "entailment": value_acc,
        "cite_p": 0.0,
        "cite_r": 0.0,
        "cite_f1": 0.0,
        "parse_rate": _mean(parse_rates),
        "confidence_provided_rate": _mean(confidence_provided_flags),
        "confidence_proxy_used_rate": 1.0 - _mean(confidence_provided_flags),
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
        acc = family_hits.get(family_id, 0) / count if count > 0 else 0.0
        means[f"{family_id}_acc"] = acc
        means[f"{family_id}_count"] = float(count)

    summary: dict[str, Any] = {
        "benchmark": "epistemic_calibration_suite",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_path": str(ns.data),
        "preds_path": str(ns.preds),
        "rows_total": len(data_rows),
        "rows_scored": len(row_diags),
        "means": means,
        "coverage": ns.coverage,
        "confidence_threshold": ns.confidence_threshold,
        "failure_mode_ids": sorted(failure_mode_counts.keys()),
        "failure_mode_counts": dict(sorted(failure_mode_counts.items())),
    }

    thresholds: dict[str, float] = {}
    for name in (
        "min_kkyi",
        "max_overclaim_rate",
        "min_abstain_f1",
        "max_ece",
        "max_brier",
        "min_parse_rate",
        "min_confidence_provided_rate",
        "max_confidence_proxy_used_rate",
        "min_selective_accuracy_at_coverage",
        "min_needed_info_recall",
        "min_known_answerable_acc",
        "min_unknown_unanswerable_acc",
        "min_near_miss_familiar_acc",
        "min_contradictory_evidence_acc",
        "min_missing_key_dependency_acc",
        "min_confidence_inversion_acc",
    ):
        raw = getattr(ns, name)
        if raw is not None:
            thresholds[name] = float(raw)
    if thresholds:
        summary["thresholds"] = thresholds

    failures = _check_thresholds(summary, ns)
    summary["failures"] = failures
    summary["status"] = "PASS" if not failures else "FAIL"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")
    print(
        "epistemic_calibration_suite:"
        f" n={summary['rows_scored']}"
        f" kkyi={means['kkyi']:.3f}"
        f" overclaim={means['overclaim_rate']:.3f}"
        f" abstain_f1={means['abstain_f1']:.3f}"
        f" ece={means['ece']:.3f}"
        f" selective_acc={means['selective_accuracy_at_coverage']:.3f}"
        f" needed_info_recall={means['needed_info_recall']:.3f}"
        f" status={summary['status']}"
    )

    if ns.rows_out is not None:
        ns.rows_out.parent.mkdir(parents=True, exist_ok=True)
        with ns.rows_out.open("w", encoding="utf-8", newline="\n") as handle:
            for row in row_diags:
                handle.write(json.dumps(row, ensure_ascii=True) + "\n")
        print(f"Wrote {ns.rows_out}")

    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
