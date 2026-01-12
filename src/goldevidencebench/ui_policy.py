from __future__ import annotations

from typing import Any

from goldevidencebench.ui_prompt import extract_ui_instruction

OVERLAY_MODAL_SCOPES = {"popup", "overlay"}
LABEL_KEYWORD_STOPWORDS = {
    "a",
    "an",
    "and",
    "button",
    "buttons",
    "choose",
    "click",
    "close",
    "dialog",
    "left",
    "leftmost",
    "link",
    "links",
    "main",
    "menu",
    "modal",
    "of",
    "on",
    "open",
    "option",
    "options",
    "or",
    "overlay",
    "page",
    "popup",
    "press",
    "primary",
    "right",
    "rightmost",
    "screen",
    "secondary",
    "select",
    "tab",
    "tabs",
    "tap",
    "the",
    "to",
    "top",
    "upper",
    "use",
    "window",
    "bottom",
    "lower",
}
LABEL_KEYWORD_SYNONYMS = {
    "apply": ("confirm", "save", "submit"),
    "back": ("previous", "prev"),
    "begin": ("start", "open"),
    "cancel": ("close", "dismiss"),
    "close": ("cancel", "dismiss"),
    "confirm": ("ok", "okay", "yes", "apply", "save", "continue"),
    "continue": ("next", "proceed"),
    "deactivate": ("disable", "turnoff"),
    "disable": ("deactivate", "turnoff"),
    "dismiss": ("cancel", "close"),
    "done": ("finish", "complete"),
    "enable": ("activate", "turnon"),
    "finish": ("done", "complete"),
    "launch": ("open", "start"),
    "next": ("continue", "proceed"),
    "ok": ("confirm", "okay", "yes"),
    "okay": ("confirm", "ok", "yes"),
    "open": ("start", "begin", "launch"),
    "previous": ("back", "prev"),
    "prev": ("back", "previous"),
    "proceed": ("continue", "next"),
    "save": ("apply", "confirm", "submit"),
    "start": ("begin", "open", "launch"),
    "submit": ("apply", "send"),
    "turnoff": ("disable", "deactivate"),
    "turnon": ("enable", "activate"),
    "yes": ("confirm", "ok", "okay"),
    "activate": ("enable", "turnon"),
}
OVERLAY_CONFIRM_TOKENS = {
    "accept",
    "approve",
    "apply",
    "confirm",
    "continue",
    "finish",
    "ok",
    "okay",
    "proceed",
    "yes",
}

STATE_ADVANCE_KEYS = {"permission_granted", "consent_granted"}


def _candidate_clears_modal(candidate: dict[str, Any]) -> bool:
    if candidate.get("modal_cleared") is True:
        return True
    next_state = candidate.get("next_state")
    if isinstance(next_state, dict) and next_state.get("modal_cleared") is True:
        return True
    state = candidate.get("state")
    if isinstance(state, dict) and state.get("modal_cleared") is True:
        return True
    return False


