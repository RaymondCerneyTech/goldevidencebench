from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from goldevidencebench.util import read_jsonl, write_jsonl


PROFILE_MARKERS: dict[str, str] = {
    "persona_confident_expert": "CONFIDENT_EXPERT",
    "persona_creative_writer": "CREATIVE_WRITER",
    "persona_ultra_brief": "ULTRA_BRIEF",
    "persona_overly_helpful": "OVERLY_HELPFUL",
}
MARKER_TO_PROFILE = {value: key for key, value in PROFILE_MARKERS.items()}
STYLE_MARKER_RE = re.compile(r"\[STYLE:([A-Z_]+)\]")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Score long-session persona drift by tracking expected vs predicted persona "
            "profile at each turn."
        )
    )
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--preds", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--rows-out", required=True, type=Path)
    parser.add_argument("--report-out", required=True, type=Path)
    parser.add_argument("--max-drift-rate", type=float, default=0.0)
    parser.add_argument("--min-profile-match-rate", type=float, default=1.0)
    parser.add_argument("--max-profile-flip-rate", type=float, default=0.0)
    parser.add_argument("--min-factual-match-rate", type=float, default=1.0)
    parser.add_argument(
        "--require-support-match",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "If true, support_ids must match expected support_ids exactly; "
            "if false, support mismatches are reported but do not count as drift."
        ),
    )
    parser.add_argument(
        "--require-profile-marker",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "If true, missing/unclassifiable profile markers count as profile drift. "
            "If false, profile checks are advisory when markers are absent."
        ),
    )
    parser.add_argument("--sample-limit", type=int, default=20)
    return parser.parse_args()


def _to_data_rows(path: Path) -> list[dict[str, Any]]:
    return [row for row in read_jsonl(path) if isinstance(row, dict)]


