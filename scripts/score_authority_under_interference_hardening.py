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
            "Score authority_under_interference_hardening runs using value/exact/citation "
            "metrics plus stale/note interference rates."
        )
    )
    parser.add_argument("--data", required=True, type=Path, help="Fixture JSONL path.")
    parser.add_argument("--preds", required=True, type=Path, help="Predictions JSONL path.")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Summary output path (default: <preds_dir>/authority_under_interference_hardening_summary.json).",
    )
    parser.add_argument("--rows-out", type=Path, default=None, help="Optional per-row diagnostics JSONL.")
    parser.add_argument("--min-value-acc", type=float, default=None)
    parser.add_argument("--min-exact-acc", type=float, default=None)
    parser.add_argument("--min-cite-f1", type=float, default=None)
    parser.add_argument("--min-latest-support-hit-rate", type=float, default=None)
    parser.add_argument("--max-note-citation-rate", type=float, default=None)
    parser.add_argument("--max-stale-citation-rate", type=float, default=None)
    parser.add_argument("--max-authority-violation-rate", type=float, default=None)
    return parser.parse_args()


def _mean(values: list[float]) -> float:
    return (sum(values) / len(values)) if values else 0.0


def _norm(value: Any) -> str:
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


def _check_thresholds(summary: dict[str, Any], ns: argparse.Namespace) -> list[str]:
    means = summary.get("means", {})
    failures: list[str] = []
    min_checks = [
        ("value_acc", ns.min_value_acc),
        ("exact_acc", ns.min_exact_acc),
        ("cite_f1", ns.min_cite_f1),
        ("latest_support_hit_rate", ns.min_latest_support_hit_rate),
    ]
    for metric, threshold in min_checks:
        if threshold is None:
            continue
        value = means.get(metric)
        if not isinstance(value, (int, float)) or float(value) < float(threshold):
            failures.append(f"{metric} < {threshold}")

    max_checks = [
        ("note_citation_rate", ns.max_note_citation_rate),
        ("stale_citation_rate", ns.max_stale_citation_rate),
        ("authority_violation_rate", ns.max_authority_violation_rate),
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
    out_path = ns.out or (ns.preds.parent / "authority_under_interference_hardening_summary.json")

    data_rows = [row for row in read_jsonl(ns.data) if isinstance(row, dict)]
    pred_rows = [row for row in read_jsonl(ns.preds) if isinstance(row, dict)]
    preds_by_id = {str(row.get("id")): row for row in pred_rows if row.get("id") is not None}

    value_accs: list[float] = []
    exact_accs: list[float] = []
    cite_ps: list[float] = []
    cite_rs: list[float] = []
    cite_f1s: list[float] = []
    parse_rates: list[float] = []
    latest_hits: list[float] = []
    note_hits: list[float] = []
    stale_hits: list[float] = []
    authority_violations: list[float] = []
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
        latest_support = _support_set(meta.get("latest_support_ids")) or gold_support
        note_support = _support_set(meta.get("note_support_ids"))
        stale_support = _support_set(meta.get("stale_support_ids"))

        cite_p, cite_r, cite_f1 = _citation_prf(pred_support, gold_support)
        latest_hit = float(bool(pred_support & latest_support))
        note_hit = float(bool(pred_support & note_support))
        stale_hit = float(bool(pred_support & stale_support))
        authority_violation = float(bool(note_hit or stale_hit))

        value_accs.append(value_ok)
        exact_accs.append(exact_ok)
        cite_ps.append(cite_p)
        cite_rs.append(cite_r)
        cite_f1s.append(cite_f1)
        parse_rates.append(1.0 if has_value else 0.0)
        latest_hits.append(latest_hit)
        note_hits.append(note_hit)
        stale_hits.append(stale_hit)
        authority_violations.append(authority_violation)

        row_diags.append(
            {
                "id": rid,
                "value_ok": bool(value_ok),
                "exact_ok": bool(exact_ok),
                "gold_value": gold.get("value"),
                "pred_value": pred.get("value"),
                "parse_ok": bool(has_value),
                "gold_support_ids": sorted(gold_support),
                "pred_support_ids": sorted(pred_support),
                "latest_support_ids": sorted(latest_support),
                "note_support_ids": sorted(note_support),
                "stale_support_ids": sorted(stale_support),
                "cite_p": cite_p,
                "cite_r": cite_r,
                "cite_f1": cite_f1,
                "latest_support_hit": bool(latest_hit),
                "note_citation": bool(note_hit),
                "stale_citation": bool(stale_hit),
                "authority_violation": bool(authority_violation),
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
        "latest_support_hit_rate": _mean(latest_hits),
        "note_citation_rate": _mean(note_hits),
        "stale_citation_rate": _mean(stale_hits),
        "authority_violation_rate": _mean(authority_violations),
    }
    summary: dict[str, Any] = {
        "benchmark": "authority_under_interference_hardening",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_path": str(ns.data),
        "preds_path": str(ns.preds),
        "rows_total": len(data_rows),
        "rows_scored": len(row_diags),
        "means": means,
    }

    thresholds: dict[str, float] = {}
    for name in (
        "min_value_acc",
        "min_exact_acc",
        "min_cite_f1",
        "min_latest_support_hit_rate",
        "max_note_citation_rate",
        "max_stale_citation_rate",
        "max_authority_violation_rate",
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
        "authority_under_interference_hardening:"
        f" n={summary['rows_scored']}"
        f" value_acc={means['value_acc']:.3f}"
        f" exact_acc={means['exact_acc']:.3f}"
        f" cite_f1={means['cite_f1']:.3f}"
        f" latest_hit={means['latest_support_hit_rate']:.3f}"
        f" authority_violation={means['authority_violation_rate']:.3f}"
        f" parse_rate={means['parse_rate']:.3f}"
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

