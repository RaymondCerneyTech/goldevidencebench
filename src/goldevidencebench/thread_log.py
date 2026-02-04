from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1"


def _iso_timestamp(ts: datetime | None = None) -> str:
    now = ts or datetime.now(timezone.utc)
    return now.isoformat()


def build_event(
    *,
    run_id: str | None,
    step: int,
    event_type: str,
    why_type: str | None = None,
    inputs_ref: str | None = None,
    outputs_ref: str | None = None,
    notes: str | None = None,
    case_id: str | None = None,
    step_id: int | None = None,
    candidate_id: str | None = None,
    selected_id: str | None = None,
    gold_id: str | None = None,
    ts: datetime | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "ts": _iso_timestamp(ts),
        "run_id": run_id,
        "step": int(step),
        "type": event_type,
        "why_type": why_type,
        "inputs_ref": inputs_ref,
        "outputs_ref": outputs_ref,
        "notes": notes,
        "case_id": case_id,
        "step_id": step_id,
        "candidate_id": candidate_id,
        "selected_id": selected_id,
        "gold_id": gold_id,
    }


def append_event(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(event, ensure_ascii=True))
        f.write("\n")
