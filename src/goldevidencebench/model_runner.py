from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from goldevidencebench.baselines import parse_book_ledger, parse_updates, validate_book_artifact


class ModelAdapter(Protocol):
    def predict(self, row: dict[str, Any], *, protocol: str = "open_book") -> dict[str, Any]: ...
    # Optional: build an artifact from the episode log once per episode_id.
    def build_artifact(self, *, document: str, episode_id: str, protocol: str = "open_book") -> str: ...


def load_adapter(spec: str) -> ModelAdapter:
    """
    Load an adapter from a spec of the form 'module:factory'.
    The factory must return an object with .predict(row, protocol=...) -> {value, support_ids}.
    """
    if ":" not in spec:
        raise ValueError("adapter spec must be module:factory")
    module_name, factory_name = spec.split(":", 1)
    mod = importlib.import_module(module_name)
    factory = getattr(mod, factory_name)
    adapter = factory()
    return adapter


@dataclass(frozen=True)
class ModelResult:
    predictions: list[dict[str, Any]]
    raw_predictions: list[dict[str, Any]]
    retrieval_stats: list[dict[str, Any]]
    tokens: int
    tokens_per_q: float
    passes: int
    artifact_stats: list[dict[str, Any]]
    perf_stats: list[dict[str, Any]]


