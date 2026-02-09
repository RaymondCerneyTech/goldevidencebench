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
            "Score myopic_planning_traps runs with value/exact/citation metrics and "
            "planning-specific trap metrics."
        )
    )
    parser.add_argument("--data", required=True, type=Path, help="Fixture JSONL path.")
    parser.add_argument("--preds", required=True, type=Path, help="Predictions JSONL path.")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Summary output path (default: <preds_dir>/myopic_planning_traps_summary.json).",
    )
    parser.add_argument("--rows-out", type=Path, default=None, help="Optional per-row diagnostics JSONL.")
    parser.add_argument("--min-value-acc", type=float, default=None)
    parser.add_argument("--min-exact-acc", type=float, default=None)
    parser.add_argument("--min-cite-f1", type=float, default=None)
    parser.add_argument("--min-horizon-success-rate", type=float, default=None)
    parser.add_argument("--min-recovery-rate", type=float, default=None)
    parser.add_argument("--max-trap-entry-rate", type=float, default=None)
    parser.add_argument("--min-first-error-step-mean", type=float, default=None)
    parser.add_argument("--min-entry-acc", type=float, default=None)
    parser.add_argument("--min-counterfactual-acc", type=float, default=None)
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


def _failure_mode_id(*, profile: str, value_ok: bool, trap_entry: bool, recovery_expected: str, pred_norm: str) -> str | None:
    if value_ok:
        return None
    if trap_entry:
        return "trap_entry"
    if profile == "horizon":
        return "horizon_failure"
    if profile == "recovery":
        if pred_norm == _norm(recovery_expected):
            return "recovery_misparsed"
        return "recovery_failure"
    if profile == "counterfactual":
        return "counterfactual_failure"
    if profile == "entry":
        return "entry_failure"
    return f"{profile}_failure"


