from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from goldevidencebench.util import read_jsonl, write_jsonl


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Score row-level persona persistence drift by comparing canonical predictions "
            "against multi-turn persona-override perturbations."
        )
    )
    parser.add_argument("--canonical-preds", required=True, type=Path)
    parser.add_argument("--perturbed-preds", required=True, type=Path)
    parser.add_argument("--canonical-data", required=True, type=Path)
    parser.add_argument("--perturbed-data", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--rows-out", required=True, type=Path)
    parser.add_argument("--min-row-invariance-rate", type=float, default=1.0)
    return parser.parse_args()


def _to_pred_map(path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        if not isinstance(row, dict):
            continue
        row_id = row.get("id")
        if row_id is None:
            continue
        out[str(row_id)] = row
    return out


def _to_data_map(path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        if not isinstance(row, dict):
            continue
        row_id = row.get("id")
        if row_id is None:
            continue
        out[str(row_id)] = row
    return out


def _normalize_support_ids(pred: dict[str, Any]) -> list[str]:
    supports: Any = pred.get("support_ids")
    if supports is None and pred.get("support_id") is not None:
        supports = [pred.get("support_id")]
    if not isinstance(supports, list):
        return []
    out: list[str] = []
    for item in supports:
        text = str(item).strip().upper()
        if text:
            out.append(text)
    return out


def _normalize_jsonish_string(value: str) -> Any:
    raw = value.strip()
    if not raw:
        return None
    if raw[0] in "{[":
        try:
            return _normalize_value(json.loads(raw))
        except Exception:
            return raw
    return raw


def _normalize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        return _normalize_jsonish_string(value)
    if isinstance(value, dict):
        return {str(k): _normalize_value(v) for k, v in sorted(value.items(), key=lambda x: str(x[0]))}
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    if isinstance(value, (bool, int, float)):
        return value
    return str(value).strip()


def _normalize_prediction(pred: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(pred, dict):
        return {"parse_ok": False, "value": None, "support_ids": []}
    has_value = "value" in pred
    has_support = "support_ids" in pred or "support_id" in pred
    return {
        "parse_ok": bool(has_value and has_support),
        "value": _normalize_value(pred.get("value")),
        "support_ids": _normalize_support_ids(pred),
    }


def _canonicalize_for_family(norm: dict[str, Any], family: str) -> dict[str, Any]:
    out = {
        "parse_ok": bool(norm.get("parse_ok")),
        "value": norm.get("value"),
        "support_ids": list(norm.get("support_ids") or []),
    }
    if family != "epistemic_calibration_suite":
        return out
    value = out.get("value")
    if not isinstance(value, dict):
        return out

    decision_raw = value.get("decision")
    decision = str(decision_raw).strip().lower() if decision_raw is not None else ""
    if decision in {"abstain", "ask", "retrieve"}:
        value = dict(value)
        value["decision"] = "abstain"
        value["answer"] = None
        needed_info = value.get("needed_info")
        if isinstance(needed_info, list):
            normalized_needed: list[str] = []
            seen: set[str] = set()
            for item in needed_info:
                text = re.sub(r"[^a-z0-9]+", "", str(item).strip().lower())
                if not text:
                    continue
                if text in seen:
                    continue
                seen.add(text)
                normalized_needed.append(text)
            value["needed_info"] = sorted(normalized_needed)
        out["value"] = _normalize_value(value)
        out["support_ids"] = []
    return out


def _count_reasons(rows: list[dict[str, Any]]) -> dict[str, int]:
    out = {
        "value_changed": 0,
        "support_changed": 0,
        "parse_changed": 0,
        "null_flip": 0,
    }
    for row in rows:
        for reason in row.get("change_reasons", []):
            if reason in out:
                out[reason] += 1
    return out


def _status_for_rate(rate: float, floor: float) -> str:
    return "PASS" if rate >= floor else "FAIL"


def main() -> int:
    ns = _parse_args()

    if ns.min_row_invariance_rate < 0.0 or ns.min_row_invariance_rate > 1.0:
        raise SystemExit("--min-row-invariance-rate must be between 0.0 and 1.0")

    canonical_data = _to_data_map(ns.canonical_data)
    perturbed_data_rows = [row for row in read_jsonl(ns.perturbed_data) if isinstance(row, dict)]
    canonical_preds = _to_pred_map(ns.canonical_preds)
    perturbed_preds = _to_pred_map(ns.perturbed_preds)

    rows_out: list[dict[str, Any]] = []

    for perturbed_row in perturbed_data_rows:
        perturbed_row_id = str(perturbed_row.get("id") or "")
        meta = perturbed_row.get("meta") if isinstance(perturbed_row.get("meta"), dict) else {}
        base_row_id = str(meta.get("persona_base_row_id") or "")
        profile = str(meta.get("persona_profile") or "")
        seed_profile = str(meta.get("persona_seed_profile") or profile)
        override_profile = str(meta.get("persona_override_profile") or "")
        base_row = canonical_data.get(base_row_id) if base_row_id in canonical_data else None
        base_meta = base_row.get("meta") if isinstance(base_row, dict) and isinstance(base_row.get("meta"), dict) else {}
        family = str(base_meta.get("family") or "")

        canonical_exists = base_row_id in canonical_data
        canonical_norm = _normalize_prediction(canonical_preds.get(base_row_id))
        perturbed_norm = _normalize_prediction(perturbed_preds.get(perturbed_row_id))
        canonical_norm = _canonicalize_for_family(canonical_norm, family)
        perturbed_norm = _canonicalize_for_family(perturbed_norm, family)

        change_reasons: list[str] = []
        if canonical_norm["parse_ok"] != perturbed_norm["parse_ok"]:
            change_reasons.append("parse_changed")
        if canonical_norm["value"] != perturbed_norm["value"]:
            change_reasons.append("value_changed")
        if canonical_norm["support_ids"] != perturbed_norm["support_ids"]:
            change_reasons.append("support_changed")
        canonical_is_null = canonical_norm["value"] is None
        perturbed_is_null = perturbed_norm["value"] is None
        if canonical_is_null != perturbed_is_null:
            change_reasons.append("null_flip")

        row_result = {
            "id": perturbed_row_id,
            "family": family,
            "persona_base_row_id": base_row_id,
            "persona_profile": profile,
            "persona_seed_profile": seed_profile,
            "persona_override_profile": override_profile,
            "canonical_row_exists": canonical_exists,
            "canonical_parse_ok": canonical_norm["parse_ok"],
            "perturbed_parse_ok": perturbed_norm["parse_ok"],
            "canonical_value": canonical_norm["value"],
            "perturbed_value": perturbed_norm["value"],
            "canonical_support_ids": canonical_norm["support_ids"],
            "perturbed_support_ids": perturbed_norm["support_ids"],
            "invariant": len(change_reasons) == 0,
            "change_reasons": change_reasons,
        }
        rows_out.append(row_result)

    rows_total = len(rows_out)
    rows_changed = sum(1 for row in rows_out if not bool(row.get("invariant")))
    row_invariance_rate = ((rows_total - rows_changed) / rows_total) if rows_total else 0.0
    drift_rate = 1.0 - row_invariance_rate
    change_reasons = _count_reasons(rows_out)
    status = _status_for_rate(row_invariance_rate, ns.min_row_invariance_rate)

    summary = {
        "benchmark": "persona_persistence_drift",
        "status": status,
        "min_row_invariance_rate": ns.min_row_invariance_rate,
        "row_invariance_rate": row_invariance_rate,
        "drift_rate": drift_rate,
        "rows_total": rows_total,
        "rows_changed": rows_changed,
        "change_reasons": change_reasons,
        "failure_category": "persona_persistence_drift",
    }

    ns.out.parent.mkdir(parents=True, exist_ok=True)
    ns.rows_out.parent.mkdir(parents=True, exist_ok=True)
    ns.out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_jsonl(ns.rows_out, rows_out)

    print(
        "persona_persistence_drift:"
        f" status={status}"
        f" row_invariance_rate={row_invariance_rate:.6f}"
        f" drift_rate={drift_rate:.6f}"
        f" rows_changed={rows_changed}/{rows_total}"
    )
    print(f"Wrote {ns.out}")
    print(f"Wrote {ns.rows_out}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
