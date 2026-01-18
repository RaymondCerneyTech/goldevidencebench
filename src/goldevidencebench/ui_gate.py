from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from goldevidencebench.ui_prompt import extract_ui_instruction
from goldevidencebench.ui_policy import LABEL_KEYWORD_STOPWORDS, LABEL_KEYWORD_SYNONYMS


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


def _instruction_tokens(instruction: str) -> list[str]:
    tokens = [
        token
        for token in _tokenize_text(instruction)
        if token and token not in LABEL_KEYWORD_STOPWORDS
    ]
    expanded: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        for candidate in (token, *LABEL_KEYWORD_SYNONYMS.get(token, ())):
            if candidate in seen:
                continue
            expanded.append(candidate)
            seen.add(candidate)
    return expanded


def _label_tokens(candidate: dict[str, Any]) -> set[str]:
    tokens: set[str] = set()
    label = candidate.get("label")
    if isinstance(label, str) and label.strip():
        tokens.update(_tokenize_text(label))
    accessible_name = candidate.get("accessible_name")
    if isinstance(accessible_name, str) and accessible_name.strip():
        tokens.update(_tokenize_text(accessible_name))
    return tokens


def _app_path_tokens(candidate: dict[str, Any]) -> set[str]:
    tokens: set[str] = set()
    app_path = candidate.get("app_path")
    if isinstance(app_path, str) and app_path.strip():
        tokens.update(_tokenize_text(app_path))
    return tokens


def _next_state(candidate: dict[str, Any]) -> dict[str, Any]:
    state = candidate.get("next_state")
    if isinstance(state, dict):
        return state
    return {}


def _token_matches(instruction_token: str, label_token: str) -> bool:
    if instruction_token == label_token:
        return True
    if len(instruction_token) < 4 or len(label_token) < 4:
        return False
    return instruction_token.startswith(label_token) or label_token.startswith(instruction_token)


def _label_match_count(instruction_tokens: list[str], label_tokens: set[str]) -> int:
    if not instruction_tokens or not label_tokens:
        return 0
    count = 0
    for instruction_token in instruction_tokens:
        if any(_token_matches(instruction_token, label_token) for label_token in label_tokens):
            count += 1
    return count


def extract_gate_features(row: dict[str, Any], candidate: dict[str, Any]) -> dict[str, float]:
    instruction = extract_ui_instruction(row)
    instruction_tokens = _instruction_tokens(instruction)
    label_tokens = _label_tokens(candidate)
    app_path_tokens = _app_path_tokens(candidate)
    next_state = _next_state(candidate)
    next_modal_scope = next_state.get("modal_scope")
    next_location = next_state.get("location")
    next_overlay = next_state.get("overlay_present")
    if next_overlay is None and "overlay" in next_state:
        next_overlay = next_state.get("overlay")
    label_match_count = _label_match_count(instruction_tokens, label_tokens)
    app_path_match_count = _label_match_count(instruction_tokens, app_path_tokens)
    modal_scope = candidate.get("modal_scope")
    role = candidate.get("role")
    role_is_button = 1.0 if role == "button" else 0.0
    role_is_menuitem = 1.0 if role == "menuitem" else 0.0
    instr_has_menu = "menu" in instruction_tokens
    instr_has_toolbar = "toolbar" in instruction_tokens
    candidate_overlay = candidate.get("overlay")
    if candidate_overlay is None:
        candidate_overlay = candidate.get("overlay_present")

    return {
        "bias": 1.0,
        "label_match_any": 1.0 if label_match_count else 0.0,
        "label_match_count": float(label_match_count),
        "app_path_match_any": 1.0 if app_path_match_count else 0.0,
        "app_path_match_count": float(app_path_match_count),
        "label_has_apply": 1.0 if "apply" in label_tokens else 0.0,
        "label_has_ok": 1.0 if "ok" in label_tokens or "okay" in label_tokens else 0.0,
        "label_has_confirm": 1.0 if "confirm" in label_tokens else 0.0,
        "label_has_save": 1.0 if "save" in label_tokens else 0.0,
        "label_has_finish": 1.0 if "finish" in label_tokens else 0.0,
        "label_has_cancel": 1.0 if "cancel" in label_tokens else 0.0,
        "label_has_back": 1.0 if "back" in label_tokens else 0.0,
        "instr_has_apply": 1.0 if "apply" in instruction_tokens else 0.0,
        "instr_has_ok": 1.0 if "ok" in instruction_tokens or "okay" in instruction_tokens else 0.0,
        "instr_has_confirm": 1.0 if "confirm" in instruction_tokens else 0.0,
        "instr_has_save": 1.0 if "save" in instruction_tokens else 0.0,
        "instr_has_finish": 1.0 if "finish" in instruction_tokens else 0.0,
        "instr_has_commit": 1.0 if "commit" in instruction_tokens else 0.0,
        "instr_has_finalize": 1.0 if "finalize" in instruction_tokens else 0.0,
        "role_is_button": role_is_button,
        "role_is_menuitem": role_is_menuitem,
        "instr_toolbar_role_match": 1.0 if instr_has_toolbar and role_is_button else 0.0,
        "instr_menu_role_match": 1.0 if instr_has_menu and role_is_menuitem else 0.0,
        "enabled": 1.0 if candidate.get("enabled") is not False else 0.0,
        "visible": 1.0 if candidate.get("visible") is not False else 0.0,
        "aria_disabled": 1.0 if candidate.get("aria_disabled") is True else 0.0,
        "modal_scope_is_main": 1.0
        if modal_scope in (None, "", "main")
        else 0.0,
        "overlay_present": 1.0 if candidate.get("overlay_present") is True else 0.0,
        "overlay_flag": 1.0 if candidate_overlay is True else 0.0,
        "next_overlay_present": 1.0 if next_overlay is True else 0.0,
        "next_modal_scope_is_main": 1.0
        if next_modal_scope in (None, "", "main")
        else 0.0,
        "next_modal_scope_is_overlay": 1.0 if next_modal_scope == "overlay" else 0.0,
        "next_modal_scope_is_dialog": 1.0 if next_modal_scope == "dialog" else 0.0,
        "next_modal_scope_is_drawer": 1.0 if next_modal_scope == "drawer" else 0.0,
        "next_modal_required": 1.0 if next_state.get("modal_required") is True else 0.0,
        "next_modal_confirmed": 1.0 if next_state.get("modal_confirmed") is True else 0.0,
        "next_destructive_ready": 1.0 if next_state.get("destructive_ready") is True else 0.0,
        "next_location_toolbar": 1.0 if next_location == "toolbar" else 0.0,
        "next_location_menu": 1.0 if next_location == "menu" else 0.0,
    }


