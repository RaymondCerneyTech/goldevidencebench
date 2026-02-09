from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from goldevidencebench.adapters.llama_prompt import (
    build_prompt,
    extract_ledger,
    ledger_key_for_row,
    truncate_tokens,
)
from goldevidencebench.baselines import parse_book_ledger
from goldevidencebench.util import get_env


class ExternalCliAdapter:
    """
    Closed-book adapter that delegates to an external CLI command.

    The command is provided via env var:
      - GOLDEVIDENCEBENCH_EXTERNAL_LLM_CMD

    The command string is templated with {placeholders}:
      - {prompt} (inline prompt text; caller must quote safely)
      - {prompt_file} (path to a temp file containing the prompt)
      - {model_path} (from GOLDEVIDENCEBENCH_MODEL or model_path)
      - {max_tokens}
      - {n_ctx}
      - {require_citations} (1/0)
    """

    def __init__(
        self,
        model_path: str | None = None,
        n_ctx: int = 2048,
        n_threads: int | None = None,
        max_book_tokens: int = 1600,
        query_sandwich: bool = False,
        cmd_template: str | None = None,
        timeout_s: float | None = None,
    ) -> None:
        _ = n_threads  # reserved for parity with LlamaCppAdapter
        self.model_path = model_path or get_env("MODEL") or ""
        if self.model_path and not Path(self.model_path).exists():
            raise FileNotFoundError(self.model_path)
        require_citations_env = (get_env("REQUIRE_CITATIONS", "1") or "1").strip().lower()
        self.require_citations = require_citations_env not in {"0", "false", "no"}
        self.n_ctx = n_ctx
        self.max_book_tokens = max_book_tokens
        self.query_sandwich = query_sandwich
        self.cmd_template = cmd_template or get_env("EXTERNAL_LLM_CMD") or ""
        if not self.cmd_template:
            raise ValueError(
                "Set GOLDEVIDENCEBENCH_EXTERNAL_LLM_CMD to a CLI template (use {prompt} or {prompt_file})."
            )
        self.timeout_s = _parse_timeout(timeout_s, get_env("EXTERNAL_LLM_TIMEOUT_S"))
        self.max_output_tokens = _parse_int(get_env("EXTERNAL_LLM_MAX_TOKENS"), default=64)
        self.normalize_support_ids = _parse_bool(get_env("NORMALIZE_SUPPORT_IDS", "1"))
        self._last_raw: dict[str, Any] | None = None

    def predict_raw_from_prompt(self, *, prompt: str, require_citations: bool) -> dict[str, Any] | None:
        text = _run_external(
            cmd_template=self.cmd_template,
            prompt=prompt,
            model_path=self.model_path,
            n_ctx=self.n_ctx,
            max_tokens=self.max_output_tokens,
            require_citations=require_citations,
            timeout_s=self.timeout_s,
        )
        parsed = _parse_json(text=text, require_citations=require_citations)
        if parsed is not None and require_citations:
            self._last_raw = {"value": parsed.get("value"), "support_ids": parsed.get("support_ids")}
        return parsed

    def predict(self, row: dict[str, Any], *, protocol: str = "closed_book") -> dict[str, Any]:
        if protocol != "closed_book":
            raise ValueError("ExternalCliAdapter supports closed_book only.")
        book = row.get("book") or row.get("artifact")
        if not book:
            raise ValueError("book/artifact required for closed_book inference.")
        ledger = extract_ledger(book, key=ledger_key_for_row(row))
        ledger = truncate_tokens(ledger, self.max_book_tokens)
        question = row["question"]
        if not self.require_citations:
            question = question.splitlines()[0]
        prompt = build_prompt(
            ledger=ledger,
            question=question,
            require_citations=self.require_citations,
            query_sandwich=self.query_sandwich,
        )
        text = _run_external(
            cmd_template=self.cmd_template,
            prompt=prompt,
            model_path=self.model_path,
            n_ctx=self.n_ctx,
            max_tokens=self.max_output_tokens,
            require_citations=self.require_citations,
            timeout_s=self.timeout_s,
        )
        parsed = _parse_json(text=text, require_citations=self.require_citations)
        if isinstance(parsed, dict):
            if not self.require_citations:
                parsed["support_ids"] = []
                parsed.pop("support_id", None)
            else:
                raw_supports = parsed.get("support_ids") or []
                if self.normalize_support_ids:
                    raw_supports = [str(s).upper() for s in raw_supports]
                self._last_raw = {"value": parsed.get("value"), "support_ids": raw_supports}
                selected = _select_support_id(book, row, parsed.get("value"))
                if selected:
                    parsed["support_ids"] = [selected]
                else:
                    parsed["support_ids"] = _filter_support_ids(book, raw_supports)
                parsed.pop("support_id", None)
            return parsed
        if not self.require_citations:
            return {"value": None, "support_ids": []}
        return {"value": None, "support_ids": [], "output": text}

    def take_perf(self) -> dict[str, Any] | None:
        return None

    def take_raw(self) -> dict[str, Any] | None:
        raw = self._last_raw
        self._last_raw = None
        return raw