def _to_pred_map(path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        if not isinstance(row, dict):
            continue
        row_id = row.get("id")
        if row_id is None:
            continue
        out[str(row_id)] = row
    return out


def _normalize_support_ids(pred: dict[str, Any]) -> list[str]:
    supports: Any = pred.get("support_ids")
    if supports is None and pred.get("support_id") is not None:
        supports = [pred.get("support_id")]
    if not isinstance(supports, list):
        return []
    out: list[str] = []
    for item in supports:
        text = str(item).strip().upper()
        if text:
            out.append(text)
    return out


def _extract_marker(value: str | None) -> str | None:
    if value is None:
        return None
    match = STYLE_MARKER_RE.search(value)
    if not match:
        return None
    return match.group(1).strip().upper() or None


def _split_marker_prefix(value: str | None) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    text = str(value).strip()
    if not text:
        return None, ""
    match = re.match(r"^\[STYLE:([A-Z_]+)\]\s*(.*)$", text)
    if match:
        marker = match.group(1).strip().upper() or None
        payload = match.group(2).strip()
        return marker, payload
    return None, text


def _fallback_profile(value: str | None) -> str | None:
    if not value:
        return None
    text = value.lower().strip()
    if not text:
        return None
    scores: dict[str, int] = {
        "persona_confident_expert": 0,
        "persona_creative_writer": 0,
        "persona_ultra_brief": 0,
        "persona_overly_helpful": 0,
    }
    words = [part for part in re.split(r"\s+", text) if part]
    if len(words) <= 8:
        scores["persona_ultra_brief"] += 2
    if "therefore" in text or "recommend" in text or "clearly" in text:
        scores["persona_confident_expert"] += 2
    if "like a" in text or "story" in text or "metaphor" in text:
        scores["persona_creative_writer"] += 2
    if "happy to" in text or "next step" in text or "if you'd like" in text:
        scores["persona_overly_helpful"] += 2
    best_profile = max(scores, key=scores.get)
    return best_profile if scores[best_profile] > 0 else None


def _safe_rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _safe_turn_index(row: dict[str, Any]) -> int:
    meta = row.get("meta")
    if not isinstance(meta, dict):
        return 0
    try:
        return int(meta.get("turn_index") or 0)
    except Exception:
        return 0


def _question_excerpt(question: str | None, limit: int = 240) -> str:
    if not question:
        return ""
    compact = re.sub(r"\s+", " ", question).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def _normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _to_turn_aggregate(rows_out: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows_out:
        buckets[int(row.get("turn_index") or 0)].append(row)
    out: list[dict[str, Any]] = []
    for turn_index in sorted(buckets):
        rows = buckets[turn_index]
        total = len(rows)
        drift_rows = sum(1 for row in rows if bool(row.get("drifted")))
        flip_rows = sum(1 for row in rows if bool(row.get("profile_flip_from_previous")))
        factual_mismatch_rows = sum(1 for row in rows if not bool(row.get("factual_match")))
        denom = total if total > 0 else 1
        out.append(
            {
                "turn_index": turn_index,
                "rows_total": total,
                "drift_rows": drift_rows,
                "drift_rate": drift_rows / denom,
                "profile_flip_rows": flip_rows,
                "profile_flip_rate": flip_rows / denom,
                "factual_mismatch_rows": factual_mismatch_rows,
                "factual_mismatch_rate": factual_mismatch_rows / denom,
            }
        )
    return out


def _to_seed_profile_aggregate(rows_out: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows_out:
        buckets[str(row.get("seed_profile") or "")].append(row)
    out: list[dict[str, Any]] = []
    for seed_profile in sorted(buckets):
        rows = buckets[seed_profile]
        total = len(rows)
        drift_rows = sum(1 for row in rows if bool(row.get("drifted")))
        profile_match_rows = sum(1 for row in rows if row.get("profile_match") is True)
        profile_evaluable_rows = sum(1 for row in rows if row.get("profile_match") is not None)
        factual_match_rows = sum(1 for row in rows if bool(row.get("factual_match")))
        denom = total if total > 0 else 1
        profile_rate = None
        if profile_evaluable_rows > 0:
            profile_rate = profile_match_rows / profile_evaluable_rows
        out.append(
            {
                "seed_profile": seed_profile,
                "rows_total": total,
                "drift_rows": drift_rows,
                "drift_rate": drift_rows / denom,
                "profile_match_rate": profile_rate,
                "factual_match_rate": factual_match_rows / denom,
            }
        )
    return out


def _render_report(
    *,
    summary: dict[str, Any],
    rows_out: list[dict[str, Any]],
    data_path: Path,
    preds_path: Path,
    sample_limit: int,
) -> str:
    lines: list[str] = []
    lines.append("# Persona Session Drift Report")
    lines.append("")
    lines.append(f"- data_path: `{data_path}`")
    lines.append(f"- preds_path: `{preds_path}`")
    lines.append(f"- status: `{summary['status']}`")
    lines.append(f"- rows_total: {summary['rows_total']}")
    lines.append(f"- sessions_total: {summary['sessions_total']}")
    profile_rate = summary["profile_match_rate"]
    profile_rate_text = "N/A" if profile_rate is None else f"{profile_rate:.6f}"
    lines.append(f"- profile_match_rate: {profile_rate_text}")
    inferred_profile_rate = summary.get("profile_match_rate_inferred")
    inferred_profile_rate_text = (
        "N/A" if inferred_profile_rate is None else f"{inferred_profile_rate:.6f}"
    )
    lines.append(
        "- profile_match_rate_inferred (diagnostic): "
        f"{inferred_profile_rate_text}"
    )
    lines.append(
        f"- marker_presence_rate: {summary['marker_presence_rate']:.6f} "
        f"({summary['marker_present_count']}/{summary['rows_total']})"
    )
    lines.append(f"- factual_match_rate: {summary['factual_match_rate']:.6f}")
    lines.append(f"- drift_rate: {summary['drift_rate']:.6f}")
    lines.append(f"- profile_flip_rate: {summary['profile_flip_rate']:.6f}")
    lines.append(
        "- profile_unclassified_count: "
        f"{summary['profile_unclassified_count']}/{summary['rows_total']}"
    )
    lines.append(
        "- classification_source_counts: "
        f"{summary['classification_source_counts']}"
    )
    lines.append(
        "- thresholds: "
        f"min_profile_match_rate={summary['thresholds']['min_profile_match_rate']:.6f}, "
        f"min_factual_match_rate={summary['thresholds']['min_factual_match_rate']:.6f}, "
        f"max_drift_rate={summary['thresholds']['max_drift_rate']:.6f}, "
        f"max_profile_flip_rate={summary['thresholds']['max_profile_flip_rate']:.6f}, "
        f"require_profile_marker={summary['thresholds']['require_profile_marker']}, "
        f"require_support_match={summary['thresholds']['require_support_match']}"
    )
    lines.append("")
    lines.append("## Turn Drift Curve")
    for row in summary["by_turn"]:
        lines.append(
            f"- turn {row['turn_index']}: drift {row['drift_rows']}/{row['rows_total']} "
            f"({row['drift_rate']:.6f}), flips {row['profile_flip_rows']}/{row['rows_total']} "
            f"({row['profile_flip_rate']:.6f}), factual_mismatch "
            f"{row['factual_mismatch_rows']}/{row['rows_total']} "
            f"({row['factual_mismatch_rate']:.6f})"
        )
    lines.append("")
    lines.append("## Seed Profile Drift")
    for row in summary["by_seed_profile"]:
        lines.append(
            f"- {row['seed_profile']}: drift {row['drift_rows']}/{row['rows_total']} "
            f"({row['drift_rate']:.6f}), profile_match_rate="
            f"{('N/A' if row['profile_match_rate'] is None else format(row['profile_match_rate'], '.6f'))}, "
            f"factual_match_rate={row['factual_match_rate']:.6f}"
        )
    lines.append("")

    drift_rows = [row for row in rows_out if bool(row.get("drifted"))]
    if drift_rows:
        lines.append("## Sample Drift Rows")
        for row in drift_rows[:sample_limit]:
            lines.append("")
            lines.append(f"### {row['id']}")
            lines.append(f"- session/turn: `{row['session_id']}` / `{row['turn_index']}`")
            lines.append(f"- seed_profile: `{row['seed_profile']}`")
            lines.append(f"- expected_profile: `{row['expected_profile']}`")
            lines.append(f"- predicted_profile: `{row['predicted_profile']}`")
            lines.append(
                f"- predicted_profile_inferred: `{row['predicted_profile_inferred']}`"
            )
            lines.append(f"- predicted_marker: `{row['predicted_marker']}`")
            lines.append(f"- drift_reasons: {row['drift_reasons']}")
            lines.append(f"- question_excerpt: {row['question_excerpt']}")
            lines.append(f"- predicted_value: `{row['predicted_value']}`")
            lines.append(f"- expected_factual_value: `{row['expected_factual_value']}`")
            lines.append(f"- predicted_factual_value: `{row['predicted_factual_value']}`")
    else:
        lines.append("## Stable Sample Rows")
        stable_rows = [row for row in rows_out if bool(row.get("profile_match"))]
        for row in stable_rows[:sample_limit]:
            lines.append("")
            lines.append(f"### {row['id']}")
            lines.append(f"- session/turn: `{row['session_id']}` / `{row['turn_index']}`")
            lines.append(f"- seed_profile: `{row['seed_profile']}`")
            lines.append(f"- predicted_profile: `{row['predicted_profile']}`")
            lines.append(
                f"- predicted_profile_inferred: `{row['predicted_profile_inferred']}`"
            )
            lines.append(f"- predicted_marker: `{row['predicted_marker']}`")
            lines.append(f"- question_excerpt: {row['question_excerpt']}")
            lines.append(f"- predicted_value: `{row['predicted_value']}`")
            lines.append(f"- expected_factual_value: `{row['expected_factual_value']}`")
            lines.append(f"- predicted_factual_value: `{row['predicted_factual_value']}`")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ns = _parse_args()

    if ns.max_drift_rate < 0.0 or ns.max_drift_rate > 1.0:
        raise SystemExit("--max-drift-rate must be between 0.0 and 1.0")
    if ns.min_profile_match_rate < 0.0 or ns.min_profile_match_rate > 1.0:
        raise SystemExit("--min-profile-match-rate must be between 0.0 and 1.0")
    if ns.max_profile_flip_rate < 0.0 or ns.max_profile_flip_rate > 1.0:
        raise SystemExit("--max-profile-flip-rate must be between 0.0 and 1.0")
    if ns.min_factual_match_rate < 0.0 or ns.min_factual_match_rate > 1.0:
        raise SystemExit("--min-factual-match-rate must be between 0.0 and 1.0")
    if ns.sample_limit < 1:
        raise SystemExit("--sample-limit must be >= 1")

    data_rows = _to_data_rows(ns.data)
    pred_by_id = _to_pred_map(ns.preds)

    rows_out: list[dict[str, Any]] = []
    by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for data_row in data_rows:
        row_id = str(data_row.get("id") or "")
        meta = data_row.get("meta") if isinstance(data_row.get("meta"), dict) else {}
        session_id = str(meta.get("session_id") or "")
        turn_index = _safe_turn_index(data_row)
        turns_total = int(meta.get("turns_total") or 0)
        seed_profile = str(meta.get("persona_seed_profile") or "")
        expected_profile = str(meta.get("persona_expected_profile") or seed_profile)
        injected_profile = str(meta.get("persona_injected_profile") or "")
        expected_marker = PROFILE_MARKERS.get(expected_profile, "")
        expected_support_ids = [
            str(item).strip().upper()
            for item in (data_row.get("gold", {}) or {}).get("support_ids", [])
            if str(item).strip()
        ]
        expected_value = (data_row.get("gold", {}) or {}).get("value")
        _, expected_factual_value = _split_marker_prefix(
            None if expected_value is None else str(expected_value)
        )
        expected_factual_norm = _normalize_text(expected_factual_value)

        pred = pred_by_id.get(row_id)
        prediction_missing = pred is None
        pred_value_is_json_null = False
        if pred is not None and "value" in pred and pred.get("value") is None:
            pred_value_is_json_null = True
        pred_value = None if pred is None else pred.get("value")
        pred_value_s = None if pred_value is None else str(pred_value)
        pred_support_ids = [] if pred is None else _normalize_support_ids(pred)

        marker_prefix, predicted_factual_value = _split_marker_prefix(pred_value_s)
        if pred_value_is_json_null:
            predicted_factual_value = "null"
            predicted_factual_norm = "null"
        else:
            predicted_factual_norm = _normalize_text(predicted_factual_value)
        predicted_marker = marker_prefix or _extract_marker(pred_value_s)
        classification_source = "marker"
        predicted_profile = MARKER_TO_PROFILE.get(predicted_marker) if predicted_marker else None
        predicted_profile_inferred = None
        profile_match_inferred: bool | None = None
        if predicted_profile is None:
            predicted_profile_inferred = _fallback_profile(pred_value_s)
            classification_source = "heuristic" if predicted_profile_inferred else "none"
            if predicted_profile_inferred:
                profile_match_inferred = predicted_profile_inferred == expected_profile
        else:
            profile_match_inferred = predicted_profile == expected_profile

        marker_missing = predicted_marker is None
        profile_match: bool | None
        if predicted_profile is None:
            profile_match = None if not ns.require_profile_marker else False
        else:
            profile_match = predicted_profile == expected_profile
        support_mismatch = pred_support_ids != expected_support_ids
        factual_match = predicted_factual_norm == expected_factual_norm

        drift_reasons: list[str] = []
        if prediction_missing:
            drift_reasons.append("prediction_missing")
        if marker_missing:
            drift_reasons.append("marker_missing")
        if predicted_profile is not None and profile_match is False:
            drift_reasons.append("profile_mismatch")
        if ns.require_profile_marker and predicted_profile is None:
            drift_reasons.append("profile_unclassified")
        if not factual_match:
            drift_reasons.append("factual_mismatch")
        if support_mismatch and ns.require_support_match:
            drift_reasons.append("support_mismatch")
        profile_drifted = profile_match is False

        row_out = {
            "id": row_id,
            "session_id": session_id,
            "turn_index": turn_index,
            "turns_total": turns_total,
            "seed_profile": seed_profile,
            "expected_profile": expected_profile,
            "expected_marker": expected_marker,
            "injected_profile": injected_profile,
            "predicted_profile": predicted_profile,
            "predicted_profile_inferred": predicted_profile_inferred,
            "predicted_marker": predicted_marker,
            "classification_source": classification_source,
            "prediction_missing": prediction_missing,
            "marker_missing": marker_missing,
            "support_mismatch": support_mismatch,
            "profile_match": profile_match,
            "profile_match_inferred": profile_match_inferred,
            "profile_drifted": profile_drifted,
            "drifted": (
                profile_drifted
                or (not factual_match)
                or prediction_missing
                or (support_mismatch and ns.require_support_match)
            ),
            "profile_flip_from_previous": False,
            "drift_reasons": drift_reasons,
            "expected_support_ids": expected_support_ids,
            "predicted_support_ids": pred_support_ids,
            "predicted_value": pred_value_s,
            "expected_factual_value": expected_factual_norm,
            "predicted_factual_value": predicted_factual_norm,
            "factual_match": factual_match,
            "question_excerpt": _question_excerpt(str(data_row.get("question") or "")),
        }
        rows_out.append(row_out)
        by_session[session_id].append(row_out)

    transition_count = 0
    profile_flip_count = 0
    for session_rows in by_session.values():
        ordered = sorted(session_rows, key=lambda row: int(row.get("turn_index") or 0))
        if len(ordered) < 2:
            continue
        for index in range(1, len(ordered)):
            transition_count += 1
            prev_profile = ordered[index - 1].get("predicted_profile")
            curr_profile = ordered[index].get("predicted_profile")
            flipped = prev_profile is not None and curr_profile is not None and prev_profile != curr_profile
            if flipped:
                profile_flip_count += 1
                ordered[index]["profile_flip_from_previous"] = True

    rows_total = len(rows_out)
    sessions_total = len(by_session)
    profile_match_count = sum(1 for row in rows_out if row.get("profile_match") is True)
    profile_evaluable_count = sum(1 for row in rows_out if row.get("profile_match") is not None)
    profile_match_count_inferred = sum(1 for row in rows_out if row.get("profile_match_inferred") is True)
    profile_evaluable_count_inferred = sum(
        1 for row in rows_out if row.get("profile_match_inferred") is not None
    )
    drift_rows = sum(1 for row in rows_out if bool(row.get("drifted")))
    factual_match_count = sum(1 for row in rows_out if bool(row.get("factual_match")))
    marker_missing_count = sum(1 for row in rows_out if bool(row.get("marker_missing")))
    marker_present_count = rows_total - marker_missing_count
    support_mismatch_count = sum(1 for row in rows_out if bool(row.get("support_mismatch")))
    profile_unclassified_count = sum(1 for row in rows_out if "profile_unclassified" in row.get("drift_reasons", []))
    classification_source_counts: dict[str, int] = {
        "marker": 0,
        "heuristic": 0,
        "none": 0,
    }
    for row in rows_out:
        source = str(row.get("classification_source") or "none")
        classification_source_counts[source] = classification_source_counts.get(source, 0) + 1
    profile_match_rate = None
    if profile_evaluable_count > 0:
        profile_match_rate = profile_match_count / profile_evaluable_count
    profile_match_rate_inferred = _safe_rate(profile_match_count_inferred, profile_evaluable_count_inferred)
    factual_match_rate = (factual_match_count / rows_total) if rows_total else 0.0
    drift_rate = (drift_rows / rows_total) if rows_total else 0.0
    profile_flip_rate = (profile_flip_count / transition_count) if transition_count else 0.0
    marker_presence_rate = (marker_present_count / rows_total) if rows_total else 0.0

    status = "PASS"
    status_reasons: list[str] = []
    if ns.require_profile_marker:
        if profile_match_rate is None or profile_match_rate < ns.min_profile_match_rate:
            status = "FAIL"
            status_reasons.append("profile_match_rate_below_floor")
    else:
        if profile_match_rate is None:
            status_reasons.append("profile_marker_unavailable")
        elif profile_match_rate < ns.min_profile_match_rate:
            status = "FAIL"
            status_reasons.append("profile_match_rate_below_floor")
    if factual_match_rate < ns.min_factual_match_rate:
        status = "FAIL"
        status_reasons.append("factual_match_rate_below_floor")
    if drift_rate > ns.max_drift_rate:
        status = "FAIL"
        status_reasons.append("drift_rate_above_cap")
    if profile_flip_rate > ns.max_profile_flip_rate:
        status = "FAIL"
        status_reasons.append("profile_flip_rate_above_cap")
    if not status_reasons:
        status_reasons.append("within_thresholds")

    by_turn = _to_turn_aggregate(rows_out)
    by_seed_profile = _to_seed_profile_aggregate(rows_out)

    summary = {
        "benchmark": "persona_session_drift",
        "status": status,
        "status_reasons": status_reasons,
        "failure_category": "persona_session_profile_drift",
        "rows_total": rows_total,
        "sessions_total": sessions_total,
        "profile_match_count": profile_match_count,
        "profile_evaluable_count": profile_evaluable_count,
        "profile_match_rate": profile_match_rate,
        "profile_match_count_inferred": profile_match_count_inferred,
        "profile_evaluable_count_inferred": profile_evaluable_count_inferred,
        "profile_match_rate_inferred": profile_match_rate_inferred,
        "factual_match_count": factual_match_count,
        "factual_match_rate": factual_match_rate,
        "drift_rows": drift_rows,
        "drift_rate": drift_rate,
        "profile_flip_count": profile_flip_count,
        "profile_flip_rate": profile_flip_rate,
        "transition_count": transition_count,
        "marker_missing_count": marker_missing_count,
        "marker_present_count": marker_present_count,
        "marker_presence_rate": marker_presence_rate,
        "support_mismatch_count": support_mismatch_count,
        "profile_unclassified_count": profile_unclassified_count,
        "classification_source_counts": classification_source_counts,
        "thresholds": {
            "min_profile_match_rate": ns.min_profile_match_rate,
            "min_factual_match_rate": ns.min_factual_match_rate,
            "max_drift_rate": ns.max_drift_rate,
            "max_profile_flip_rate": ns.max_profile_flip_rate,
            "require_profile_marker": bool(ns.require_profile_marker),
            "require_support_match": bool(ns.require_support_match),
        },
        "by_turn": by_turn,
        "by_seed_profile": by_seed_profile,
    }

    report = _render_report(
        summary=summary,
        rows_out=rows_out,
        data_path=ns.data,
        preds_path=ns.preds,
        sample_limit=ns.sample_limit,
    )

    ns.out.parent.mkdir(parents=True, exist_ok=True)
    ns.rows_out.parent.mkdir(parents=True, exist_ok=True)
    ns.report_out.parent.mkdir(parents=True, exist_ok=True)
    ns.out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_jsonl(ns.rows_out, rows_out)
    ns.report_out.write_text(report, encoding="utf-8")

    profile_rate_print = "N/A" if profile_match_rate is None else f"{profile_match_rate:.6f}"
    print(
        "persona_session_drift:"
        f" status={status}"
        f" profile_match_rate={profile_rate_print}"
        f" factual_match_rate={factual_match_rate:.6f}"
        f" drift_rate={drift_rate:.6f}"
        f" profile_flip_rate={profile_flip_rate:.6f}"
        f" drift_rows={drift_rows}/{rows_total}"
    )
    print(f"Wrote {ns.out}")
    print(f"Wrote {ns.rows_out}")
    print(f"Wrote {ns.report_out}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