def gate_feature_names() -> list[str]:
    return list(extract_gate_features({}, {}).keys())


def build_feature_vector(
    row: dict[str, Any], candidate: dict[str, Any], feature_names: Iterable[str]
) -> list[float]:
    features = extract_gate_features(row, candidate)
    return [float(features.get(name, 0.0)) for name in feature_names]


@dataclass
class GateModel:
    feature_names: list[str]
    weights: list[float]
    bias: float = 0.0
    min_score: float = 0.5
    min_margin: float = 0.0

    def score(self, vector: list[float]) -> float:
        return _sigmoid(_dot(self.weights, vector) + self.bias)


def _dot(weights: list[float], vector: list[float]) -> float:
    return sum(w * x for w, x in zip(weights, vector, strict=False))


def _sigmoid(value: float) -> float:
    if value >= 0:
        exp = pow(2.718281828459045, -value)
        return 1.0 / (1.0 + exp)
    exp = pow(2.718281828459045, value)
    return exp / (1.0 + exp)


def train_logistic_regression(
    x_rows: list[list[float]],
    y_rows: list[int],
    *,
    lr: float = 0.1,
    epochs: int = 200,
    l2: float = 0.0,
) -> tuple[list[float], float]:
    if not x_rows:
        raise ValueError("x_rows is empty")
    dim = len(x_rows[0])
    weights = [0.0] * dim
    bias = 0.0
    for _ in range(epochs):
        for vector, y in zip(x_rows, y_rows, strict=True):
            pred = _sigmoid(_dot(weights, vector) + bias)
            error = pred - y
            for i in range(dim):
                weights[i] -= lr * (error * vector[i] + l2 * weights[i])
            bias -= lr * error
    return weights, bias


def score_candidates(
    row: dict[str, Any],
    candidates: list[dict[str, Any]],
    model: GateModel,
) -> list[tuple[dict[str, Any], float]]:
    scored: list[tuple[dict[str, Any], float]] = []
    for candidate in candidates:
        vector = build_feature_vector(row, candidate, model.feature_names)
        scored.append((candidate, model.score(vector)))
    return scored


def select_candidate(
    row: dict[str, Any],
    candidates: list[dict[str, Any]],
    model: GateModel,
) -> str | None:
    if not candidates:
        return None
    scored = score_candidates(row, candidates, model)
    scored.sort(key=lambda item: item[1], reverse=True)
    best_candidate, best_score = scored[0]
    if best_score < model.min_score:
        return None
    if len(scored) > 1:
        margin = best_score - scored[1][1]
        if margin < model.min_margin:
            return None
    return best_candidate.get("candidate_id")
