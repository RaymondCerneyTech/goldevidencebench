from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from goldevidencebench.util import read_jsonl


_QUERY_TYPES = ("direct", "aggregate", "exception", "negation")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Score compression_roundtrip_generalization runs with core "
            "accuracy/citation metrics and orthogonal subset metrics."
        )
    )
    parser.add_argument("--data", required=True, type=Path, help="Fixture JSONL path.")
    parser.add_argument("--preds", required=True, type=Path, help="Predictions JSONL path.")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Summary output path (default: <preds_dir>/compression_roundtrip_generalization_summary.json).",
    )
    parser.add_argument("--rows-out", type=Path, default=None, help="Optional per-row diagnostics JSONL.")
    parser.add_argument("--min-value-acc", type=float, default=None)
    parser.add_argument("--min-exact-acc", type=float, default=None)
    parser.add_argument("--min-cite-f1", type=float, default=None)
    parser.add_argument("--min-direct-acc", type=float, default=None)
    parser.add_argument("--min-aggregate-acc", type=float, default=None)
    parser.add_argument("--min-exception-acc", type=float, default=None)
    parser.add_argument("--min-negation-acc", type=float, default=None)
    parser.add_argument("--min-tail-key-acc", type=float, default=None)
    parser.add_argument("--min-null-target-acc", type=float, default=None)
    parser.add_argument("--min-nonnull-target-acc", type=float, default=None)
    parser.add_argument("--min-large-snapshot-acc", type=float, default=None)
    parser.add_argument(
        "--large-snapshot-min-keys",
        type=int,
        default=64,
        help="Rows with snapshot_key_count >= this threshold are counted for large_snapshot_acc.",
    )
    return parser.parse_args()


