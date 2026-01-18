from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from goldevidencebench.ui_gate import (
    GateModel,
    build_feature_vector,
    gate_feature_names,
    train_logistic_regression,
)
from goldevidencebench.util import read_jsonl, write_jsonl


def _build_dataset(rows: list[dict[str, Any]], feature_names: list[str]) -> tuple[list[list[float]], list[int]]:
    x_rows: list[list[float]] = []
    y_rows: list[int] = []
    for row in rows:
        gold = row.get("gold", {})
        gold_id = gold.get("candidate_id") if isinstance(gold, dict) else None
        candidates = row.get("candidates", [])
        for candidate in candidates:
            candidate_id = candidate.get("candidate_id")
            y = 1 if candidate_id == gold_id else 0
            x_rows.append(build_feature_vector(row, candidate, feature_names))
            y_rows.append(y)
    return x_rows, y_rows


def _training_metrics(rows: list[dict[str, Any]], model: GateModel) -> dict[str, float]:
    total = len(rows)
    correct = 0
    abstain = 0
    for row in rows:
        candidates = row.get("candidates", [])
        selected = None
        if isinstance(candidates, list) and candidates:
            selected = model_select(row, candidates, model)
        if selected is None:
            abstain += 1
            continue
        gold = row.get("gold", {})
        gold_id = gold.get("candidate_id") if isinstance(gold, dict) else None
        if selected == gold_id:
            correct += 1
    return {
        "selection_rate": (correct / total) if total else 0.0,
        "abstain_rate": (abstain / total) if total else 0.0,
    }


def model_select(
    row: dict[str, Any],
    candidates: list[dict[str, Any]],
    model: GateModel,
) -> str | None:
    from goldevidencebench.ui_gate import select_candidate

    return select_candidate(row, candidates, model)


def _emit_preferences(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prefs: list[dict[str, Any]] = []
    for row in rows:
        row_id = row.get("id")
        gold = row.get("gold", {})
        gold_id = gold.get("candidate_id") if isinstance(gold, dict) else None
        if not gold_id:
            continue
        for candidate in row.get("candidates", []):
            candidate_id = candidate.get("candidate_id")
            if candidate_id == gold_id:
                continue
            prefs.append(
                {
                    "row_id": row_id,
                    "better": gold_id,
                    "worse": candidate_id,
                    "reason": "gold_vs_non_gold",
                }
            )
    return prefs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--observed")
    parser.add_argument("--out-model", required=True)
    parser.add_argument("--out-prefs")
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--lr", type=float, default=0.1)
    parser.add_argument("--l2", type=float, default=0.0)
    parser.add_argument("--min-score", type=float, default=0.5)
    parser.add_argument("--min-margin", type=float, default=0.0)
    args = parser.parse_args()

    rows = list(read_jsonl(args.fixture))
    feature_names = gate_feature_names()
    x_rows, y_rows = _build_dataset(rows, feature_names)
    weights, bias = train_logistic_regression(
        x_rows,
        y_rows,
        lr=args.lr,
        epochs=args.epochs,
        l2=args.l2,
    )
    model = GateModel(
        feature_names=feature_names,
        weights=weights,
        bias=bias,
        min_score=args.min_score,
        min_margin=args.min_margin,
    )
    out_model = Path(args.out_model)
    out_model.parent.mkdir(parents=True, exist_ok=True)
    out_model.write_text(
        json.dumps(
            {
                "feature_names": model.feature_names,
                "weights": model.weights,
                "bias": model.bias,
                "min_score": model.min_score,
                "min_margin": model.min_margin,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    metrics = _training_metrics(rows, model)
    print(json.dumps({"rows": len(rows), "metrics": metrics}, indent=2))

    if args.out_prefs:
        prefs = _emit_preferences(rows)
        write_jsonl(args.out_prefs, prefs)
        print(f"Wrote preferences: {args.out_prefs}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
