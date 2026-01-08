from __future__ import annotations

from typing import Any

from goldevidencebench.ui_prompt import extract_ui_instruction

OVERLAY_MODAL_SCOPES = {"popup", "overlay"}


def _is_overlay_candidate(candidate: dict[str, Any]) -> bool:
    if candidate.get("overlay") is True:
        return True
    modal_scope = candidate.get("modal_scope")
    if isinstance(modal_scope, str) and modal_scope.strip().lower() in OVERLAY_MODAL_SCOPES:
        return True
    return False


def filter_overlay_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    filtered = [candidate for candidate in candidates if not _is_overlay_candidate(candidate)]
    return filtered or candidates


def allow_overlay_from_row(row: dict[str, Any]) -> bool:
    if row.get("allow_overlay") is True:
        return True
    meta = row.get("meta")
    if isinstance(meta, dict) and meta.get("allow_overlay") is True:
        return True
    return False


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _has_negated(text: str, token: str) -> bool:
    for prefix in ("not", "no"):
        for mid in ("", " the", " a", " an"):
            if f"{prefix}{mid} {token}" in text:
                return True
    return False


def _filter_modal_scope(
    candidates: list[dict[str, Any]], *, require_modal: bool | None
) -> list[dict[str, Any]]:
    if require_modal is None:
        return candidates
    filtered = []
    for candidate in candidates:
        modal_scope = candidate.get("modal_scope")
        has_modal = isinstance(modal_scope, str) and modal_scope.strip()
        if require_modal and has_modal:
            filtered.append(candidate)
        if not require_modal and not has_modal:
            filtered.append(candidate)
    return filtered or candidates


def _filter_by_bbox(
    candidates: list[dict[str, Any]], *, axis: int, pick_max: bool
) -> list[dict[str, Any]]:
    with_bbox: list[tuple[dict[str, Any], float]] = []
    for candidate in candidates:
        bbox = candidate.get("bbox")
        if isinstance(bbox, list) and len(bbox) == 4 and isinstance(bbox[axis], (int, float)):
            with_bbox.append((candidate, float(bbox[axis])))
    if not with_bbox:
        return candidates
    target = max(v for _, v in with_bbox) if pick_max else min(v for _, v in with_bbox)
    filtered = [candidate for candidate, value in with_bbox if value == target]
    return filtered or candidates


def _filter_by_candidate_id(
    candidates: list[dict[str, Any]], *, token: str
) -> list[dict[str, Any]]:
    token = token.lower()
    filtered = []
    for candidate in candidates:
        candidate_id = candidate.get("candidate_id")
        if isinstance(candidate_id, str) and token in candidate_id.lower():
            filtered.append(candidate)
    return filtered or candidates


def _bbox_sum(candidate: dict[str, Any]) -> float | None:
    bbox = candidate.get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 4:
        return None
    x = bbox[0]
    y = bbox[1]
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        return None
    return float(x) + float(y)


def tie_break_same_label_candidates(
    candidates: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    best_by_label: dict[str, dict[str, Any]] = {}
    best_score: dict[str, float] = {}
    labels_with_bbox: set[str] = set()
    seen_labels: set[str] = set()

    for candidate in candidates:
        label = candidate.get("label")
        if not isinstance(label, str) or not label.strip():
            continue
        label = label.strip()
        seen_labels.add(label)
        score = _bbox_sum(candidate)
        if score is None:
            continue
        labels_with_bbox.add(label)
        if label not in best_by_label or score > best_score.get(label, float("-inf")):
            best_by_label[label] = candidate
            best_score[label] = score

    if not labels_with_bbox:
        return candidates

    filtered: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        label = candidate.get("label")
        if not isinstance(label, str) or not label.strip():
            filtered.append(candidate)
            continue
        label = label.strip()
        if label not in labels_with_bbox:
            filtered.append(candidate)
            continue
        if label in seen:
            continue
        seen.add(label)
        filtered.append(best_by_label.get(label, candidate))
    return filtered or candidates


def preselect_candidates(
    row: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    apply_overlay_filter: bool,
    apply_rules: bool,
) -> list[dict[str, Any]]:
    instruction = extract_ui_instruction(row)
    text = instruction.lower()

    neg_overlay = _has_negated(text, "popup") or _has_negated(text, "overlay")
    wants_overlay = _has_any(text, ("popup", "overlay")) and not neg_overlay
    neg_modal = _has_negated(text, "modal") or _has_negated(text, "dialog")
    wants_modal = _has_any(text, ("modal", "dialog")) and not neg_modal
    prefers_main = _has_any(text, ("main page", "main screen"))

    wants_primary = "primary" in text
    wants_secondary = "secondary" in text

    wants_bottom = _has_any(text, ("bottom", "lower"))
    wants_top = _has_any(text, ("top", "upper"))
    wants_left = _has_any(text, ("left", "leftmost"))
    wants_right = _has_any(text, ("right", "rightmost"))

    if apply_overlay_filter and not wants_overlay and not allow_overlay_from_row(row):
        candidates = filter_overlay_candidates(candidates)

    if apply_rules and wants_overlay:
        overlay_only = [candidate for candidate in candidates if _is_overlay_candidate(candidate)]
        if overlay_only:
            candidates = overlay_only

    if apply_rules and wants_modal:
        candidates = _filter_modal_scope(candidates, require_modal=True)
    if apply_rules and prefers_main:
        candidates = _filter_modal_scope(candidates, require_modal=False)

    if apply_rules and wants_primary:
        candidates = _filter_by_candidate_id(candidates, token="primary")
    if apply_rules and wants_secondary:
        candidates = _filter_by_candidate_id(candidates, token="secondary")

    if apply_rules and wants_bottom:
        candidates = _filter_by_bbox(candidates, axis=1, pick_max=True)
    if apply_rules and wants_top:
        candidates = _filter_by_bbox(candidates, axis=1, pick_max=False)
    if apply_rules and wants_left:
        candidates = _filter_by_bbox(candidates, axis=0, pick_max=False)
    if apply_rules and wants_right:
        candidates = _filter_by_bbox(candidates, axis=0, pick_max=True)

    candidates = tie_break_same_label_candidates(candidates)
    return candidates