def _norm(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value.strip().lower()
    return json.dumps(value, sort_keys=True, ensure_ascii=True)


def _support_set(value: Any) -> set[str]:
    if isinstance(value, list):
        return {str(v) for v in value if v is not None}
    if value is None:
        return set()
    return {str(value)}


def _citation_prf(pred: set[str], gold: set[str]) -> tuple[float, float, float]:
    inter = len(pred & gold)
    precision = inter / len(pred) if pred else (1.0 if not gold else 0.0)
    recall = inter / len(gold) if gold else 1.0
    f1 = (2.0 * precision * recall / (precision + recall)) if precision > 0 and recall > 0 else 0.0
    return precision, recall, f1


def _mean(values: list[float]) -> float:
    return (sum(values) / len(values)) if values else 0.0


def _check_thresholds(summary: dict[str, Any], ns: argparse.Namespace) -> list[str]:
    means = summary.get("means", {})
    failures: list[str] = []
    checks = [
        ("value_acc", ns.min_value_acc),
        ("exact_acc", ns.min_exact_acc),
        ("cite_f1", ns.min_cite_f1),
        ("direct_acc", ns.min_direct_acc),
        ("aggregate_acc", ns.min_aggregate_acc),
        ("exception_acc", ns.min_exception_acc),
        ("negation_acc", ns.min_negation_acc),
        ("tail_key_acc", ns.min_tail_key_acc),
        ("null_target_acc", ns.min_null_target_acc),
        ("nonnull_target_acc", ns.min_nonnull_target_acc),
        ("large_snapshot_acc", ns.min_large_snapshot_acc),
    ]
    for metric, threshold in checks:
        if threshold is None:
            continue
        value = means.get(metric)
        if not isinstance(value, (int, float)) or float(value) < float(threshold):
            failures.append(f"{metric} < {threshold}")
    return failures


def main() -> int:
    ns = _parse_args()
    out_path = ns.out or (ns.preds.parent / "compression_roundtrip_generalization_summary.json")

    data_rows = [row for row in read_jsonl(ns.data) if isinstance(row, dict)]
    pred_rows = [row for row in read_jsonl(ns.preds) if isinstance(row, dict)]
    preds_by_id = {str(row.get("id")): row for row in pred_rows if row.get("id") is not None}

    value_accs: list[float] = []
    exact_accs: list[float] = []
    cite_ps: list[float] = []
    cite_rs: list[float] = []
    cite_f1s: list[float] = []
    parse_rates: list[float] = []
    per_type: dict[str, list[float]] = {k: [] for k in _QUERY_TYPES}
    tail_accs: list[float] = []
    null_target_accs: list[float] = []
    nonnull_target_accs: list[float] = []
    large_snapshot_accs: list[float] = []
    row_diags: list[dict[str, Any]] = []

    for data_row in data_rows:
        rid = str(data_row.get("id"))
        pred = preds_by_id.get(rid, {})
        gold = data_row.get("gold") if isinstance(data_row.get("gold"), dict) else {}
        meta = data_row.get("meta") if isinstance(data_row.get("meta"), dict) else {}

        has_value = "value" in pred
        gold_norm = _norm(gold.get("value"))
        pred_norm = _norm(pred.get("value"))
        value_ok = float(gold_norm == pred_norm)
        exact_ok = value_ok

        gold_support = _support_set(gold.get("support_ids"))
        pred_support = _support_set(pred.get("support_ids"))
        cite_p, cite_r, cite_f1 = _citation_prf(pred_support, gold_support)

        query_type = str(meta.get("query_type", "")).strip().lower()
        query_position = str(meta.get("query_position", "")).strip().lower()
        query_target_type = str(meta.get("query_target_type", "")).strip().lower()
        snapshot_key_count = int(meta.get("snapshot_key_count", 0) or 0)

        value_accs.append(value_ok)
        exact_accs.append(exact_ok)
        cite_ps.append(cite_p)
        cite_rs.append(cite_r)
        cite_f1s.append(cite_f1)
        parse_rates.append(1.0 if has_value else 0.0)
        if query_type in per_type:
            per_type[query_type].append(value_ok)
        if query_position == "tail":
            tail_accs.append(value_ok)
        if query_target_type == "null":
            null_target_accs.append(value_ok)
        if query_target_type == "nonnull":
            nonnull_target_accs.append(value_ok)
        if snapshot_key_count >= ns.large_snapshot_min_keys:
            large_snapshot_accs.append(value_ok)

        row_diags.append(
            {
                "id": rid,
                "query_type": query_type,
                "query_position": query_position,
                "query_target_type": query_target_type,
                "snapshot_key_count": snapshot_key_count,
                "value_ok": bool(value_ok),
                "exact_ok": bool(exact_ok),
                "gold_value": gold.get("value"),
                "pred_value": pred.get("value"),
                "gold_support_ids": sorted(gold_support),
                "pred_support_ids": sorted(pred_support),
                "cite_p": cite_p,
                "cite_r": cite_r,
                "cite_f1": cite_f1,
                "parse_ok": bool(has_value),
            }
        )

    means = {
        "value_acc": _mean(value_accs),
        "exact_acc": _mean(exact_accs),
        "entailment": _mean(value_accs),
        "cite_p": _mean(cite_ps),
        "cite_r": _mean(cite_rs),
        "cite_f1": _mean(cite_f1s),
        "parse_rate": _mean(parse_rates),
        "direct_acc": _mean(per_type["direct"]),
        "aggregate_acc": _mean(per_type["aggregate"]),
        "exception_acc": _mean(per_type["exception"]),
        "negation_acc": _mean(per_type["negation"]),
        "tail_key_acc": _mean(tail_accs),
        "null_target_acc": _mean(null_target_accs),
        "nonnull_target_acc": _mean(nonnull_target_accs),
        "large_snapshot_acc": _mean(large_snapshot_accs),
        "direct_count": float(len(per_type["direct"])),
        "aggregate_count": float(len(per_type["aggregate"])),
        "exception_count": float(len(per_type["exception"])),
        "negation_count": float(len(per_type["negation"])),
        "tail_key_count": float(len(tail_accs)),
        "null_target_count": float(len(null_target_accs)),
        "nonnull_target_count": float(len(nonnull_target_accs)),
        "large_snapshot_count": float(len(large_snapshot_accs)),
    }

    summary: dict[str, Any] = {
        "benchmark": "compression_roundtrip_generalization",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_path": str(ns.data),
        "preds_path": str(ns.preds),
        "rows_total": len(data_rows),
        "rows_scored": len(row_diags),
        "means": means,
        "subset_policy": {
            "large_snapshot_min_keys": ns.large_snapshot_min_keys,
        },
    }

    thresholds: dict[str, float] = {}
    for key in (
        "min_value_acc",
        "min_exact_acc",
        "min_cite_f1",
        "min_direct_acc",
        "min_aggregate_acc",
        "min_exception_acc",
        "min_negation_acc",
        "min_tail_key_acc",
        "min_null_target_acc",
        "min_nonnull_target_acc",
        "min_large_snapshot_acc",
    ):
        value = getattr(ns, key)
        if value is not None:
            thresholds[key] = float(value)
    if thresholds:
        summary["thresholds"] = thresholds

    failures = _check_thresholds(summary, ns)
    summary["failures"] = failures
    summary["status"] = "PASS" if not failures else "FAIL"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")
    print(
        "compression_roundtrip_generalization:"
        f" n={summary['rows_scored']}"
        f" value_acc={means['value_acc']:.3f}"
        f" exact_acc={means['exact_acc']:.3f}"
        f" cite_f1={means['cite_f1']:.3f}"
        f" direct_acc={means['direct_acc']:.3f}"
        f" aggregate_acc={means['aggregate_acc']:.3f}"
        f" exception_acc={means['exception_acc']:.3f}"
        f" negation_acc={means['negation_acc']:.3f}"
        f" tail_key_acc={means['tail_key_acc']:.3f}"
        f" status={summary['status']}"
    )

    if ns.rows_out is not None:
        ns.rows_out.parent.mkdir(parents=True, exist_ok=True)
        with ns.rows_out.open("w", encoding="utf-8", newline="\n") as handle:
            for row in row_diags:
                handle.write(json.dumps(row, ensure_ascii=True) + "\n")
        print(f"Wrote {ns.rows_out}")

    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
