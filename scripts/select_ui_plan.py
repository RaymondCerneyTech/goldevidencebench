from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from goldevidencebench.model_runner import load_adapter
from goldevidencebench.util import read_jsonl


def _candidate_by_id(row: dict[str, Any], candidate_id: str | None) -> dict[str, Any] | None:
    if candidate_id is None:
        return None
    candidates = row.get("candidates", [])
    if not isinstance(candidates, list):
        return None
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if candidate.get("candidate_id") == candidate_id:
            return candidate
    return None


def _load_rows(path: Path, task_id: str) -> list[dict[str, Any]]:
    rows = [row for row in read_jsonl(path) if isinstance(row, dict)]
    filtered = [row for row in rows if row.get("task_id") == task_id]
    if not filtered:
        raise ValueError(f"No rows found for task_id={task_id}")
    filtered.sort(key=lambda row: int(row.get("step_index", 0)))
    return filtered


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Select a UI action plan using the UI adapter."
    )
    parser.add_argument(
        "--fixture",
        required=True,
        help="Path to a UI fixture JSONL file.",
    )
    parser.add_argument(
        "--task-id",
        required=True,
        help="task_id to select rows for.",
    )
    parser.add_argument(
        "--adapter",
        default="goldevidencebench.adapters.ui_llama_cpp_adapter:create_adapter",
        help="UI adapter factory path.",
    )
    parser.add_argument(
        "--model",
        default="",
        help="Optional model path (sets GOLDEVIDENCEBENCH_MODEL).",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Output JSON path for the selected plan.",
    )
    args = parser.parse_args()

    if args.model:
        os.environ["GOLDEVIDENCEBENCH_MODEL"] = args.model

    fixture_path = Path(args.fixture)
    if not fixture_path.exists():
        raise FileNotFoundError(f"Fixture not found: {fixture_path}")

    rows = _load_rows(fixture_path, args.task_id)
    adapter = load_adapter(args.adapter)

    steps: list[dict[str, Any]] = []
    for row in rows:
        pred = adapter.predict(row, protocol="ui")
        value = pred.get("value")
        selected_id = value if isinstance(value, str) and value.strip() else None
        selected = _candidate_by_id(row, selected_id)
        steps.append(
            {
                "row_id": row.get("id"),
                "step_index": row.get("step_index"),
                "instruction": row.get("instruction"),
                "selected_id": selected_id,
                "action_type": selected.get("action_type") if selected else None,
                "label": selected.get("label") if selected else None,
            }
        )

    payload = {
        "fixture": str(fixture_path),
        "task_id": args.task_id,
        "steps": steps,
    }
    out_path = Path(args.out)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