def _check_thresholds(summary: dict[str, Any], ns: argparse.Namespace) -> list[str]:
    means = summary.get("means", {})
    failures: list[str] = []

    min_checks = [
        ("value_acc", ns.min_value_acc),
        ("exact_acc", ns.min_exact_acc),
        ("cite_f1", ns.min_cite_f1),
        ("horizon_success_rate", ns.min_horizon_success_rate),
        ("recovery_rate", ns.min_recovery_rate),
        ("first_error_step_mean", ns.min_first_error_step_mean),
        ("entry_acc", ns.min_entry_acc),
        ("counterfactual_acc", ns.min_counterfactual_acc),
    ]
    for metric, threshold in min_checks:
        if threshold is None:
            continue
        value = means.get(metric)
        if not isinstance(value, (int, float)) or float(value) < float(threshold):
            failures.append(f"{metric} < {threshold}")

    max_checks = [
        ("trap_entry_rate", ns.max_trap_entry_rate),
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
    out_path = ns.out or (ns.preds.parent / "myopic_planning_traps_summary.json")

    data_rows = [row for row in read_jsonl(ns.data) if isinstance(row, dict)]
    pred_rows = [row for row in read_jsonl(ns.preds) if isinstance(row, dict)]
    preds_by_id = {str(row.get("id")): row for row in pred_rows if row.get("id") is not None}

    value_accs: list[float] = []
    exact_accs: list[float] = []
    cite_ps: list[float] = []
    cite_rs: list[float] = []
    cite_f1s: list[float] = []
    parse_rates: list[float] = []

    entry_accs: list[float] = []
    horizon_accs: list[float] = []
    recovery_accs: list[float] = []
    counterfactual_accs: list[float] = []
    trap_entries: list[float] = []
    first_error_steps: list[float] = []

    row_diags: list[dict[str, Any]] = []
    failure_mode_counts: Counter[str] = Counter()

    for data_row in data_rows:
        rid = str(data_row.get("id"))
        pred = preds_by_id.get(rid, {})
        gold = data_row.get("gold") if isinstance(data_row.get("gold"), dict) else {}
        meta = data_row.get("meta") if isinstance(data_row.get("meta"), dict) else {}

        profile = str(meta.get("profile", "")).strip().lower()
        local_action = str(meta.get("local_action", "")).strip()
        recovery_action = str(meta.get("recovery_action", "")).strip()
        horizon_steps = int(meta.get("horizon_steps", 0) or 0)

        has_value = "value" in pred
        gold_norm = _norm(gold.get("value"))
        pred_norm = _norm(pred.get("value"))
        value_ok = float(gold_norm == pred_norm)
        exact_ok = value_ok

        gold_support = _support_set(gold.get("support_ids"))
        pred_support = _support_set(pred.get("support_ids"))
        cite_p, cite_r, cite_f1 = _citation_prf(pred_support, gold_support)

        trap_entry = bool(local_action) and pred_norm == _norm(local_action)

        if value_ok >= 1.0:
            first_error_step = float(max(1, horizon_steps + 1))
        elif trap_entry:
            first_error_step = 1.0
        else:
            first_error_step = 2.0

        value_accs.append(value_ok)
        exact_accs.append(exact_ok)
        cite_ps.append(cite_p)
        cite_rs.append(cite_r)
        cite_f1s.append(cite_f1)
        parse_rates.append(1.0 if has_value else 0.0)
        trap_entries.append(1.0 if trap_entry else 0.0)
        first_error_steps.append(first_error_step)

        if profile == "entry":
            entry_accs.append(value_ok)
        elif profile == "horizon":
            horizon_accs.append(value_ok)
        elif profile == "recovery":
            recovery_accs.append(value_ok)
        elif profile == "counterfactual":
            counterfactual_accs.append(value_ok)

        failure_mode_id = _failure_mode_id(
            profile=profile,
            value_ok=bool(value_ok),
            trap_entry=trap_entry,
            recovery_expected=recovery_action,
            pred_norm=pred_norm,
        )
        if failure_mode_id:
            failure_mode_counts[failure_mode_id] += 1

        row_diags.append(
            {
                "id": rid,
                "profile": profile,
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
                "trap_entry": trap_entry,
                "first_error_step": first_error_step,
                "failure_mode_id": failure_mode_id,
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
        "entry_acc": _mean(entry_accs),
        "horizon_success_rate": _mean(horizon_accs),
        "recovery_rate": _mean(recovery_accs),
        "counterfactual_acc": _mean(counterfactual_accs),
        "trap_entry_rate": _mean(trap_entries),
        "first_error_step_mean": _mean(first_error_steps),
        "entry_count": float(len(entry_accs)),
        "horizon_count": float(len(horizon_accs)),
        "recovery_count": float(len(recovery_accs)),
        "counterfactual_count": float(len(counterfactual_accs)),
    }

    summary: dict[str, Any] = {
        "benchmark": "myopic_planning_traps",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_path": str(ns.data),
        "preds_path": str(ns.preds),
        "rows_total": len(data_rows),
        "rows_scored": len(row_diags),
        "means": means,
        "failure_mode_ids": sorted(failure_mode_counts.keys()),
        "failure_mode_counts": dict(sorted(failure_mode_counts.items())),
    }

    thresholds: dict[str, float] = {}
    for key in (
        "min_value_acc",
        "min_exact_acc",
        "min_cite_f1",
        "min_horizon_success_rate",
        "min_recovery_rate",
        "max_trap_entry_rate",
        "min_first_error_step_mean",
        "min_entry_acc",
        "min_counterfactual_acc",
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
        "myopic_planning_traps:"
        f" n={summary['rows_scored']}"
        f" value_acc={means['value_acc']:.3f}"
        f" exact_acc={means['exact_acc']:.3f}"
        f" cite_f1={means['cite_f1']:.3f}"
        f" horizon_success_rate={means['horizon_success_rate']:.3f}"
        f" recovery_rate={means['recovery_rate']:.3f}"
        f" trap_entry_rate={means['trap_entry_rate']:.3f}"
        f" first_error_step_mean={means['first_error_step_mean']:.3f}"
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
