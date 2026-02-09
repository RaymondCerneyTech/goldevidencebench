from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from goldevidencebench.util import read_jsonl


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Score referential_indexing_suite runs with indexing/reassembly metrics."
        )
    )
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--preds", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--rows-out", type=Path, default=None)
    parser.add_argument("--min-value-acc", type=float, default=None)
    parser.add_argument("--min-exact-acc", type=float, default=None)
    parser.add_argument("--min-cite-f1", type=float, default=None)
    parser.add_argument("--min-part-coverage-recall", type=float, default=None)
    parser.add_argument("--min-pointer-precision", type=float, default=None)
    parser.add_argument("--min-pointer-recall", type=float, default=None)
    parser.add_argument("--min-reassembly-fidelity", type=float, default=None)
    parser.add_argument("--max-hallucinated-expansion-rate", type=float, default=None)
    parser.add_argument("--max-stale-pointer-override-rate", type=float, default=None)
    parser.add_argument("--max-lookup-depth-cost", type=float, default=None)
    parser.add_argument("--min-exception-acc", type=float, default=None)
    parser.add_argument("--min-large-snapshot-acc", type=float, default=None)
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


def _parse_pred(row: dict[str, Any]) -> tuple[Any, set[str], float | None]:
    raw_value = row.get("value")
    support = _support_set(row.get("support_ids"))
    lookup_depth: float | None = None

    if isinstance(raw_value, str):
        text = raw_value.strip()
        if text.startswith("{") and text.endswith("}"):
            try:
                obj = json.loads(text)
            except Exception:
                obj = None
            if isinstance(obj, dict):
                value = obj.get("value", obj.get("answer"))
                if not support and "support_ids" in obj:
                    support = _support_set(obj.get("support_ids"))
                raw_lookup = obj.get("lookup_depth")
                if isinstance(raw_lookup, (int, float)):
                    lookup_depth = float(raw_lookup)
                return value, support, lookup_depth

    return raw_value, support, lookup_depth


def _check_thresholds(summary: dict[str, Any], ns: argparse.Namespace) -> list[str]:
    means = summary.get("means", {})
    failures: list[str] = []

    min_checks = [
        ("value_acc", ns.min_value_acc),
        ("exact_acc", ns.min_exact_acc),
        ("cite_f1", ns.min_cite_f1),
        ("part_coverage_recall", ns.min_part_coverage_recall),
        ("pointer_precision", ns.min_pointer_precision),
        ("pointer_recall", ns.min_pointer_recall),
        ("reassembly_fidelity", ns.min_reassembly_fidelity),
        ("exception_acc", ns.min_exception_acc),
        ("large_snapshot_acc", ns.min_large_snapshot_acc),
    ]
    for metric, threshold in min_checks:
        if threshold is None:
            continue
        value = means.get(metric)
        if not isinstance(value, (int, float)) or float(value) < float(threshold):
            failures.append(f"{metric} < {threshold}")

    max_checks = [
        ("hallucinated_expansion_rate", ns.max_hallucinated_expansion_rate),
        ("stale_pointer_override_rate", ns.max_stale_pointer_override_rate),
        ("lookup_depth_cost", ns.max_lookup_depth_cost),
    ]
    for metric, threshold in max_checks:
        if threshold is None:
            continue
        value = means.get(metric)
        if not isinstance(value, (int, float)) or float(value) > float(threshold):
            failures.append(f"{metric} > {threshold}")

    return failures