def create_adapter() -> ExternalCliAdapter:
    return ExternalCliAdapter()


def _parse_int(value: str | None, *, default: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
        return parsed if parsed > 0 else default
    except ValueError:
        return default


def _parse_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() not in {"0", "false", "no"}


def _parse_timeout(explicit: float | None, env_value: str | None) -> float | None:
    if explicit is not None:
        return explicit
    if env_value is None:
        return 300.0
    value = env_value.strip().lower()
    if value in {"", "none", "null", "off", "0"}:
        return None
    try:
        parsed = float(value)
        return parsed if parsed > 0 else None
    except ValueError:
        return 300.0


def _run_external(
    *,
    cmd_template: str,
    prompt: str,
    model_path: str,
    n_ctx: int,
    max_tokens: int,
    require_citations: bool,
    timeout_s: float | None,
) -> str:
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".txt") as handle:
            handle.write(prompt)
            temp_path = handle.name
        prompt_safe = prompt.replace("{", "{{").replace("}", "}}")
        cmd = cmd_template.format(
            prompt=prompt_safe,
            prompt_file=temp_path,
            model_path=model_path,
            max_tokens=str(max_tokens),
            n_ctx=str(n_ctx),
            require_citations="1" if require_citations else "0",
        )
        env = os.environ.copy()
        env.update(
            {
                "GOLDEVIDENCEBENCH_PROMPT": prompt,
                "GOLDEVIDENCEBENCH_PROMPT_FILE": temp_path,
                "GOLDEVIDENCEBENCH_MODEL": model_path,
                "GOLDEVIDENCEBENCH_MAX_TOKENS": str(max_tokens),
                "GOLDEVIDENCEBENCH_N_CTX": str(n_ctx),
                "GOLDEVIDENCEBENCH_REQUIRE_CITATIONS": "1" if require_citations else "0",
            }
        )
        result = subprocess.run(
            cmd,
            shell=True,
            check=False,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout_s,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            raise RuntimeError(f"External LLM command failed ({result.returncode}): {stderr or cmd}")
        return result.stdout.strip()
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def _parse_json(*, text: str, require_citations: bool) -> dict[str, Any] | None:
    parsed = _loads_first_json(text)
    if not isinstance(parsed, dict):
        return None
    parsed.setdefault("value", None)
    if require_citations:
        if "support_ids" not in parsed and "support_id" in parsed:
            parsed["support_ids"] = [parsed.get("support_id")]
        if not isinstance(parsed.get("support_ids"), list):
            parsed["support_ids"] = [parsed.get("support_ids")] if parsed.get("support_ids") is not None else []
    else:
        parsed["support_ids"] = []
        parsed.pop("support_id", None)
    return parsed


def _loads_first_json(text: str) -> Any | None:
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    candidate = _extract_first_json_object(text)
    if not candidate:
        return None
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def _extract_first_json_object(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    escape = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return None


def _select_support_id(book: str, row: dict[str, Any], value: Any) -> str | None:
    key = row.get("meta", {}).get("key")
    if not key:
        return None
    entries = parse_book_ledger(book)
    ignore_notes = _is_latest_authoritative()
    last_for_key = None
    match_for_value = None
    value_str = None if value is None else str(value)
    for entry in entries:
        if ignore_notes and entry.get("op") == "NOTE":
            continue
        if entry.get("key") != key:
            continue
        last_for_key = entry
        if value_str is not None and entry.get("value") == value_str:
            match_for_value = entry
    if match_for_value:
        return match_for_value.get("uid")
    if last_for_key:
        return last_for_key.get("uid")
    return None


def _filter_support_ids(book: str, support_ids: list[Any]) -> list[str]:
    entries = parse_book_ledger(book)
    if _is_latest_authoritative():
        entries = [entry for entry in entries if entry.get("op") != "NOTE"]
    valid_ids = {entry.get("uid") for entry in entries}
    filtered: list[str] = []
    for sid in support_ids or []:
        if sid is None:
            continue
        sid_str = str(sid)
        if sid_str in valid_ids:
            filtered.append(sid_str)
    return filtered


def _is_latest_authoritative() -> bool:
    mode = (get_env("LEDGER_MODE", "latest_authoritative") or "latest_authoritative").strip().lower()
    return mode == "latest_authoritative"
