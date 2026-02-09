from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from goldevidencebench.baselines import parse_updates
from goldevidencebench.grade import (
    _implied_from_citations,
    _norm_support_list,
    _norm_value,
    _prf1,
)
from goldevidencebench.util import read_jsonl, write_jsonl


def _require_citations(row: dict[str, Any], citations: str) -> bool:
    if citations == "on":
        return True
    if citations == "off":
        return False
    return bool(row.get("meta", {}).get("requires_citation", False))


def _norm_supports(pred: dict[str, Any], max_support_k: int) -> list[str]:
    supports = _norm_support_list(pred.get("support_ids"))
    if not supports:
        supports = _norm_support_list(pred.get("support_id"))
    return supports[:max_support_k]


def _gold_supports(row: dict[str, Any]) -> list[str]:
    gold = row.get("gold", {})
    supports = _norm_support_list(gold.get("support_ids"))
    if not supports:
        supports = _norm_support_list(gold.get("support_id"))
    return supports


def _check_row(
    *,
    row: dict[str, Any],
    pred: dict[str, Any],
    citations: str,
    support_metric: str,
    max_support_k: int,
    entailment_check: bool,
) -> dict[str, Any]:
    gold = row.get("gold", {})
    pv = _norm_value(pred.get("value"))
    gv = _norm_value(gold.get("value"))
    pred_supports = _norm_supports(pred, max_support_k=max_support_k)
    gold_supports = _gold_supports(row)
    require = _require_citations(row, citations)

    value_ok = pv == gv
    cite_ok = True
    entails_ok = True
    cite_prec = None
    cite_rec = None
    cite_f1 = None
    bloat = False
    missing_citations = False

    if require:
        cite_prec, cite_rec, cite_f1 = _prf1(pred=pred_supports, gold=gold_supports)
        bloat = bool(gold_supports) and len(pred_supports) > len(gold_supports)
        if support_metric == "exact":
            cite_ok = set(pred_supports) == set(gold_supports)
        else:
            cite_ok = set(gold_supports).issubset(set(pred_supports))
        if bloat:
            cite_ok = False

        if entailment_check:
            uid_to_entry = {e["uid"]: e for e in parse_updates(row["document"])}
            cited_entries = [uid_to_entry.get(uid) for uid in pred_supports]
            if any(e is None for e in cited_entries):
                entails_ok = False
                missing_citations = True
            else:
                implied = _implied_from_citations(
                    row=row, cited_entries=[e for e in cited_entries if e is not None]
                )
                entails_ok = _norm_value(implied) == pv

    exact_ok = value_ok and (cite_ok if require else True) and (entails_ok if require else True)

    reasons: list[str] = []
    if not pred:
        reasons.append("missing_pred")
    if not value_ok:
        reasons.append("value_mismatch")
    if require and not cite_ok:
        reasons.append("citation_mismatch")
    if require and not entails_ok:
        reasons.append("entailment_fail")
    if require and missing_citations:
        reasons.append("unknown_support_id")
    if require and bloat:
        reasons.append("support_bloat")

    meta = row.get("meta", {})
    return {
        "id": row.get("id"),
        "question": row.get("question"),
        "key": meta.get("key"),
        "query_type": meta.get("query_type"),
        "derived_op": meta.get("derived_op"),
        "state_mode": meta.get("state_mode"),
        "gold_value": gv,
        "pred_value": pv,
        "gold_support_ids": gold_supports,
        "pred_support_ids": pred_supports,
        "require_citations": require,
        "value_ok": value_ok,
        "cite_ok": cite_ok if require else None,
        "entails_ok": entails_ok if require and entailment_check else None,
        "exact_ok": exact_ok,
        "citation_precision": cite_prec,
        "citation_recall": cite_rec,
        "citation_f1": cite_f1,
        "reasons": reasons,
        "last_update_step": meta.get("last_update_step"),
        "tokens_since_update": meta.get("tokens_since_update"),
        "writes_to_key": meta.get("writes_to_key"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Emit per-question failure details for a RAG dataset."
    )
    parser.add_argument("--data", required=True, type=Path, help="Dataset JSONL path.")
    parser.add_argument("--preds", required=True, type=Path, help="Predictions JSONL path.")
    parser.add_argument("--out", required=True, type=Path, help="Output JSONL path.")
    parser.add_argument("--citations", choices=["auto", "on", "off"], default="auto")
    parser.add_argument("--support-metric", choices=["f1", "exact"], default="f1")
    parser.add_argument("--max-support-k", type=int, default=3)
    parser.add_argument(
        "--entailment-check",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--include-passes",
        action="store_true",
        help="Include passing rows (default: failures only).",
    )
    args = parser.parse_args()

    data_rows = list(read_jsonl(args.data))
    pred_rows = list(read_jsonl(args.preds))
    pred_by_id = {row.get("id"): row for row in pred_rows if isinstance(row, dict)}

    failures: list[dict[str, Any]] = []
    passes = 0
    for row in data_rows:
        if not isinstance(row, dict):
            continue
        rid = row.get("id")
        pred = pred_by_id.get(rid, {})
        diag = _check_row(
            row=row,
            pred=pred,
            citations=args.citations,
            support_metric=args.support_metric,
            max_support_k=args.max_support_k,
            entailment_check=args.entailment_check,
        )
        if diag["exact_ok"]:
            passes += 1
            if args.include_passes:
                failures.append(diag)
        else:
            failures.append(diag)

    write_jsonl(args.out, failures)
    total = len([r for r in data_rows if isinstance(r, dict)])
    print(
        f"Wrote {len(failures)} rows to {args.out} ({passes}/{total} exact_ok)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
