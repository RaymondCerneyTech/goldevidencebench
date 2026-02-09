from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from goldevidencebench.util import read_jsonl


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Score compression_loss_bounded runs using precision/recall/F1, "
            "bloat, exact compact-state match, and parse rate."
        )
    )
    parser.add_argument("--data", required=True, type=Path, help="Fixture JSONL path.")
    parser.add_argument("--preds", required=True, type=Path, help="Predictions JSONL path.")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Summary output path (default: <preds_dir>/compression_loss_bounded_summary.json).",
    )
    parser.add_argument(
        "--rows-out",
        type=Path,
        default=None,
        help="Optional per-row diagnostics JSONL.",
    )
    parser.add_argument("--min-precision", type=float, default=None)
    parser.add_argument("--min-recall", type=float, default=None)
    parser.add_argument("--min-f1", type=float, default=None)
    parser.add_argument("--max-bloat", type=float, default=None)
    return parser.parse_args()


def _norm_scalar(value: Any) -> str:
    if value is None:
        return "null"
    text = str(value).strip().lower()
    return text


def _state_to_pairs(state: dict[str, Any]) -> set[str]:
    pairs: set[str] = set()
    for key, value in state.items():
        key_text = str(key).strip()
        if not key_text:
            continue
        pairs.add(f"{key_text}={_norm_scalar(value)}")
    return pairs


def _f1(precision: float, recall: float) -> float:
    if precision <= 0.0 or recall <= 0.0:
        return 0.0
    return (2.0 * precision * recall) / (precision + recall)


def _extract_json_blob(text: str) -> str | None:
    if "{" not in text or "}" not in text:
        return None
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    return match.group(0)


def _parse_state(candidate: Any) -> tuple[dict[str, Any], bool]:
    if isinstance(candidate, dict):
        compact = candidate.get("compact_state")
        if isinstance(compact, dict):
            return compact, True
        if all(not isinstance(v, (dict, list)) for v in candidate.values()):
            return candidate, True
        return {}, False

    if isinstance(candidate, str):
        text = candidate.strip()
        if not text:
            return {}, False
        payload: Any = None
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            blob = _extract_json_blob(text)
            if blob is None:
                return {}, False
            try:
                payload = json.loads(blob)
            except json.JSONDecodeError:
                return {}, False
        return _parse_state(payload)

    return {}, False


def _gold_state(row: dict[str, Any]) -> dict[str, Any]:
    gold = row.get("gold")
    if not isinstance(gold, dict):
        return {}
    compact = gold.get("compact_state")
    if isinstance(compact, dict):
        return compact
    value = gold.get("value")
    parsed, ok = _parse_state(value)
    return parsed if ok else {}


def _pred_state(row: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    for key in ("compact_state", "value", "answer", "text"):
        parsed, ok = _parse_state(row.get(key))
        if ok:
            return parsed, True
    return {}, False


def _mean(values: list[float]) -> float:
    return (sum(values) / len(values)) if values else 0.0


def _check_thresholds(summary: dict[str, Any], args: argparse.Namespace) -> list[str]:
    means = summary.get("means", {})
    failures: list[str] = []

    def _check_min(name: str, threshold: float | None) -> None:
        if threshold is None:
            return
        value = means.get(name)
        if not isinstance(value, (int, float)) or float(value) < threshold:
            failures.append(f"{name} < {threshold}")

    def _check_max(name: str, threshold: float | None) -> None:
        if threshold is None:
            return
        value = means.get(name)
        if not isinstance(value, (int, float)) or float(value) > threshold:
            failures.append(f"{name} > {threshold}")

    _check_min("precision", args.min_precision)
    _check_min("recall", args.min_recall)
    _check_min("f1", args.min_f1)
    _check_max("bloat", args.max_bloat)
    return failures


def main() -> int:
    args = _parse_args()
    out_path = args.out or (args.preds.parent / "compression_loss_bounded_summary.json")

    data_rows = [row for row in read_jsonl(args.data) if isinstance(row, dict)]
    pred_rows = [row for row in read_jsonl(args.preds) if isinstance(row, dict)]
    preds_by_id = {str(row.get("id")): row for row in pred_rows if row.get("id") is not None}

    row_diags: list[dict[str, Any]] = []
    precisions: list[float] = []
    recalls: list[float] = []
    f1s: list[float] = []
    bloats: list[float] = []
    exacts: list[float] = []
    parses: list[float] = []

    for data_row in data_rows:
        rid = str(data_row.get("id"))
        pred_row = preds_by_id.get(rid, {})
        gold_state = _gold_state(data_row)
        pred_state, parse_ok = _pred_state(pred_row)

        gold_pairs = _state_to_pairs(gold_state)
        pred_pairs = _state_to_pairs(pred_state) if parse_ok else set()
        inter = len(gold_pairs & pred_pairs)
        pred_n = len(pred_pairs)
        gold_n = len(gold_pairs)

        precision = (inter / pred_n) if pred_n else (1.0 if gold_n == 0 else 0.0)
        recall = (inter / gold_n) if gold_n else 1.0
        f1 = _f1(precision, recall)
        excess = max(pred_n - gold_n, 0)
        bloat = (excess / (gold_n if gold_n > 0 else 1))
        exact = 1.0 if parse_ok and pred_pairs == gold_pairs else 0.0

        precisions.append(precision)
        recalls.append(recall)
        f1s.append(f1)
        bloats.append(bloat)
        exacts.append(exact)
        parses.append(1.0 if parse_ok else 0.0)

        row_diags.append(
            {
                "id": rid,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "bloat": bloat,
                "exact_match": bool(exact),
                "parse_ok": bool(parse_ok),
                "gold_pairs": sorted(gold_pairs),
                "pred_pairs": sorted(pred_pairs),
            }
        )

    summary: dict[str, Any] = {
        "benchmark": "compression_loss_bounded",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_path": str(args.data),
        "preds_path": str(args.preds),
        "rows_total": len(data_rows),
        "rows_scored": len(row_diags),
        "means": {
            "precision": _mean(precisions),
            "recall": _mean(recalls),
            "f1": _mean(f1s),
            "bloat": _mean(bloats),
            "exact_match_rate": _mean(exacts),
            "parse_rate": _mean(parses),
        },
    }

    thresholds: dict[str, float] = {}
    if args.min_precision is not None:
        thresholds["min_precision"] = args.min_precision
    if args.min_recall is not None:
        thresholds["min_recall"] = args.min_recall
    if args.min_f1 is not None:
        thresholds["min_f1"] = args.min_f1
    if args.max_bloat is not None:
        thresholds["max_bloat"] = args.max_bloat
    if thresholds:
        summary["thresholds"] = thresholds

    failures = _check_thresholds(summary, args)
    summary["failures"] = failures
    summary["status"] = "PASS" if not failures else "FAIL"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")
    print(
        "compression_loss_bounded:"
        f" n={summary['rows_scored']}"
        f" precision={summary['means']['precision']:.3f}"
        f" recall={summary['means']['recall']:.3f}"
        f" f1={summary['means']['f1']:.3f}"
        f" bloat={summary['means']['bloat']:.3f}"
        f" parse_rate={summary['means']['parse_rate']:.3f}"
        f" status={summary['status']}"
    )

    if args.rows_out is not None:
        args.rows_out.parent.mkdir(parents=True, exist_ok=True)
        with args.rows_out.open("w", encoding="utf-8", newline="\n") as handle:
            for row in row_diags:
                handle.write(json.dumps(row, ensure_ascii=True) + "\n")
        print(f"Wrote {args.rows_out}")

    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
