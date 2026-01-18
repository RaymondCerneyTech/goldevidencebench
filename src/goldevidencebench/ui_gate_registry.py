from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from goldevidencebench.ui_gate import GateModel


@dataclass(frozen=True)
class GateModelEntry:
    pattern: str
    path: Path
    model: GateModel


def load_gate_model(path: str | Path) -> GateModel:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return GateModel(
        feature_names=payload["feature_names"],
        weights=payload["weights"],
        bias=payload.get("bias", 0.0),
        min_score=payload.get("min_score", 0.5),
        min_margin=payload.get("min_margin", 0.0),
    )


def load_gate_model_map(path: str | Path) -> list[GateModelEntry]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    entries: list[GateModelEntry] = []
    if isinstance(payload, dict):
        items: Iterable[tuple[str, Any]] = payload.items()
    elif isinstance(payload, list):
        items = []
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            pattern = entry.get("pattern") or entry.get("match") or entry.get("name")
            model_path = entry.get("path") or entry.get("model")
            if isinstance(pattern, str) and isinstance(model_path, str):
                items.append((pattern, model_path))
    else:
        raise ValueError("UI gate model map must be a JSON object or list.")

    for pattern, model_path in items:
        if not isinstance(pattern, str) or not isinstance(model_path, str):
            continue
        model_file = Path(model_path)
        entries.append(
            GateModelEntry(
                pattern=pattern,
                path=model_file,
                model=load_gate_model(model_file),
            )
        )
    entries.sort(key=lambda entry: len(entry.pattern), reverse=True)
    return entries


def match_gate_model(
    row: dict[str, Any],
    candidates: list[dict[str, Any]],
    entries: list[GateModelEntry],
) -> GateModelEntry | None:
    if not entries:
        return None
    text = _gate_match_text(row, candidates)
    for entry in entries:
        if entry.pattern.lower() in text:
            return entry
    return None


def _gate_match_text(row: dict[str, Any], candidates: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for key in ("instruction", "goal", "question", "task_id", "id", "app_path"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value)
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        for key in ("label", "accessible_name", "app_path", "role"):
            value = candidate.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(value)
    return " ".join(parts).lower()
