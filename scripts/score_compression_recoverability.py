from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from goldevidencebench.util import read_jsonl


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Score compression_recoverability runs with value/exact accuracy, "
            "citation F1, and parse rate."
        )
    )
    parser.add_argument("--data", required=True, type=Path, help="Fixture JSONL path.")
    parser.add_argument("--preds", required=True, type=Path, help="Predictions JSONL path.")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Summary output path (default: <preds_dir>/compression_recoverability_summary.json).",
    )
    parser.add_argument("--rows-out", type=Path, default=None, help="Optional per-row diagnostics JSONL.")
    parser.add_argument("--min-value-acc", type=float, default=None)
    parser.add_argument("--min-exact-acc", type=float, default=None)
    parser.add_argument("--min-cite-f1", type=float, default=None)
    return parser.parse_args()


def _mean(values: list[float]) -> float:
    return (sum(values) / len(values)) if values else 0.0


def _norm_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, sort_keys=True, ensure_ascii=True)


def _support_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        if value is None:
            return set()
        return {str(value)}
    out: set[str] = set()
    for item in value:
        if item is None:
            continue
        out.add(str(item))
    return out


def _citation_prf(pred: set[str], gold: set[str]) -> tuple[float, float, float]:
    inter = len(pred & gold)
    p = inter / len(pred) if pred else (1.0 if not gold else 0.0)
    r = inter / len(gold) if gold else 1.0
    f1 = (2.0 * p * r / (p + r)) if p > 0.0 and r > 0.0 else 0.0
    return p, r, f1


def _check_thresholds(summary: dict[str, Any], args: argparse.Namespace) -> list[str]:
    means = summary.get("means", {})
    failures: list[str] = []

    def _check_min(name: str, threshold: float | None) -> None:
        if threshold is None:
            return
        value = means.get(name)
        if not isinstance(value, (int, float)) or float(value) < threshold:
            failures.append(f"{name} < {threshold}")

    _check_min("value_acc", args.min_value_acc)
    _check_min("exact_acc", args.min_exact_acc)
    _check_min("cite_f1", args.min_cite_f1)
    return failures


def main() -> int:
    args = _parse_args()
    out_path = args.out or (args.preds.parent / "compression_recoverability_summary.json")

    data_rows = [row for row in read_jsonl(args.data) if isinstance(row, dict)]
    pred_rows = [row for row in read_jsonl(args.preds) if isinstance(row, dict)]
    preds_by_id = {str(row.get("id")): row for row in pred_rows if row.get("id") is not None}

    value_accs: list[float] = []
    exact_accs: list[float] = []
    cite_ps: list[float] = []
    cite_rs: list[float] = []
    cite_f1s: list[float] = []
    parse_rates: list[float] = []
    row_diags: list[dict[str, Any]] = []

    for data_row in data_rows:
        rid = str(data_row.get("id"))
        pred_row = preds_by_id.get(rid, {})
        gold = data_row.get("gold") if isinstance(data_row.get("gold"), dict) else {}
        gold_value = gold.get("value")
        pred_has_value = "value" in pred_row
        pred_value = pred_row.get("value")

        gold_norm = _norm_value(gold_value)
        pred_norm = _norm_value(pred_value)
        value_ok = float(gold_norm == pred_norm)
        exact_ok = value_ok

        gold_support = _support_set(gold.get("support_ids"))
        pred_support = _support_set(pred_row.get("support_ids"))
        cite_p, cite_r, cite_f1 = _citation_prf(pred_support, gold_support)

        value_accs.append(value_ok)
        exact_accs.append(exact_ok)
        cite_ps.append(cite_p)
        cite_rs.append(cite_r)
        cite_f1s.append(cite_f1)
        parse_rates.append(1.0 if pred_has_value else 0.0)

        row_diags.append(
            {
                "id": rid,
                "value_ok": bool(value_ok),
                "exact_ok": bool(exact_ok),
                "gold_value": gold_value,
                "pred_value": pred_value,
                "gold_support_ids": sorted(gold_support),
                "pred_support_ids": sorted(pred_support),
                "cite_p": cite_p,
                "cite_r": cite_r,
                "cite_f1": cite_f1,
                "parse_ok": bool(pred_has_value),
            }
        )

    summary: dict[str, Any] = {
        "benchmark": "compression_recoverability",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_path": str(args.data),
        "preds_path": str(args.preds),
        "rows_total": len(data_rows),
        "rows_scored": len(row_diags),
        "means": {
            "value_acc": _mean(value_accs),
            "exact_acc": _mean(exact_accs),
            "entailment": _mean(value_accs),
            "cite_p": _mean(cite_ps),
            "cite_r": _mean(cite_rs),
            "cite_f1": _mean(cite_f1s),
            "parse_rate": _mean(parse_rates),
        },
    }

    thresholds: dict[str, float] = {}
    if args.min_value_acc is not None:
        thresholds["min_value_acc"] = args.min_value_acc
    if args.min_exact_acc is not None:
        thresholds["min_exact_acc"] = args.min_exact_acc
    if args.min_cite_f1 is not None:
        thresholds["min_cite_f1"] = args.min_cite_f1
    if thresholds:
        summary["thresholds"] = thresholds

    failures = _check_thresholds(summary, args)
    summary["failures"] = failures
    summary["status"] = "PASS" if not failures else "FAIL"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")
    print(
        "compression_recoverability:"
        f" n={summary['rows_scored']}"
        f" value_acc={summary['means']['value_acc']:.3f}"
        f" exact_acc={summary['means']['exact_acc']:.3f}"
        f" cite_f1={summary['means']['cite_f1']:.3f}"
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