def main() -> int:
    ns = _parse_args()
    out_path = ns.out or (ns.preds.parent / "referential_indexing_suite_summary.json")

    data_rows = [row for row in read_jsonl(ns.data) if isinstance(row, dict)]
    pred_rows = [row for row in read_jsonl(ns.preds) if isinstance(row, dict)]
    preds_by_id = {str(row.get("id")): row for row in pred_rows if row.get("id") is not None}

    value_accs: list[float] = []
    exact_accs: list[float] = []
    cite_ps: list[float] = []
    cite_rs: list[float] = []
    cite_f1s: list[float] = []
    parse_rates: list[float] = []
    pointer_sizes: list[float] = []
    part_cov_recalls: list[float] = []
    reassembly_fids: list[float] = []
    hallucinated_rates: list[float] = []
    stale_override_rates: list[float] = []
    lookup_costs: list[float] = []

    family_hits: Counter[str] = Counter()
    family_counts: Counter[str] = Counter()
    failure_modes: Counter[str] = Counter()
    row_diags: list[dict[str, Any]] = []

    for data_row in data_rows:
        rid = str(data_row.get("id"))
        pred_row = preds_by_id.get(rid, {})
        gold = data_row.get("gold") if isinstance(data_row.get("gold"), dict) else {}
        meta = data_row.get("meta") if isinstance(data_row.get("meta"), dict) else {}

        family_id = str(meta.get("family_id", "unknown"))
        family_counts[family_id] += 1

        pred_value, pred_support, pred_lookup_depth = _parse_pred(pred_row)
        gold_support = _support_set(gold.get("support_ids"))
        all_support = _support_set(meta.get("all_support_ids")) | gold_support

        has_value = "value" in pred_row
        value_ok = float(_norm(pred_value) == _norm(gold.get("value")))
        exact_ok = value_ok
        cite_p, cite_r, cite_f1 = _citation_prf(pred_support, gold_support)

        hallucinated = float(bool(pred_support - all_support))

        stale_override = 0.0
        if family_id == "stale_pointer_conflict" and not value_ok:
            if _norm(pred_value) == _norm(meta.get("stale_value")):
                stale_override = 1.0

        lookup_target = meta.get("lookup_depth_target")
        if pred_lookup_depth is not None:
            lookup_cost = pred_lookup_depth
        elif isinstance(lookup_target, (int, float)):
            lookup_cost = float(lookup_target)
        else:
            lookup_cost = 0.0

        value_accs.append(value_ok)
        exact_accs.append(exact_ok)
        cite_ps.append(cite_p)
        cite_rs.append(cite_r)
        cite_f1s.append(cite_f1)
        parse_rates.append(1.0 if has_value else 0.0)
        pointer_sizes.append(float(len(pred_support)))
        part_cov_recalls.append(value_ok)
        reassembly_fids.append(exact_ok)
        hallucinated_rates.append(hallucinated)
        stale_override_rates.append(stale_override)
        lookup_costs.append(lookup_cost)

        if value_ok:
            family_hits[family_id] += 1
        else:
            failure_modes[f"{family_id}_miss"] += 1
        if hallucinated:
            failure_modes["hallucinated_expansion"] += 1
        if stale_override:
            failure_modes["stale_pointer_override"] += 1

        row_diags.append(
            {
                "id": rid,
                "family_id": family_id,
                "value_ok": bool(value_ok),
                "exact_ok": bool(exact_ok),
                "gold_value": gold.get("value"),
                "pred_value": pred_value,
                "gold_support_ids": sorted(gold_support),
                "pred_support_ids": sorted(pred_support),
                "cite_p": cite_p,
                "cite_r": cite_r,
                "cite_f1": cite_f1,
                "hallucinated_expansion": bool(hallucinated),
                "stale_pointer_override": bool(stale_override),
                "lookup_depth_cost": lookup_cost,
            }
        )

    means: dict[str, float] = {
        "value_acc": _mean(value_accs),
        "exact_acc": _mean(exact_accs),
        "entailment": _mean(value_accs),
        "cite_p": _mean(cite_ps),
        "cite_r": _mean(cite_rs),
        "cite_f1": _mean(cite_f1s),
        "parse_rate": _mean(parse_rates),
        "pointer_set_size": _mean(pointer_sizes),
        "part_coverage_recall": _mean(part_cov_recalls),
        "pointer_precision": _mean(cite_ps),
        "pointer_recall": _mean(cite_rs),
        "reassembly_fidelity": _mean(reassembly_fids),
        "hallucinated_expansion_rate": _mean(hallucinated_rates),
        "stale_pointer_override_rate": _mean(stale_override_rates),
        "lookup_depth_cost": _mean(lookup_costs),
        "exception_acc": (
            family_hits.get("stale_pointer_conflict", 0) / family_counts.get("stale_pointer_conflict", 1)
            if family_counts.get("stale_pointer_conflict", 0) > 0
            else 0.0
        ),
        "large_snapshot_acc": (
            family_hits.get("wrong_hub_attraction", 0) / family_counts.get("wrong_hub_attraction", 1)
            if family_counts.get("wrong_hub_attraction", 0) > 0
            else 0.0
        ),
    }

    for family_id, count in sorted(family_counts.items()):
        acc = family_hits.get(family_id, 0) / count if count > 0 else 0.0
        means[f"{family_id}_acc"] = acc
        means[f"{family_id}_count"] = float(count)

    summary: dict[str, Any] = {
        "benchmark": "referential_indexing_suite",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_path": str(ns.data),
        "preds_path": str(ns.preds),
        "rows_total": len(data_rows),
        "rows_scored": len(row_diags),
        "means": means,
        "failure_mode_ids": sorted(failure_modes.keys()),
        "failure_mode_counts": dict(sorted(failure_modes.items())),
    }

    thresholds: dict[str, float] = {}
    for name in (
        "min_value_acc",
        "min_exact_acc",
        "min_cite_f1",
        "min_part_coverage_recall",
        "min_pointer_precision",
        "min_pointer_recall",
        "min_reassembly_fidelity",
        "max_hallucinated_expansion_rate",
        "max_stale_pointer_override_rate",
        "max_lookup_depth_cost",
        "min_exception_acc",
        "min_large_snapshot_acc",
    ):
        value = getattr(ns, name)
        if value is not None:
            thresholds[name] = float(value)
    if thresholds:
        summary["thresholds"] = thresholds

    failures = _check_thresholds(summary, ns)
    summary["failures"] = failures
    summary["status"] = "PASS" if not failures else "FAIL"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")
    print(
        "referential_indexing_suite:"
        f" n={summary['rows_scored']}"
        f" value_acc={means['value_acc']:.3f}"
        f" exact_acc={means['exact_acc']:.3f}"
        f" cite_f1={means['cite_f1']:.3f}"
        f" fidelity={means['reassembly_fidelity']:.3f}"
        f" hallucinated={means['hallucinated_expansion_rate']:.3f}"
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
