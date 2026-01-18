from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

try:
    from llama_cpp import Llama, LlamaGrammar
except ImportError as exc:  # pragma: no cover - optional dependency
    raise ImportError("llama_cpp not installed; install via `pip install llama-cpp-python`") from exc

from goldevidencebench.ui_gate import select_candidate
from goldevidencebench.ui_gate_registry import (
    GateModelEntry,
    load_gate_model,
    load_gate_model_map,
    match_gate_model,
)
from goldevidencebench.ui_policy import (
    preselect_candidates,
    preselect_candidates_with_trace,
)
from goldevidencebench.ui_prompt import build_ui_prompt
from goldevidencebench.util import get_env

UI_JSON_GRAMMAR = r"""
root   ::= ws "{" ws "\"value\"" ws ":" ws value ws "," ws "\"support_ids\"" ws ":" ws array ws "}" ws
value  ::= string | "null"
array  ::= "[" ws "]"
string ::= "\"" chars "\""
chars  ::= (char)*
char   ::= [^"\\] | escape
escape ::= "\\" ["\\/bfnrt]
ws     ::= [ \t\r\n]*
"""


class UILlamaCppAdapter:
    """
    UI adapter that selects a candidate_id using llama-cpp.
    Model path is taken from:
    - env GOLDEVIDENCEBENCH_UI_MODEL
    - or env GOLDEVIDENCEBENCH_MODEL
    - or constructor argument model_path
    """

    def __init__(
        self,
        model_path: str | None = None,
        n_ctx: int = 2048,
        n_threads: int | None = None,
        max_output_tokens: int = 64,
    ) -> None:
        model_path = model_path or get_env("UI_MODEL") or get_env("MODEL")
        if not model_path:
            raise ValueError("Set GOLDEVIDENCEBENCH_MODEL or GOLDEVIDENCEBENCH_UI_MODEL to a GGUF model path.")
        if not Path(model_path).exists():
            raise FileNotFoundError(model_path)
        self.llm = Llama(model_path=model_path, n_ctx=n_ctx, n_threads=n_threads)
        self.max_output_tokens = max_output_tokens
        self.grammar = _load_grammar(UI_JSON_GRAMMAR)
        self.filter_overlay = _env_flag("UI_OVERLAY_FILTER", default="0")
        self.preselect_rules = _env_flag("UI_PRESELECT_RULES", default="0")
        self.gate_only = _env_flag("UI_GATE_ONLY", default="0")
        self.gate_model_path = get_env("UI_GATE_MODEL")
        self.gate_models_path = get_env("UI_GATE_MODELS")
        self.gate_model = None
        self.gate_models: list[GateModelEntry] = []
        if self.gate_model_path:
            self.gate_model = load_gate_model(Path(self.gate_model_path))
        if self.gate_models_path:
            self.gate_models = load_gate_model_map(Path(self.gate_models_path))
        self.trace_path = get_env("UI_TRACE_PATH")
        self.trace_append = _env_flag("UI_TRACE_APPEND", default="0")
        if self.trace_path and not self.trace_append:
            try:
                Path(self.trace_path).unlink(missing_ok=True)
            except OSError:
                pass

    def predict(self, row: dict[str, Any], *, protocol: str = "ui") -> dict[str, Any]:
        if protocol != "ui":
            raise ValueError("UILlamaCppAdapter supports protocol='ui' only.")

        candidates = row.get("candidates")
        if not isinstance(candidates, list):
            raise ValueError("UI row must include a candidates list.")
        selected = None

        trace: dict[str, Any] | None = None
        if self.trace_path:
            candidates, trace = preselect_candidates_with_trace(
                row,
                candidates,
                apply_overlay_filter=self.filter_overlay,
                apply_rules=self.preselect_rules,
            )
        else:
            candidates = preselect_candidates(
                row,
                candidates,
                apply_overlay_filter=self.filter_overlay,
                apply_rules=self.preselect_rules,
            )
        if not candidates:
            if trace is not None:
                trace["final_choice"] = None
                _append_trace(self.trace_path, trace)
            return {"value": None, "support_ids": []}
        candidate_ids = [
            candidate.get("candidate_id")
            for candidate in candidates
            if isinstance(candidate, dict) and isinstance(candidate.get("candidate_id"), str)
        ]
        if len(candidate_ids) == 1:
            if trace is not None:
                trace["final_choice"] = candidate_ids[0]
                _append_trace(self.trace_path, trace)
            return {"value": candidate_ids[0], "support_ids": []}
        gate_selected = None
        gate_label = None
        gate_entry = None
        if self.gate_models:
            gate_entry = match_gate_model(row, candidates, self.gate_models)
            if gate_entry is not None:
                gate_label = str(gate_entry.path)
                gate_selected = select_candidate(row, candidates, gate_entry.model)
        if gate_selected is None and self.gate_model is not None:
            gate_label = str(self.gate_model_path)
            gate_selected = select_candidate(row, candidates, self.gate_model)
        if trace is not None and (gate_entry is not None or self.gate_model is not None):
            trace["gate_model"] = gate_label
            trace["gate_choice"] = gate_selected
            trace["gate_used"] = gate_selected in candidate_ids if gate_selected else False
        if gate_selected in candidate_ids:
            if trace is not None:
                trace["final_choice"] = gate_selected
                _append_trace(self.trace_path, trace)
            return {"value": gate_selected, "support_ids": []}
        if self.gate_only:
            if trace is not None:
                trace["final_choice"] = None
                _append_trace(self.trace_path, trace)
            return {"value": None, "support_ids": []}
        prompt = build_ui_prompt(row, candidates)
        text = _generate_text(self, prompt=prompt)
        parsed = _parse_json(text)
        selected = _normalize_value(parsed.get("value") if parsed else None)
        if selected not in candidate_ids:
            selected = None
        if trace is not None:
            trace["final_choice"] = selected
            _append_trace(self.trace_path, trace)
        return {"value": selected, "support_ids": []}


def create_adapter() -> UILlamaCppAdapter:
    return UILlamaCppAdapter()


def _load_grammar(grammar: str) -> LlamaGrammar | None:
    try:
        return LlamaGrammar.from_string(grammar)
    except Exception:
        return None


def _normalize_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        value = str(value)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if value else None


def _parse_json(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _env_flag(key: str, *, default: str = "0") -> bool:
    value = (get_env(key, default) or default).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _append_trace(path: str | None, trace: dict[str, Any]) -> None:
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(trace, ensure_ascii=True) + "\n")


def _generate_text(self: UILlamaCppAdapter, *, prompt: str) -> str:
    print("[goldevidencebench] ui prompt", file=sys.stderr)
    grammar = self.grammar
    if grammar is not None and hasattr(self.llm, "create_completion"):
        resp = self.llm.create_completion(
            prompt=prompt,
            max_tokens=self.max_output_tokens,
            grammar=grammar,
        )
        return resp["choices"][0]["text"]
    try:
        resp = self.llm(
            prompt,
            max_tokens=self.max_output_tokens,
            response_format={"type": "json_object"},
        )
        return resp["choices"][0]["text"]
    except TypeError:
        if hasattr(self.llm, "create_completion"):
            resp = self.llm.create_completion(
                prompt=prompt,
                max_tokens=self.max_output_tokens,
                grammar=grammar,
            )
            return resp["choices"][0]["text"]
        resp = self.llm(prompt, max_tokens=self.max_output_tokens)
        return resp["choices"][0]["text"]