def _filter_overlay_clears_modal(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    overlay_candidates = [candidate for candidate in candidates if _is_overlay_candidate(candidate)]
    if not overlay_candidates or len(overlay_candidates) == len(candidates):
        return candidates
    matches = [candidate for candidate in overlay_candidates if _candidate_clears_modal(candidate)]
    if matches:
        return matches
    return candidates


def _candidate_opens_modal(candidate: dict[str, Any]) -> bool:
    next_state = candidate.get("next_state")
    if isinstance(next_state, dict):
        modal_scope = next_state.get("modal_scope")
        if isinstance(modal_scope, str) and modal_scope.strip().lower() in OVERLAY_MODAL_SCOPES:
            return True
        if next_state.get("overlay_present") is True and not next_state.get("modal_cleared"):
            return True
    return False


def _filter_overlay_opens_modal(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    overlay_candidates = [candidate for candidate in candidates if _is_overlay_candidate(candidate)]
    if not overlay_candidates or len(overlay_candidates) == len(candidates):
        return candidates
    matches = [candidate for candidate in overlay_candidates if _candidate_opens_modal(candidate)]
    if matches:
        return matches
    return candidates


def _is_overlay_candidate(candidate: dict[str, Any]) -> bool:
    if candidate.get("overlay_present") is True:
        return True
    if candidate.get("overlay") is True:
        return True
    modal_scope = candidate.get("modal_scope")
    if isinstance(modal_scope, str) and modal_scope.strip().lower() in OVERLAY_MODAL_SCOPES:
        return True
    return False


def filter_overlay_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    filtered = [candidate for candidate in candidates if not _is_overlay_candidate(candidate)]
    return filtered or candidates


def _filter_non_overlay(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    non_overlay = [candidate for candidate in candidates if not _is_overlay_candidate(candidate)]
    if non_overlay:
        candidates = non_overlay
    with_z: list[tuple[dict[str, Any], float]] = []
    for candidate in candidates:
        z_index = candidate.get("z_index")
        if isinstance(z_index, (int, float)):
            with_z.append((candidate, float(z_index)))
    if not with_z:
        return candidates
    min_z = min(value for _, value in with_z)
    filtered = [candidate for candidate, value in with_z if value == min_z]
    return filtered or candidates


def allow_overlay_from_row(row: dict[str, Any]) -> bool:
    if row.get("allow_overlay") is True:
        return True
    meta = row.get("meta")
    if isinstance(meta, dict) and meta.get("allow_overlay") is True:
        return True
    return False


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    tokens = set(_tokenize_text(text))
    return any(needle in tokens for needle in needles)


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


def _is_main_scope(candidate: dict[str, Any]) -> bool:
    modal_scope = candidate.get("modal_scope")
    if modal_scope is None:
        return True
    if isinstance(modal_scope, str):
        return modal_scope.strip().lower() in {"", "main"}
    return False


def _filter_main_scope(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    filtered = [candidate for candidate in candidates if _is_main_scope(candidate)]
    return filtered or candidates


def _filter_actionable(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for candidate in candidates:
        if candidate.get("visible") is False:
            continue
        if candidate.get("enabled") is False:
            continue
        if candidate.get("clickable") is False:
            continue
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


def _tokenize_text(text: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    for char in text.lower():
        if char.isalnum():
            current.append(char)
            continue
        if current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return tokens


def _label_tokens(label: str) -> set[str]:
    return {token for token in _tokenize_text(label) if token}


def _token_matches(instruction_token: str, label_token: str) -> bool:
    if instruction_token == label_token:
        return True
    if len(instruction_token) < 4 or len(label_token) < 4:
        return False
    return instruction_token.startswith(label_token) or label_token.startswith(instruction_token)


def _expand_keyword_tokens(tokens: list[str]) -> list[str]:
    expanded: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        for candidate in (token, *LABEL_KEYWORD_SYNONYMS.get(token, ())):
            if candidate in seen:
                continue
            expanded.append(candidate)
            seen.add(candidate)
    return expanded


def _desired_role_from_instruction(instruction: str) -> str | None:
    tokens = _tokenize_text(instruction)
    has_button = "button" in tokens
    has_link = "link" in tokens
    if has_button and not has_link:
        return "button"
    if has_link and not has_button:
        return "link"
    return None


def _filter_by_role(candidates: list[dict[str, Any]], role: str) -> list[dict[str, Any]]:
    matches = [
        candidate
        for candidate in candidates
        if isinstance(candidate.get("role"), str)
        and candidate.get("role", "").strip().lower() == role
    ]
    if not matches or len(matches) == len(candidates):
        return candidates
    return matches


def _filter_by_label_keywords(
    candidates: list[dict[str, Any]], instruction: str
) -> tuple[list[dict[str, Any]], str | None]:
    if not instruction:
        return candidates, None
    instruction_tokens = [
        token for token in _tokenize_text(instruction) if token not in LABEL_KEYWORD_STOPWORDS
    ]
    if not instruction_tokens:
        return candidates, None
    instruction_tokens = _expand_keyword_tokens(instruction_tokens)

    candidate_tokens: list[tuple[dict[str, Any], set[str]]] = []
    label_token_set: set[str] = set()
    for candidate in candidates:
        label = candidate.get("label")
        tokens: set[str] = set()
        if isinstance(label, str) and label.strip():
            tokens = _label_tokens(label)
        candidate_tokens.append((candidate, tokens))
        label_token_set.update(tokens)

    if not label_token_set:
        return candidates, None

    match_tokens: list[str] = []
    for token in instruction_tokens:
        if any(_token_matches(token, label_token) for label_token in label_token_set) and token not in match_tokens:
            match_tokens.append(token)

    best_matches: list[dict[str, Any]] | None = None
    best_token: str | None = None
    best_size: int | None = None
    for token in match_tokens:
        matches = [
            candidate
            for candidate, tokens in candidate_tokens
            if any(_token_matches(token, label_token) for label_token in tokens)
        ]
        if not matches or len(matches) == len(candidates):
            continue
        size = len(matches)
        if best_size is None or size < best_size:
            best_size = size
            best_token = token
            best_matches = matches
    if best_matches is None:
        return candidates, None
    return best_matches, best_token


SAVE_DIALOG_DEST_TOKENS = {"desktop", "documents", "downloads"}
SAVE_DIALOG_VERB_TOKENS = {"save"}


def _instruction_needs_save_dialog(instruction: str) -> bool:
    tokens = set(_tokenize_text(instruction))
    if not tokens:
        return False
    if not (tokens & SAVE_DIALOG_VERB_TOKENS):
        return False
    return bool(tokens & SAVE_DIALOG_DEST_TOKENS)


def _opens_save_dialog(candidate: dict[str, Any]) -> bool:
    next_state = candidate.get("next_state")
    if isinstance(next_state, dict) and next_state.get("save_dialog_open") is True:
        return True
    candidate_id = candidate.get("candidate_id")
    if isinstance(candidate_id, str) and "save_as" in candidate_id.lower():
        return True
    label = candidate.get("label")
    if isinstance(label, str) and label.strip():
        tokens = _label_tokens(label)
        if "save" in tokens and "as" in tokens:
            return True
    return False


def _filter_save_dialog_openers(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    matches = [candidate for candidate in candidates if _opens_save_dialog(candidate)]
    return matches or candidates


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
    label_counts: dict[str, int] = {}
    for candidate in candidates:
        label = candidate.get("label")
        if isinstance(label, str) and label.strip():
            label = label.strip()
            label_counts[label] = label_counts.get(label, 0) + 1

    if not any(count > 1 for count in label_counts.values()):
        return candidates

    best_by_label: dict[str, dict[str, Any]] = {}
    best_score: dict[str, tuple[float, float, float]] = {}
    tie_counts: dict[str, int] = {}
    labels_with_bbox: set[str] = set()
    ambiguous_labels: set[str] = set()

    for candidate in candidates:
        label = candidate.get("label")
        if not isinstance(label, str) or not label.strip():
            continue
        label = label.strip()
        if label_counts.get(label, 0) < 2:
            continue
        bbox = candidate.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            ambiguous_labels.add(label)
            continue
        x, y, width, height = bbox
        if not all(isinstance(v, (int, float)) for v in (x, y, width, height)):
            ambiguous_labels.add(label)
            continue
        area = float(width) * float(height)
        score = (area, float(y), float(x))
        labels_with_bbox.add(label)
        if label not in best_by_label or score < best_score.get(label, (float("inf"),) * 3):
            best_by_label[label] = candidate
            best_score[label] = score
            tie_counts[label] = 1
            continue
        if score == best_score.get(label):
            tie_counts[label] = tie_counts.get(label, 1) + 1

    for label, count in tie_counts.items():
        if count > 1:
            ambiguous_labels.add(label)

    if ambiguous_labels:
        return []

    if not labels_with_bbox:
        return []

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
    if not filtered:
        return []
    if len(filtered) == len(candidates):
        return filtered
    for label, count in label_counts.items():
        if count > 1:
            remaining = sum(
                1
                for candidate in filtered
                if isinstance(candidate.get("label"), str)
                and candidate.get("label", "").strip() == label
            )
            if remaining > 1:
                return []
    return filtered


def _label_token_richness(candidate: dict[str, Any]) -> int:
    label = candidate.get("label")
    if not isinstance(label, str) or not label.strip():
        return 0
    tokens = [
        token
        for token in _tokenize_text(label)
        if token and token not in LABEL_KEYWORD_STOPWORDS
    ]
    return len(tokens)


def _filter_by_label_richness(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    scored: list[tuple[dict[str, Any], int]] = []
    for candidate in candidates:
        scored.append((candidate, _label_token_richness(candidate)))
    if not scored:
        return candidates
    max_score = max(score for _, score in scored)
    if max_score <= 0:
        return candidates
    filtered = [candidate for candidate, score in scored if score == max_score]
    return filtered or candidates


def _filter_overlay_confirmation(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    overlay_candidates = [candidate for candidate in candidates if _is_overlay_candidate(candidate)]
    if not overlay_candidates or len(overlay_candidates) == len(candidates):
        return candidates
    matches: list[dict[str, Any]] = []
    for candidate in overlay_candidates:
        label = candidate.get("label")
        if not isinstance(label, str) or not label.strip():
            continue
        tokens = _label_tokens(label)
        if any(token in OVERLAY_CONFIRM_TOKENS for token in tokens):
            matches.append(candidate)
    if matches:
        return matches
    return candidates


def _candidate_opens_required_modal(candidate: dict[str, Any]) -> bool:
    next_state = candidate.get("next_state")
    if isinstance(next_state, dict) and next_state.get("modal_required") is True:
        return True
    return False


def _candidate_advances_state(candidate: dict[str, Any]) -> bool:
    next_state = candidate.get("next_state")
    if not isinstance(next_state, dict):
        return False
    for key in STATE_ADVANCE_KEYS:
        if next_state.get(key) is True:
            return True
    return False


def _filter_overlay_advances_state(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    overlay_candidates = [candidate for candidate in candidates if _is_overlay_candidate(candidate)]
    if not overlay_candidates or len(overlay_candidates) == len(candidates):
        return candidates
    matches = [candidate for candidate in overlay_candidates if _candidate_advances_state(candidate)]
    return matches or candidates


def _filter_required_modal_openers(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    matches = [candidate for candidate in candidates if _candidate_opens_required_modal(candidate)]
    return matches or candidates


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

    wants_primary = "primary" in text
    wants_secondary = "secondary" in text

    wants_bottom = _has_any(text, ("bottom", "lower"))
    wants_top = _has_any(text, ("top", "upper"))
    wants_left = _has_any(text, ("left", "leftmost"))
    wants_right = _has_any(text, ("right", "rightmost"))

    allow_overlay = allow_overlay_from_row(row)
    allow_modal = wants_modal or wants_overlay
    overlay_allowed = allow_overlay or wants_overlay or wants_modal

    if apply_rules and not allow_modal:
        candidates = _filter_main_scope(candidates)

    if apply_rules and wants_modal:
        candidates = _filter_modal_scope(candidates, require_modal=True)

    if apply_rules:
        candidates = _filter_actionable(candidates)

    label_hint = False
    if apply_rules and allow_overlay and not wants_overlay:
        advanced = _filter_overlay_advances_state(candidates)
        if len(advanced) != len(candidates):
            candidates = advanced
            label_hint = True
    if apply_rules:
        candidates, label_token = _filter_by_label_keywords(candidates, instruction)
        label_hint = label_hint or (label_token is not None)
        role_hint = _desired_role_from_instruction(instruction)
        if role_hint:
            candidates = _filter_by_role(candidates, role_hint)
        if not label_hint and _instruction_needs_save_dialog(instruction):
            save_filtered = _filter_save_dialog_openers(candidates)
            if len(save_filtered) != len(candidates):
                candidates = save_filtered
                label_hint = True
        if not label_hint and allow_overlay:
            modal_required_filtered = _filter_required_modal_openers(candidates)
            if len(modal_required_filtered) != len(candidates):
                candidates = modal_required_filtered
                label_hint = True
    if apply_rules and not label_hint and wants_primary:
        candidates = _filter_by_candidate_id(candidates, token="primary")
    if apply_rules and not label_hint and wants_secondary:
        candidates = _filter_by_candidate_id(candidates, token="secondary")
    if apply_rules and not label_hint and (wants_primary or wants_secondary):
        candidates = _filter_by_label_richness(candidates)
    if apply_rules and not label_hint and allow_overlay and not wants_overlay:
        candidates = _filter_overlay_clears_modal(candidates)
    if apply_rules and not label_hint and allow_overlay and not wants_overlay:
        candidates = _filter_overlay_opens_modal(candidates)
    if apply_rules and not label_hint and allow_overlay and not wants_overlay:
        candidates = _filter_overlay_confirmation(candidates)

    if apply_rules and not wants_overlay and not overlay_allowed:
        candidates = _filter_non_overlay(candidates)
    if apply_rules and not wants_overlay and apply_overlay_filter and not overlay_allowed:
        candidates = filter_overlay_candidates(candidates)

    if apply_rules and wants_overlay:
        overlay_only = [candidate for candidate in candidates if _is_overlay_candidate(candidate)]
        if overlay_only:
            candidates = overlay_only

    if apply_rules and not label_hint and wants_bottom:
        candidates = _filter_by_bbox(candidates, axis=1, pick_max=True)
    if apply_rules and not label_hint and wants_top:
        candidates = _filter_by_bbox(candidates, axis=1, pick_max=False)
    if apply_rules and not label_hint and wants_left:
        candidates = _filter_by_bbox(candidates, axis=0, pick_max=False)
    if apply_rules and not label_hint and wants_right:
        candidates = _filter_by_bbox(candidates, axis=0, pick_max=True)

    if not label_hint:
        candidates = tie_break_same_label_candidates(candidates)
    return candidates


def _candidate_ids(candidates: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for candidate in candidates:
        candidate_id = candidate.get("candidate_id")
        if isinstance(candidate_id, str):
            ids.append(candidate_id)
    return ids


def _record_removed(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
    reason: str,
    reasons: dict[str, list[str]],
) -> None:
    before_ids = {candidate.get("candidate_id") for candidate in before if isinstance(candidate, dict)}
    after_ids = {candidate.get("candidate_id") for candidate in after if isinstance(candidate, dict)}
    for candidate in before:
        candidate_id = candidate.get("candidate_id")
        if not isinstance(candidate_id, str):
            continue
        if candidate_id in before_ids and candidate_id not in after_ids:
            reasons.setdefault(candidate_id, []).append(reason)


def preselect_candidates_with_trace(
    row: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    apply_overlay_filter: bool,
    apply_rules: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    instruction = extract_ui_instruction(row)
    text = instruction.lower()

    neg_overlay = _has_negated(text, "popup") or _has_negated(text, "overlay")
    wants_overlay = _has_any(text, ("popup", "overlay")) and not neg_overlay
    neg_modal = _has_negated(text, "modal") or _has_negated(text, "dialog")
    wants_modal = _has_any(text, ("modal", "dialog")) and not neg_modal

    wants_primary = "primary" in text
    wants_secondary = "secondary" in text

    wants_bottom = _has_any(text, ("bottom", "lower"))
    wants_top = _has_any(text, ("top", "upper"))
    wants_left = _has_any(text, ("left", "leftmost"))
    wants_right = _has_any(text, ("right", "rightmost"))

    allow_overlay = allow_overlay_from_row(row)
    allow_modal = wants_modal or wants_overlay
    overlay_allowed = allow_overlay or wants_overlay or wants_modal

    trace: dict[str, Any] = {
        "row_id": row.get("id"),
        "task_id": row.get("task_id"),
        "instruction": instruction,
        "candidates_in": _candidate_ids(candidates),
        "after_overlay_filter": None,
        "after_rules": None,
        "final_choice": None,
        "reasons": {},
    }
    reasons: dict[str, list[str]] = {}
    current = list(candidates)

    if apply_rules and not allow_modal:
        filtered = _filter_main_scope(current)
        _record_removed(current, filtered, "modal_scope_not_main", reasons)
        current = filtered

    if apply_rules and wants_modal:
        filtered = _filter_modal_scope(current, require_modal=True)
        _record_removed(current, filtered, "modal_scope_required", reasons)
        current = filtered

    if apply_rules:
        filtered = _filter_actionable(current)
        _record_removed(current, filtered, "not_actionable", reasons)
        current = filtered

    label_hint = False
    if apply_rules and allow_overlay and not wants_overlay:
        filtered = _filter_overlay_advances_state(current)
        if len(filtered) != len(current):
            _record_removed(current, filtered, "overlay_advances_state", reasons)
            label_hint = True
        current = filtered
    if apply_rules:
        filtered, token = _filter_by_label_keywords(current, instruction)
        if token:
            _record_removed(current, filtered, f"label_keyword_mismatch:{token}", reasons)
            label_hint = True
        current = filtered
        role_hint = _desired_role_from_instruction(instruction)
        if role_hint:
            filtered = _filter_by_role(current, role_hint)
            _record_removed(current, filtered, f"role_mismatch:{role_hint}", reasons)
            current = filtered
        if not label_hint and _instruction_needs_save_dialog(instruction):
            filtered = _filter_save_dialog_openers(current)
            if len(filtered) != len(current):
                _record_removed(current, filtered, "save_dialog_required", reasons)
                label_hint = True
            current = filtered
        if not label_hint and allow_overlay:
            filtered = _filter_required_modal_openers(current)
            if len(filtered) != len(current):
                _record_removed(current, filtered, "modal_required", reasons)
                label_hint = True
            current = filtered
    if apply_rules and not label_hint and wants_primary:
        filtered = _filter_by_candidate_id(current, token="primary")
        _record_removed(current, filtered, "not_primary", reasons)
        current = filtered
    if apply_rules and not label_hint and wants_secondary:
        filtered = _filter_by_candidate_id(current, token="secondary")
        _record_removed(current, filtered, "not_secondary", reasons)
        current = filtered
    if apply_rules and not label_hint and (wants_primary or wants_secondary):
        filtered = _filter_by_label_richness(current)
        _record_removed(current, filtered, "label_richness", reasons)
        current = filtered
    if apply_rules and not label_hint and allow_overlay and not wants_overlay:
        filtered = _filter_overlay_clears_modal(current)
        _record_removed(current, filtered, "overlay_clears_modal", reasons)
        current = filtered
    if apply_rules and not label_hint and allow_overlay and not wants_overlay:
        filtered = _filter_overlay_opens_modal(current)
        _record_removed(current, filtered, "overlay_opens_modal", reasons)
        current = filtered
    if apply_rules and not label_hint and allow_overlay and not wants_overlay:
        filtered = _filter_overlay_confirmation(current)
        _record_removed(current, filtered, "overlay_confirmation_preferred", reasons)
        current = filtered

    if apply_rules and not wants_overlay and not overlay_allowed:
        filtered = _filter_non_overlay(current)
        _record_removed(current, filtered, "overlay_present", reasons)
        current = filtered

    if apply_rules and not wants_overlay and apply_overlay_filter and not overlay_allowed:
        filtered = filter_overlay_candidates(current)
        _record_removed(current, filtered, "overlay_filtered", reasons)
        current = filtered

    if apply_rules and wants_overlay:
        overlay_only = [candidate for candidate in current if _is_overlay_candidate(candidate)]
        if overlay_only:
            _record_removed(current, overlay_only, "overlay_required", reasons)
            current = overlay_only

    trace["after_overlay_filter"] = _candidate_ids(current)

    if apply_rules and not label_hint and wants_bottom:
        filtered = _filter_by_bbox(current, axis=1, pick_max=True)
        _record_removed(current, filtered, "bbox_bottom", reasons)
        current = filtered
    if apply_rules and not label_hint and wants_top:
        filtered = _filter_by_bbox(current, axis=1, pick_max=False)
        _record_removed(current, filtered, "bbox_top", reasons)
        current = filtered
    if apply_rules and not label_hint and wants_left:
        filtered = _filter_by_bbox(current, axis=0, pick_max=False)
        _record_removed(current, filtered, "bbox_left", reasons)
        current = filtered
    if apply_rules and not label_hint and wants_right:
        filtered = _filter_by_bbox(current, axis=0, pick_max=True)
        _record_removed(current, filtered, "bbox_right", reasons)
        current = filtered

    if not label_hint:
        before_tie = current
        current = tie_break_same_label_candidates(current)
        if not current and before_tie:
            for candidate in before_tie:
                candidate_id = candidate.get("candidate_id")
                if isinstance(candidate_id, str):
                    reasons.setdefault(candidate_id, []).append("ambiguous_duplicate")
        else:
            _record_removed(before_tie, current, "tie_break", reasons)

    trace["after_rules"] = _candidate_ids(current)
    trace["reasons"] = reasons
    return current, trace
