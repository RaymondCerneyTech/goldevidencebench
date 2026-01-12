from __future__ import annotations

import json
from typing import Any, Iterable

DEFAULT_UI_INSTRUCTION = "Select the best candidate for the current UI task."


def _pick_text(value: Any) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        if text:
            return text
    return None


def extract_ui_instruction(row: dict[str, Any]) -> str:
    for key in ("instruction", "goal", "task", "question"):
        text = _pick_text(row.get(key))
        if text:
            return text
    meta = row.get("meta")
    if isinstance(meta, dict):
        for key in ("instruction", "goal", "task", "question"):
            text = _pick_text(meta.get(key))
            if text:
                return text
    return DEFAULT_UI_INSTRUCTION


def _fmt(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True)


def format_ui_candidate(candidate: dict[str, Any]) -> str:
    fields: list[str] = []
    candidate_id = candidate.get("candidate_id")
    if candidate_id is not None:
        fields.append(f"id={_fmt(candidate_id)}")
    label = candidate.get("label")
    if label is not None:
        fields.append(f"label={_fmt(label)}")
    role = candidate.get("role")
    if role is not None:
        fields.append(f"role={_fmt(role)}")
    action_type = candidate.get("action_type")
    if action_type is not None:
        fields.append(f"action={_fmt(action_type)}")
    app_path = candidate.get("app_path")
    if app_path is not None:
        fields.append(f"app_path={_fmt(app_path)}")
    modal_scope = candidate.get("modal_scope")
    if modal_scope is not None:
        fields.append(f"modal_scope={_fmt(modal_scope)}")
    for flag in ("visible", "enabled", "overlay"):
        if flag in candidate:
            fields.append(f"{flag}={_fmt(candidate.get(flag))}")
    bbox = candidate.get("bbox")
    if isinstance(bbox, list) and len(bbox) == 4:
        fields.append(f"bbox={_fmt(bbox)}")
    z_index = candidate.get("z_index")
    if z_index is not None:
        fields.append(f"z_index={_fmt(z_index)}")
    return "- " + " ".join(fields)


def format_ui_candidates(candidates: Iterable[dict[str, Any]]) -> str:
    return "\n".join(format_ui_candidate(candidate) for candidate in candidates)


def build_ui_prompt(row: dict[str, Any], candidates: list[dict[str, Any]]) -> str:
    instruction = extract_ui_instruction(row)
    context = _pick_text(row.get("context"))
    if context is None:
        meta = row.get("meta")
        if isinstance(meta, dict):
            context = _pick_text(meta.get("context"))
    candidate_lines = format_ui_candidates(candidates)
    parts = [
        "You are selecting a UI action from candidates.",
        f"Instruction: {instruction}",
        "Popup/overlay options are traps unless the instruction explicitly mentions a modal, dialog, popup, or overlay.",
        "Prefer modal_scope=\"main\" unless the instruction requires a modal.",
        "Treat overlay/overlay_present/z_index as indicators of overlays.",
    ]
    if context:
        parts.append(f"Context: {context}")
    parts.extend(
        [
            "Return JSON with keys: value, support_ids.",
            "support_ids must be an empty list [].",
            "value must be one of the candidate id values or null.",
            "Candidates:",
            candidate_lines,
            "Respond with only JSON.",
        ]
    )
    return "\n".join(parts)