class AdapterOutput(BaseModel):
    value: str | None
    support_id: str | None = None
    support_ids: list[str] = Field(default_factory=list)

    model_config = {"extra": "forbid"}

    @field_validator("value", mode="before")
    @classmethod
    def coerce_value(cls, v):
        if v is None:
            return None
        if isinstance(v, (dict, list)):
            return json.dumps(v, ensure_ascii=True, sort_keys=True)
        if isinstance(v, (int, float, bool)):
            return str(v)
        return v

    @field_validator("support_ids", mode="before")
    @classmethod
    def coerce_support_ids(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        if not isinstance(v, list):
            raise TypeError("support_ids must be a list of strings")
        return v

    @model_validator(mode="after")
    def ensure_value(self):
        return self


def _valid_support_ids(row: dict[str, Any], protocol: str) -> set[str]:
    if protocol == "closed_book":
        entries = parse_book_ledger(row["book"])
    elif row.get("document"):
        entries = parse_updates(row["document"])
    else:
        entries = parse_book_ledger(row["book"])
    return {e["uid"] for e in entries}


def validate_adapter_output(
    *, row: dict[str, Any], raw: dict[str, Any], protocol: str, max_support_k: int
) -> dict[str, Any]:
    if "value" not in raw:
        raise ValueError("Adapter output missing 'value'")
    filtered = {k: raw.get(k) for k in ("value", "support_id", "support_ids")}
    try:
        parsed = AdapterOutput.model_validate(filtered)
    except ValidationError as e:
        raise ValueError(f"Adapter output failed validation: {e}") from e

    supports = parsed.support_ids or ([parsed.support_id] if parsed.support_id else [])
    if len(supports) > max_support_k:
        raise ValueError(f"support_ids exceeds max_support_k={max_support_k}")

    citation_mode = row.get("meta", {}).get("citation_mode")
    if citation_mode == "doc_id":
        allowed = row.get("meta", {}).get("doc_ids")
        if isinstance(allowed, list):
            allowed_set = {str(item) for item in allowed}
            for sid in supports:
                if sid not in allowed_set:
                    raise ValueError(f"support_id {sid!r} not in doc_ids")
        return {"value": parsed.value, "support_ids": supports}

    valid_ids = _valid_support_ids(row, protocol)
    for sid in supports:
        if sid not in valid_ids:
            raise ValueError(f"support_id {sid!r} not in episode updates (protocol={protocol})")

    return {"value": parsed.value, "support_ids": supports}


def run_adapter(
    *,
    data_rows: list[dict[str, Any]],
    adapter: ModelAdapter,
    protocol: str = "open_book",
    max_support_k: int = 3,
) -> ModelResult:
    preds: list[dict[str, Any]] = []
    raw_preds: list[dict[str, Any]] = []
    tokens = 0
    llm_tokens = 0
    artifact_stats: list[dict[str, Any]] = []
    perf_stats: list[dict[str, Any]] = []
    retrieval_stats: list[dict[str, Any]] = []
    # Group by episode to allow one-time artifact construction.
    by_episode: dict[str, list[dict[str, Any]]] = {}
    for row in data_rows:
        by_episode.setdefault(row["episode_id"], []).append(row)

    for episode_id, rows in by_episode.items():
        doc = rows[0]["document"]
        tokens += len(doc.split())  # one full read of the document for build phase
        artifact = None
        if hasattr(adapter, "build_artifact"):
            artifact = adapter.build_artifact(document=doc, episode_id=episode_id, protocol=protocol)
            artifact_stats.append(_artifact_report(artifact=artifact, episode_id=episode_id, source_doc=doc))

        for row in rows:
            row_for_adapter = {**row}
            if protocol == "closed_book":
                row_for_adapter["document"] = None
            if artifact is not None:
                row_for_adapter["artifact"] = artifact

            source_text = artifact or (row["document"] if protocol == "open_book" else row["book"])
            tokens += len(source_text.split())  # one pass to answer this query

            out = adapter.predict(row_for_adapter, protocol=protocol) or {}
            if hasattr(adapter, "take_perf"):
                try:
                    perf = adapter.take_perf()
                except Exception:
                    perf = None
                if perf:
                    perf_stats.append(perf)
                    total_tokens = perf.get("total_tokens") if isinstance(perf, dict) else None
                    if isinstance(total_tokens, (int, float)):
                        llm_tokens += int(total_tokens)
            if hasattr(adapter, "take_raw"):
                try:
                    raw = adapter.take_raw()
                except Exception:
                    raw = None
                if isinstance(raw, dict):
                    raw_preds.append(
                        {
                            "id": row["id"],
                            "value": raw.get("value"),
                            "support_ids": raw.get("support_ids"),
                        }
                    )
            if hasattr(adapter, "take_diag"):
                try:
                    diag = adapter.take_diag()
                except Exception:
                    diag = None
                if isinstance(diag, dict):
                    diag.setdefault("id", row.get("id"))
                    retrieval_stats.append(diag)
            validated = validate_adapter_output(row=row, raw=out, protocol=protocol, max_support_k=max_support_k)
            pid = row["id"]
            preds.append(
                {
                    "id": pid,
                    "value": validated["value"],
                    "support_id": None,
                    "support_ids": validated["support_ids"],
                }
            )

    final_tokens = llm_tokens if llm_tokens > 0 else tokens
    return ModelResult(
        predictions=preds,
        raw_predictions=raw_preds,
        retrieval_stats=retrieval_stats,
        tokens=final_tokens,
        tokens_per_q=(final_tokens / len(data_rows)) if data_rows else 0.0,
        passes=1,
        artifact_stats=artifact_stats,
        perf_stats=perf_stats,
    )


def _artifact_report(*, artifact: str | None, episode_id: str, source_doc: str) -> dict[str, Any]:
    if artifact is None:
        return {"episode_id": episode_id, "has_artifact": False}

    tokens = len(artifact.split())
    ledger = parse_book_ledger(artifact)
    # very rough glossary size (lines under Glossary)
    glossary_size = 0
    in_glossary = False
    for line in artifact.splitlines():
        if line.strip() == "## Glossary (Tags)":
            in_glossary = True
            continue
        if in_glossary and line.startswith("## "):
            break
        if in_glossary and line.startswith("- "):
            glossary_size += 1

    validation = validate_book_artifact(artifact)
    return {
        "episode_id": episode_id,
        "has_artifact": True,
        "tokens": tokens,
        "ledger_entries": len(ledger),
        "glossary_entries": glossary_size,
        "leak_check": validation["ok"],
    }
