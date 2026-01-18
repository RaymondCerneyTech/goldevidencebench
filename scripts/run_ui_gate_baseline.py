from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from goldevidencebench.ui_eval import score_post_action_verification, score_ui_rows, score_ui_sequences
from goldevidencebench.ui_gate import GateModel, select_candidate
from goldevidencebench.util import read_jsonl


def _load_model(path: str | Path) -> GateModel:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return GateModel(
        feature_names=payload["feature_names"],
        weights=payload["weights"],
        bias=payload.get("bias", 0.0),
        min_score=payload.get("min_score", 0.5),
        min_margin=payload.get("min_margin", 0.0),
    )


def _load_observed_deltas(path: Path, rows: list[dict[str, Any]]) -> list[dict[str, Any] | None]:
    observed_rows = list(read_jsonl(path))
    observed_by_id: dict[str, dict[str, Any] | None] = {}
    for row in observed_rows:
        row_id = row.get("id")
        if not isinstance(row_id, str):
            continue
        observed = row.get("observed_delta")
        if isinstance(observed, dict):
            observed_by_id[row_id] = observed
    observed_deltas: list[dict[str, Any] | None] = []
    for row in rows:
        row_id = row.get("id")
        if isinstance(row_id, str):
            observed_deltas.append(observed_by_id.get(row_id))
        else:
            observed_deltas.append(None)
    return observed_deltas


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--observed")
    parser.add_argument("--model", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--min-score", type=float)
    parser.add_argument("--min-margin", type=float)
    args = parser.parse_args()

    rows = list(read_jsonl(args.fixture))
    model = _load_model(args.model)
    if args.min_score is not None:
        model.min_score = args.min_score
    if args.min_margin is not None:
        model.min_margin = args.min_margin

    selected_ids: list[str | None] = []
    for row in rows:
        candidates = row.get("candidates", [])
        if isinstance(candidates, list) and candidates:
            selected = select_candidate(row, candidates, model)
        else:
            selected = None
        selected_ids.append(selected)

    metrics = score_ui_rows(rows, selected_ids)
    observed_rows: list[dict[str, Any] | None] | None = None
    if args.observed:
        observed_rows = _load_observed_deltas(Path(args.observed), rows)
        post_verify = score_post_action_verification(rows, observed_rows)
        metrics.update(post_verify)
    sequence_metrics = score_ui_sequences(
        rows, selected_ids, observed_rows
    )

    out = {
        "rows": len(rows),
        "fixture": args.fixture,
        "model": args.model,
        "metrics": metrics,
        "sequence_metrics": sequence_metrics,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
