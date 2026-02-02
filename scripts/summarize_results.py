from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path
from typing import Any

from goldevidencebench import drift as drift_mod
from goldevidencebench import grade as grade_mod
from goldevidencebench import diagnosis as diagnosis_mod
from goldevidencebench import compaction as compaction_mod
from goldevidencebench import reporting as reporting_mod
from goldevidencebench import thread_log as thread_log_mod
from goldevidencebench import schema_validation
from goldevidencebench.baselines import parse_book_ledger, parse_model_json_answer, parse_updates
from goldevidencebench.util import read_jsonl


def _iso_timestamp(ts: datetime | None = None) -> str:
    now = ts or datetime.now(timezone.utc)
    return now.isoformat()


REPRO_ARTIFACT_VERSION = "1.0.0"


def _model_fingerprint(model_path: str | None) -> dict[str, Any]:
    if not model_path:
        return {"path": None, "exists": False}
    path = Path(model_path)
    if not path.exists():
        return {"path": model_path, "exists": False}
    try:
        stat = path.stat()
    except OSError:
        return {"path": model_path, "exists": False}
    fingerprint: dict[str, Any] = {
        "path": str(path),
        "exists": True,
        "size_bytes": stat.st_size,
        "mtime": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }
    try:
        with path.open("rb") as handle:
            chunk = handle.read(1024 * 1024)
        fingerprint["sha256_1mb"] = hashlib.sha256(chunk).hexdigest()
    except OSError:
        fingerprint["sha256_1mb"] = None
    return fingerprint


def _git_commit(repo_root: Path) -> str | None:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return commit or None


def _build_repro_metadata(
    rows: list[dict[str, Any]],
    *,
    input_path: Path,
    out_json: Path,
) -> dict[str, Any]:
    first = rows[0] if rows else {}
    env = first.get("env") or {}
    config = first.get("config") or {}
    data = first.get("data") or {}
    stats = first.get("retrieval_stats") or []
    first_stat = stats[0] if isinstance(stats, list) and stats else {}
    rerank_mode = first_stat.get("rerank_mode") or env.get("GOLDEVIDENCEBENCH_RETRIEVAL_RERANK")
    authority_raw = env.get("GOLDEVIDENCEBENCH_RETRIEVAL_AUTHORITY_FILTER", "0")
    authority_enabled = str(authority_raw).lower() in {"1", "true", "yes"}
    command_line = subprocess.list2cmdline([sys.executable, *sys.argv])

    repo_root = Path(__file__).resolve().parents[1]
    model_path = env.get("GOLDEVIDENCEBENCH_MODEL") or os.environ.get("GOLDEVIDENCEBENCH_MODEL")
    return {
        "schema_version": "1",
        "artifact_version": REPRO_ARTIFACT_VERSION,
        "generated_at": _iso_timestamp(),
        "commands": [command_line],
        "command_line": command_line,
        "args": sys.argv[1:],
        "baseline": first.get("baseline") or first.get("adapter"),
        "adapter": first.get("adapter"),
        "protocol": first.get("protocol"),
        "state_mode": first.get("state_mode"),
        "seed": first.get("seed"),
        "steps": first.get("steps"),
        "retrieval": {
            "k": first_stat.get("k"),
            "rerank_mode": rerank_mode,
        },
        "config": config,
        "env": env,
        "key_env": {
            "GOLDEVIDENCEBENCH_MODEL": env.get("GOLDEVIDENCEBENCH_MODEL"),
            "GOLDEVIDENCEBENCH_RETRIEVAL_RERANK": env.get("GOLDEVIDENCEBENCH_RETRIEVAL_RERANK"),
            "GOLDEVIDENCEBENCH_RETRIEVAL_AUTHORITY_FILTER": env.get(
                "GOLDEVIDENCEBENCH_RETRIEVAL_AUTHORITY_FILTER"
            ),
            "GOLDEVIDENCEBENCH_UI_GATE_MODELS": env.get("GOLDEVIDENCEBENCH_UI_GATE_MODELS"),
            "GOLDEVIDENCEBENCH_UI_PRESELECT_RULES": env.get("GOLDEVIDENCEBENCH_UI_PRESELECT_RULES"),
        },
        "model": _model_fingerprint(model_path),
        "git_commit": _git_commit(repo_root),
        "config_paths": {
            "combined_json": str(input_path),
            "summary_json": str(out_json),
            "data_path": data.get("path"),
        },
        "authority_mode": "filter_on" if authority_enabled else "filter_off",
    }


def _flatten(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    out["adapter_schema_version"] = row.get("adapter_schema_version")
    out["baseline"] = row.get("baseline") or row.get("adapter")
    out["protocol"] = row.get("protocol")
    out["seed"] = row.get("seed")
    out["state_mode"] = row.get("state_mode")
    out["distractor_profile"] = row.get("distractor_profile")

    data = row.get("data", {})
    out["data_path"] = data.get("path")
    out["n"] = data.get("n")

    cfg = row.get("config", {})
    for key in (
        "seeds",
        "episodes",
        "steps",
        "keys",
        "queries",
        "derived_query_rate",
        "chapters",
        "distractor_rate",
        "tail_distractor_steps",
        "clear_rate",
        "require_citations",
        "twins",
        "state_modes",
        "distractor_profiles",
        "no_derived_queries",
        "no_require_citations",
        "citations",
        "support_metric",
        "max_support_k",
        "entailment_check",
        "max_book_tokens",
    ):
        if key in cfg:
            out[key] = cfg.get(key)

    env = row.get("env", {})
    out["GOLDEVIDENCEBENCH_MODEL"] = env.get("GOLDEVIDENCEBENCH_MODEL")
    out["GOLDEVIDENCEBENCH_REQUIRE_CITATIONS"] = env.get("GOLDEVIDENCEBENCH_REQUIRE_CITATIONS")

    metrics = row.get("metrics", {})
    for key in (
        "value_acc",
        "exact_acc",
        "cite_f1",
        "cite_p",
        "cite_r",
        "support_bloat",
        "entailment",
        "twin_consistency",
        "twin_flip_rate",
        "instruction_acc",
        "instruction_gap",
        "instr_override_rate",
        "instr_conflict_present_rate",
        "instr_conflict_present_count",
        "state_integrity_rate",
    ):
        if key in metrics:
            out[key] = metrics.get(key)
    metrics_raw = row.get("metrics_raw") or {}
    for key in (
        "value_acc",
        "exact_acc",
        "cite_f1",
        "cite_p",
        "cite_r",
        "support_bloat",
        "entailment",
        "twin_consistency",
        "twin_flip_rate",
        "instruction_acc",
        "instruction_gap",
        "instr_override_rate",
        "instr_conflict_present_rate",
        "instr_conflict_present_count",
        "state_integrity_rate",
    ):
        if key in metrics_raw:
            out[f"raw_{key}"] = metrics_raw.get(key)
    return out


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _norm_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        return s if s else None
    return str(value).strip() or None


def _norm_support_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if item is None:
                continue
            s = str(item).strip()
            if s:
                out.append(s)
        return out
    s = str(value).strip()
    return [s] if s else []



def _is_abstain(pred: dict[str, Any]) -> bool:
    value = _norm_value(pred.get("value"))
    supports = _norm_support_list(pred.get("support_ids") or pred.get("support_id"))
    return value is None and not supports



def _entry_value_for_uid(book: str | None, uid: str | None) -> str | None:
    if not book or not uid:
        return None
    for entry in parse_book_ledger(book):
        if entry.get("uid") == uid:
            return _norm_value(entry.get("value"))
    return None



def _bucket_label(value: int, edges: list[int]) -> str:
    if not edges:
        return "all"
    prev = 0
    for edge in edges:
        if value < edge:
            return f"{prev}-{edge}"
        prev = edge
    return f"{edges[-1]}+"


def _parse_edges(raw: str | None, default: str) -> list[int]:
    text = raw if raw is not None else default
    return [int(s) for s in text.split(",") if s.strip()]


def _relpath(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def _compute_decomposition(
    *,
    data_rows: list[dict[str, Any]],
    pred_by_id: dict[str, dict[str, Any]],
    retrieval_stats: list[dict[str, Any]],
) -> dict[str, Any] | None:
    retrieval_by_id: dict[str, dict[str, Any]] = {}
    for stat in retrieval_stats:
        rid = stat.get("id")
        if rid:
            retrieval_by_id[rid] = stat
    total = len(retrieval_stats)
    if total == 0:
        return None
    included = 0
    value_ok = 0
    selection_total = 0
    selection_ok = 0
    gold_selected_total = 0
    gold_selected_value_ok = 0
    gold_selected_value_in_line_total = 0
    gold_selected_value_in_line_ok = 0
    support_consistency_total = 0
    support_consistency_ok = 0
    gold_support_selected_total = 0
    gold_support_selected_ok = 0
    selected_entry_total = 0
    selected_note_ok = 0
    selected_wrong_update_total = 0
    selected_wrong_update_ok = 0
    selected_spoof_total = 0
    selected_spoof_ok = 0
    selected_spoof_non_gold = 0
    abstain_total = 0
    abstain_on_missing = 0
    gold_missing_total = 0
    for row in data_rows:
        rid = row.get("id")
        if not rid:
            continue
        pred = pred_by_id.get(rid)
        if pred is None:
            continue
        diag = retrieval_by_id.get(rid)
        if not diag:
            continue
        gold_missing = diag.get("gold_missing")
        if gold_missing is None:
            gold_missing = diag.get("correct_included") is not True or diag.get("dropped_correct") is True
        abstained = diag.get("abstained") is True or _is_abstain(pred)
        if abstained:
            abstain_total += 1
            if gold_missing:
                abstain_on_missing += 1
        if gold_missing:
            gold_missing_total += 1
        if diag.get("correct_included") is not True:
            continue
        included += 1
        gold_value = _norm_value(row.get("gold", {}).get("value"))
        pred_value = _norm_value(pred.get("value"))
        if gold_value == pred_value:
            value_ok += 1
        gold_supports = _norm_support_list(
            row.get("gold", {}).get("support_ids") or row.get("gold", {}).get("support_id")
        )
        correct_uid = diag.get("correct_uid") or (gold_supports[0] if gold_supports else None)
        if correct_uid:
            selection_total += 1
            pred_supports = _norm_support_list(pred.get("support_ids") or pred.get("support_id"))
            if correct_uid in pred_supports:
                selection_ok += 1
                gold_selected_total += 1
                if gold_value == pred_value:
                    gold_selected_value_ok += 1
                entry_value = _entry_value_for_uid(row.get("book"), correct_uid)
                if entry_value is not None and pred_value is not None:
                    gold_selected_value_in_line_total += 1
                    if pred_value in entry_value:
                        gold_selected_value_in_line_ok += 1
            selected_uid = diag.get("selected_uid")
            if selected_uid:
                support_consistency_total += 1
                if selected_uid in pred_supports:
                    support_consistency_ok += 1
            gold_uid = gold_supports[0] if gold_supports else None
            if gold_uid:
                gold_support_selected_total += 1
                if gold_uid in pred_supports:
                    gold_support_selected_ok += 1
            selected_uid = diag.get("selected_uid")
            if selected_uid:
                selected_entry = next((e for e in parse_book_ledger(row.get("book") or "") if e.get("uid") == selected_uid), None)
                if selected_entry:
                    selected_entry_total += 1
                    if str(selected_entry.get("op", "")).upper() == "NOTE":
                        selected_note_ok += 1
                    if gold_uid and selected_uid != gold_uid:
                        selected_wrong_update_total += 1
                        if str(selected_entry.get("op", "")).upper() != "NOTE":
                            selected_wrong_update_ok += 1
                if "selected_spoofed" in diag:
                    selected_spoof_total += 1
                    if diag.get("selected_spoofed") is True:
                        selected_spoof_ok += 1
                        if gold_uid and selected_uid and selected_uid != gold_uid:
                            selected_spoof_non_gold += 1
                        if gold_uid and selected_uid and selected_uid != gold_uid:
                            selected_spoof_non_gold += 1
    gold_present_rate = included / total if total else 0.0
    acc_when = (value_ok / included) if included else 0.0
    selection_rate = (selection_ok / selection_total) if selection_total else None
    return {
        "gold_present_rate": gold_present_rate,
        "accuracy_when_gold_present": acc_when,
        "selection_rate": selection_rate,
        "answer_acc_given_gold_selected": (
            gold_selected_value_ok / gold_selected_total if gold_selected_total else None
        ),
        "value_acc_when_gold_selected": (
            gold_selected_value_ok / gold_selected_total if gold_selected_total else None
        ),
        "value_is_substring_of_selected_line_rate": (
            gold_selected_value_in_line_ok / gold_selected_value_in_line_total
            if gold_selected_value_in_line_total
            else None
        ),
        "support_consistency_rate": (
            support_consistency_ok / support_consistency_total if support_consistency_total else None
        ),
        "gold_support_selected_rate": (
            gold_support_selected_ok / gold_support_selected_total if gold_support_selected_total else None
        ),
        "selected_note_rate": (
            selected_note_ok / selected_entry_total if selected_entry_total else None
        ),
        "selected_wrong_update_rate": (
            selected_wrong_update_ok / selected_wrong_update_total if selected_wrong_update_total else None
        ),
        "wrong_update_rate": (
            selected_wrong_update_ok / selected_entry_total if selected_entry_total else None
        ),
        "spoof_accept_rate": (
            selected_spoof_ok / selected_spoof_total if selected_spoof_total else None
        ),
        "spoof_accept_rate_non_gold": (
            selected_spoof_non_gold / selected_entry_total if selected_entry_total else None
        ),
        "gold_missing_rate": (gold_missing_total / total if total else None),
        "abstain_rate": (abstain_total / total if total else None),
        "abstain_precision": (abstain_on_missing / abstain_total if abstain_total else None),
        "abstain_recall": (abstain_on_missing / gold_missing_total if gold_missing_total else None),
    }


def _pred_index(pred_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in pred_rows:
        rid = r.get("id")
        if not rid:
            continue
        if "value" in r or "support_id" in r or "support_ids" in r:
            out[rid] = {
                "value": r.get("value"),
                "support_id": r.get("support_id"),
                "support_ids": r.get("support_ids"),
            }
            continue
        text = r.get("output") or r.get("text") or r.get("completion")
        if isinstance(text, str):
            parsed = parse_model_json_answer(text)
            out[rid] = {
                "value": parsed.get("value"),
                "support_id": parsed.get("support_id"),
                "support_ids": parsed.get("support_ids"),
            }
    return out


def _infer_run_holdout(row: dict[str, Any]) -> str | None:
    profile = row.get("distractor_profile")
    if isinstance(profile, str) and profile in diagnosis_mod.HOLDOUT_NAMES:
        return profile
    cfg = row.get("config", {})
    if isinstance(cfg, dict):
        profile = cfg.get("distractor_profile")
        if isinstance(profile, str) and profile in diagnosis_mod.HOLDOUT_NAMES:
            return profile
        profiles = cfg.get("distractor_profiles")
        if isinstance(profiles, list) and len(profiles) == 1:
            only = profiles[0]
            if isinstance(only, str) and only in diagnosis_mod.HOLDOUT_NAMES:
                return only
    return None


def _score_rows(
    *,
    data_rows: list[dict[str, Any]],
    pred_by_id: dict[str, dict[str, Any]],
    citations: str,
    support_metric: str,
    max_support_k: int,
    entailment_check: bool,
) -> list[dict[str, Any]]:
    scored: list[dict[str, Any]] = []
    for row in data_rows:
        rid = row["id"]
        pred = pred_by_id.get(rid, {})
        gold = row["gold"]

        pv = grade_mod._norm_value(pred.get("value"))
        gv = grade_mod._norm_value(gold.get("value"))
        pred_supports = grade_mod._norm_support_list(pred.get("support_ids"))
        if not pred_supports:
            pred_supports = grade_mod._norm_support_list(pred.get("support_id"))
        gold_supports = grade_mod._norm_support_list(gold.get("support_ids"))
        if not gold_supports:
            gold_supports = grade_mod._norm_support_list(gold.get("support_id"))

        require = row["meta"].get("requires_citation", False) if citations == "auto" else citations == "on"
        is_cite_ok = True
        is_entails = True
        prec = None
        rec = None
        if require:
            pred_supports_scored = pred_supports[:max_support_k]
            prec, rec, _f1 = grade_mod._prf1(pred=pred_supports_scored, gold=gold_supports)
            is_bloat = bool(gold_supports) and len(pred_supports_scored) > len(gold_supports)
            if support_metric == "exact":
                is_cite_ok = set(pred_supports_scored) == set(gold_supports)
            else:
                is_cite_ok = set(gold_supports).issubset(set(pred_supports_scored))
            if is_bloat:
                is_cite_ok = False

            if entailment_check:
                uid_to_entry = {e["uid"]: e for e in parse_updates(row["document"])}
                cited_entries = [uid_to_entry.get(uid) for uid in pred_supports_scored]
                if any(e is None for e in cited_entries):
                    is_entails = False
                else:
                    implied = grade_mod._implied_from_citations(
                        row=row,
                        cited_entries=[e for e in cited_entries if e is not None],
                    )
                    is_entails = grade_mod._norm_value(implied) == pv
            else:
                is_entails = True

        value_ok = pv == gv
        exact_ok = value_ok and (is_cite_ok if require else True) and (is_entails if require else True)
        scored.append({"row": row, "value_ok": value_ok, "exact_ok": exact_ok, "prec": prec, "rec": rec})
    return scored


def _summarize_recency(rows: list[dict[str, Any]], edges: list[int]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for entry in rows:
        row = entry["row"]
        val = row.get("meta", {}).get("tokens_since_update")
        if val is None:
            continue
        try:
            val = int(val)
        except (TypeError, ValueError):
            continue
        label = _bucket_label(val, edges)
        buckets[label]["value_ok"].append(int(entry["value_ok"]))
        buckets[label]["exact_ok"].append(int(entry["exact_ok"]))

    out = []
    for label in sorted(buckets.keys(), key=lambda x: (x.endswith("+"), x)):
        vals = buckets[label]
        n = len(vals["value_ok"])
        out.append(
            {
                "bucket": label,
                "n": n,
                "value_acc": sum(vals["value_ok"]) / n if n else 0.0,
                "exact_acc": sum(vals["exact_ok"]) / n if n else 0.0,
            }
        )
    return out


def _summarize_bucket(
    rows: list[dict[str, Any]],
    *,
    field: str,
    edges: list[int],
) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for entry in rows:
        row = entry["row"]
        val = row.get("meta", {}).get(field)
        if val is None:
            continue
        try:
            val = int(val)
        except (TypeError, ValueError):
            continue
        label = _bucket_label(val, edges)
        buckets[label]["value_ok"].append(int(entry["value_ok"]))
        buckets[label]["exact_ok"].append(int(entry["exact_ok"]))

    out = []
    for label in sorted(buckets.keys(), key=lambda x: (x.endswith("+"), x)):
        vals = buckets[label]
        n = len(vals["value_ok"])
        out.append(
            {
                "bucket": label,
                "n": n,
                "value_acc": sum(vals["value_ok"]) / n if n else 0.0,
                "exact_acc": sum(vals["exact_ok"]) / n if n else 0.0,
            }
        )
    return out


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    grouped_raw: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    overall: dict[str, list[float]] = defaultdict(list)
    overall_raw: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        metrics = row.get("metrics", {})
        key = (row.get("state_mode") or "", row.get("distractor_profile") or "")
        for metric_key in (
            "value_acc",
            "exact_acc",
            "cite_f1",
            "entailment",
            "instr_override_rate",
            "instr_conflict_present_rate",
            "instr_conflict_present_count",
            "state_integrity_rate",
        ):
            value = metrics.get(metric_key)
            if value is None:
                continue
            grouped[key][metric_key].append(float(value))
            overall[metric_key].append(float(value))
        metrics_raw = row.get("metrics_raw") or {}
        for metric_key in (
            "value_acc",
            "exact_acc",
            "cite_f1",
            "entailment",
            "instr_override_rate",
            "instr_conflict_present_rate",
            "instr_conflict_present_count",
            "state_integrity_rate",
        ):
            value = metrics_raw.get(metric_key)
            if value is None:
                continue
            grouped_raw[key][metric_key].append(float(value))
            overall_raw[metric_key].append(float(value))

    averages = []
    for k, metric_map in sorted(grouped.items()):
        entry = {
            "state_mode": k[0],
            "distractor_profile": k[1],
            "n": max((len(v) for v in metric_map.values()), default=0),
        }
        for metric_key, values in metric_map.items():
            entry[f"{metric_key}_mean"] = _mean(values)
        averages.append(entry)

    averages_raw = []
    for k, metric_map in sorted(grouped_raw.items()):
        entry = {
            "state_mode": k[0],
            "distractor_profile": k[1],
            "n": max((len(v) for v in metric_map.values()), default=0),
        }
        for metric_key, values in metric_map.items():
            entry[f"{metric_key}_mean"] = _mean(values)
        averages_raw.append(entry)

    overall_means = {f"{k}_mean": _mean(v) for k, v in overall.items()}
    overall_raw_means = {f"{k}_mean": _mean(v) for k, v in overall_raw.items()}
    summary = {
        "rows": len(rows),
        "overall": overall_means,
        "overall_raw": overall_raw_means,
        "by_group": averages,
        "by_group_raw": averages_raw,
    }
    retrieval_stats = []
    for row in rows:
        stats = row.get("retrieval_stats")
        if isinstance(stats, list):
            retrieval_stats.extend([s for s in stats if isinstance(s, dict)])
    if retrieval_stats:
        included = [1.0 for s in retrieval_stats if s.get("correct_included") is True]
        total = len(retrieval_stats)
        ranks = [s.get("correct_rank") for s in retrieval_stats if s.get("correct_rank") is not None]
        dropped = [1.0 for s in retrieval_stats if s.get("dropped_correct") is True]
        summary["retrieval"] = {
            "n": total,
            "gold_in_context_rate": (sum(included) / total) if total else 0.0,
            "correct_rank_mean": (sum(ranks) / len(ranks)) if ranks else None,
            "drop_rate": (sum(dropped) / total) if total else 0.0,
        }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize GoldEvidenceBench results JSON into CSV/JSON.")
    parser.add_argument("--in", dest="input_path", type=Path, default=Path("runs/combined.json"))
    parser.add_argument("--out-csv", dest="out_csv", type=Path, default=Path("runs/summary.csv"))
    parser.add_argument("--out-json", dest="out_json", type=Path, default=Path("runs/summary.json"))
    parser.add_argument(
        "--out-decomp-csv",
        dest="out_decomp_csv",
        type=Path,
        default=None,
        help="Optional path for decomposition CSV output (one row per run).",
    )
    parser.add_argument(
        "--recency-buckets",
        type=str,
        default=None,
        help="Comma-separated token buckets for tokens_since_update (e.g., 200,400,800,1600).",
    )
    parser.add_argument(
        "--distractor-buckets",
        type=str,
        default=None,
        help="Comma-separated buckets for distractors_since_update (e.g., 2,4,8,16).",
    )
    parser.add_argument(
        "--writes-buckets",
        type=str,
        default=None,
        help="Comma-separated buckets for writes_to_key (e.g., 1,2,4,8).",
    )
    args = parser.parse_args()

    rows = json.loads(args.input_path.read_text(encoding="utf-8"))
    flat = [_flatten(row) for row in rows]
    summary = summarize(rows)
    recency_edges = _parse_edges(args.recency_buckets, "200,400,800,1600")
    distractor_edges = _parse_edges(args.distractor_buckets, "2,4,8,16")
    writes_edges = _parse_edges(args.writes_buckets, "1,2,4,8")

    gold_present_total = 0
    gold_present_value_ok = 0
    selection_total = 0
    selection_ok = 0
    gold_selected_total = 0
    gold_selected_value_ok = 0
    gold_selected_value_in_line_total = 0
    gold_selected_value_in_line_ok = 0
    support_consistency_total = 0
    support_consistency_ok = 0
    gold_support_selected_total = 0
    gold_support_selected_ok = 0
    selected_entry_total = 0
    selected_note_ok = 0
    selected_wrong_update_total = 0
    selected_wrong_update_ok = 0
    selected_spoof_total = 0
    selected_spoof_ok = 0
    selected_spoof_non_gold = 0
    abstain_total = 0
    abstain_on_missing = 0
    gold_missing_total = 0
    drift_counts = drift_mod.DriftCounts()
    decomp_rows: list[dict[str, Any]] = []
    drift_examples: list[dict[str, Any]] = []
    holdout_names: set[str] = set()
    context_keys: set[str] = set()

    recency_rows = []
    for row in rows:
        run_holdout = _infer_run_holdout(row)
        if run_holdout:
            holdout_names.add(run_holdout)
        data_path = row.get("data", {}).get("path")
        if not data_path:
            continue
        preds_path = Path(data_path).parent / "preds.jsonl"
        if not preds_path.exists():
            continue
        data_rows = list(read_jsonl(data_path))
        for data_row in data_rows:
            key = data_row.get("meta", {}).get("key")
            if key:
                context_keys.add(str(key))
        preds = list(read_jsonl(preds_path))
        pred_by_id = _pred_index(preds)
        retrieval_by_id: dict[str, dict[str, Any]] = {}
        stats = row.get("retrieval_stats")
        if isinstance(stats, list):
            decomp = _compute_decomposition(
                data_rows=data_rows, pred_by_id=pred_by_id, retrieval_stats=stats
            )
            if decomp:
                first = stats[0] if stats else {}
                metrics = row.get("metrics", {})
                decomp_rows.append(
                    {
                        "baseline": row.get("baseline") or row.get("adapter"),
                        "seed": row.get("seed"),
                        "state_mode": row.get("state_mode"),
                        "distractor_profile": row.get("distractor_profile"),
                        "steps": row.get("steps"),
                        "queries": row.get("data", {}).get("n"),
                        "max_book_tokens": row.get("config", {}).get("max_book_tokens"),
                        "retrieval_k": first.get("k"),
                        "retrieval_wrong_type": first.get("wrong_type"),
                        "retrieval_order": first.get("order"),
                        "retrieval_drop_prob": first.get("drop_prob"),
                        "retrieval_rerank": first.get("rerank_mode"),
                        "pick_then_answer": first.get("pick_then_answer"),
                        "gold_present_rate": decomp["gold_present_rate"],
                        "selection_rate": decomp["selection_rate"],
                        "accuracy_when_gold_present": decomp["accuracy_when_gold_present"],
                        "answer_acc_given_gold_selected": decomp.get("answer_acc_given_gold_selected"),
                        "value_acc_when_gold_selected": decomp.get("value_acc_when_gold_selected"),
                        "value_is_substring_of_selected_line_rate": decomp.get("value_is_substring_of_selected_line_rate"),
                        "support_consistency_rate": decomp.get("support_consistency_rate"),
                        "gold_support_selected_rate": decomp.get("gold_support_selected_rate"),
                        "selected_note_rate": decomp.get("selected_note_rate"),
                        "selected_wrong_update_rate": decomp.get("selected_wrong_update_rate"),
                        "wrong_update_rate": decomp.get("wrong_update_rate"),
                        "spoof_accept_rate": decomp.get("spoof_accept_rate"),
                        "spoof_accept_rate_non_gold": decomp.get("spoof_accept_rate_non_gold"),
                        "abstain_precision": decomp.get("abstain_precision"),
                        "abstain_recall": decomp.get("abstain_recall"),
                        "abstain_rate": decomp.get("abstain_rate"),
                        "gold_missing_rate": decomp.get("gold_missing_rate"),
                        "overall_value_acc": metrics.get("value_acc"),
                        "overall_exact_acc": metrics.get("exact_acc"),
                        "overall_cite_f1": metrics.get("cite_f1"),
                        "overall_entailment": metrics.get("entailment"),
                    }
                )
        if isinstance(stats, list):
            for stat in stats:
                if not isinstance(stat, dict):
                    continue
                rid = stat.get("id")
                if not rid:
                    continue
                retrieval_by_id[rid] = stat
        if run_holdout and len(drift_examples) < 3 and data_rows and pred_by_id and retrieval_by_id:
            drift_examples.extend(
                diagnosis_mod.build_drift_examples(
                    data_rows=data_rows,
                    pred_by_id=pred_by_id,
                    retrieval_by_id=retrieval_by_id,
                    holdout_name=run_holdout,
                    max_examples=3 - len(drift_examples),
                )
            )
        cfg = row.get("config", {})
        require_citations = cfg.get("require_citations", True)
        citations = "auto" if require_citations else "off"
        support_metric = cfg.get("support_metric", "f1")
        max_support_k = int(cfg.get("max_support_k", 3))
        entailment_check = bool(cfg.get("entailment_check", True))
        for data_row in data_rows:
            pred = pred_by_id.get(data_row.get("id"))
            if pred is None:
                continue
            diag = retrieval_by_id.get(data_row.get("id"))
            if not diag:
                continue
            gold_missing = diag.get("gold_missing")
            if gold_missing is None:
                gold_missing = diag.get("correct_included") is not True or diag.get("dropped_correct") is True
            abstained = diag.get("abstained") is True or _is_abstain(pred)
            if abstained:
                abstain_total += 1
                if gold_missing:
                    abstain_on_missing += 1
            if gold_missing:
                gold_missing_total += 1
            if diag.get("correct_included") is not True:
                continue
            gold_present_total += 1
            gold_value = _norm_value(data_row.get("gold", {}).get("value"))
            pred_value = _norm_value(pred.get("value"))
            if gold_value == pred_value:
                gold_present_value_ok += 1
            gold_supports = _norm_support_list(
                data_row.get("gold", {}).get("support_ids") or data_row.get("gold", {}).get("support_id")
            )
            correct_uid = diag.get("correct_uid") or (gold_supports[0] if gold_supports else None)
            if correct_uid:
                selection_total += 1
                pred_supports = _norm_support_list(pred.get("support_ids") or pred.get("support_id"))
                if correct_uid in pred_supports:
                    selection_ok += 1
                    gold_selected_total += 1
                    if gold_value == pred_value:
                        gold_selected_value_ok += 1
                    entry_value = _entry_value_for_uid(data_row.get("book"), correct_uid)
                    if entry_value is not None and pred_value is not None:
                        gold_selected_value_in_line_total += 1
                        if pred_value in entry_value:
                            gold_selected_value_in_line_ok += 1
                selected_uid = diag.get("selected_uid")
                if selected_uid:
                    support_consistency_total += 1
                    if selected_uid in pred_supports:
                        support_consistency_ok += 1
                gold_uid = gold_supports[0] if gold_supports else None
                if gold_uid:
                    gold_support_selected_total += 1
                    if gold_uid in pred_supports:
                        gold_support_selected_ok += 1
                selected_uid = diag.get("selected_uid")
                if selected_uid:
                    selected_entry = next((e for e in parse_book_ledger(data_row.get("book") or "") if e.get("uid") == selected_uid), None)
                    if selected_entry:
                        selected_entry_total += 1
                        if str(selected_entry.get("op", "")).upper() == "NOTE":
                            selected_note_ok += 1
                        if gold_uid and selected_uid != gold_uid:
                            selected_wrong_update_total += 1
                            if str(selected_entry.get("op", "")).upper() != "NOTE":
                                selected_wrong_update_ok += 1
                if "selected_spoofed" in diag:
                    selected_spoof_total += 1
                    if diag.get("selected_spoofed") is True:
                        selected_spoof_ok += 1
        if data_rows and pred_by_id and retrieval_by_id:
            drift_counts.add(
                drift_mod.compute_drift_counts(
                    data_rows=data_rows,
                    pred_by_id=pred_by_id,
                    retrieval_by_id=retrieval_by_id,
                )
            )
        recency_rows.extend(
            _score_rows(
                data_rows=data_rows,
                pred_by_id=pred_by_id,
                citations=citations,
                support_metric=support_metric,
                max_support_k=max_support_k,
                entailment_check=entailment_check,
            )
        )

    if gold_present_total:
        retrieval_summary = summary.setdefault("retrieval", {})
        retrieval_summary["gold_present_count"] = gold_present_total
        retrieval_summary["accuracy_when_gold_present"] = gold_present_value_ok / gold_present_total
        retrieval_summary["selection_rate"] = (selection_ok / selection_total) if selection_total else None
        if "gold_in_context_rate" in retrieval_summary:
            retrieval_summary["gold_present_rate"] = retrieval_summary["gold_in_context_rate"]
        retrieval_summary["answer_acc_given_gold_selected"] = (
            gold_selected_value_ok / gold_selected_total if gold_selected_total else None
        )
        retrieval_summary["value_acc_when_gold_selected"] = (
            gold_selected_value_ok / gold_selected_total if gold_selected_total else None
        )
        retrieval_summary["value_is_substring_of_selected_line_rate"] = (
            gold_selected_value_in_line_ok / gold_selected_value_in_line_total
            if gold_selected_value_in_line_total
            else None
        )
        retrieval_summary["support_consistency_rate"] = (
            support_consistency_ok / support_consistency_total if support_consistency_total else None
        )
        retrieval_summary["gold_support_selected_rate"] = (
            gold_support_selected_ok / gold_support_selected_total if gold_support_selected_total else None
        )
        retrieval_summary["selected_note_rate"] = (
            selected_note_ok / selected_entry_total if selected_entry_total else None
        )
        retrieval_summary["selected_wrong_update_rate"] = (
            selected_wrong_update_ok / selected_wrong_update_total if selected_wrong_update_total else None
        )
        retrieval_summary["wrong_update_rate"] = (
            selected_wrong_update_ok / selected_entry_total if selected_entry_total else None
        )
        retrieval_summary["spoof_accept_rate"] = (
            selected_spoof_ok / selected_spoof_total if selected_spoof_total else None
        )
        retrieval_summary["spoof_accept_rate_non_gold"] = (
            selected_spoof_non_gold / selected_entry_total if selected_entry_total else None
        )
        retrieval_summary["gold_missing_rate"] = (
            gold_missing_total / (gold_present_total + gold_missing_total)
            if (gold_present_total + gold_missing_total)
            else None
        )
        retrieval_summary["abstain_rate"] = (
            abstain_total / (gold_present_total + gold_missing_total)
            if (gold_present_total + gold_missing_total)
            else None
        )
        retrieval_summary["abstain_precision"] = (
            abstain_on_missing / abstain_total if abstain_total else None
        )
        retrieval_summary["abstain_recall"] = (
            abstain_on_missing / gold_missing_total if gold_missing_total else None
        )
        overall_acc = summary.get("overall", {}).get("value_acc_mean")
        gold_rate = retrieval_summary.get("gold_present_rate")
        sel_rate = retrieval_summary.get("selection_rate")
        acc_when = retrieval_summary.get("accuracy_when_gold_present")
        if None not in (gold_rate, sel_rate, acc_when, overall_acc):
            retrieval_summary["decomposition_line"] = (
                f"{gold_rate:.4f} -> {sel_rate:.4f} -> {acc_when:.4f} -> {overall_acc:.4f}"
            )

    if recency_rows:
        summary["recency"] = {
            "tokens_since_update": _summarize_recency(recency_rows, recency_edges),
            "distractors_since_update": _summarize_bucket(
                recency_rows, field="distractors_since_update", edges=distractor_edges
            ),
            "writes_to_key": _summarize_bucket(recency_rows, field="writes_to_key", edges=writes_edges),
        }
    if drift_counts.steps_total:
        summary["drift"] = drift_counts.as_metrics()

    if flat:
        with args.out_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=sorted(flat[0].keys()))
            writer.writeheader()
            writer.writerows(flat)
    if args.out_decomp_csv and decomp_rows:
        with args.out_decomp_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=sorted(decomp_rows[0].keys()))
            writer.writeheader()
            writer.writerows(decomp_rows)
    schema_validation.validate_or_raise(
        summary,
        schema_validation.schema_path("summary.schema.json"),
    )
    args.out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    thresholds_path = Path("configs") / "diagnosis_thresholds.json"
    thresholds = diagnosis_mod.load_thresholds(thresholds_path)
    holdout_name = holdout_names.pop() if len(holdout_names) == 1 else None
    diagnosis = diagnosis_mod.build_diagnosis(
        summary=summary,
        thresholds=thresholds,
        thresholds_path=thresholds_path,
        run_dir=args.out_json.parent,
        holdout_name=holdout_name,
        evidence_examples=drift_examples,
    )
    diagnosis_path = args.out_json.with_name("diagnosis.json")
    diagnosis_mod.write_diagnosis(diagnosis_path, diagnosis)

    run_dir = args.out_json.parent
    if "release_gates" not in run_dir.parts:
        repro_metadata = _build_repro_metadata(rows, input_path=args.input_path, out_json=args.out_json)
        repro_path = run_dir / "repro_commands.json"
        schema_validation.validate_or_raise(
            repro_metadata,
            schema_validation.schema_path("repro_commands.schema.json"),
        )
        repro_path.write_text(json.dumps(repro_metadata, indent=2, ensure_ascii=True), encoding="utf-8")

        env = repro_metadata.get("env") or {}
        authority_raw = env.get("GOLDEVIDENCEBENCH_RETRIEVAL_AUTHORITY_FILTER", "0")
        authority_enabled = str(authority_raw).lower() in {"1", "true", "yes"}
        rerank_mode = (repro_metadata.get("retrieval") or {}).get("rerank_mode")
        ui_gate_models_raw = str(env.get("GOLDEVIDENCEBENCH_UI_GATE_MODELS", "")).strip().lower()
        gates_enabled = {
            "retrieval_authority_filter": authority_enabled,
            "ui_gate_models": bool(ui_gate_models_raw) and ui_gate_models_raw not in {"0", "false", "no"},
            "ui_preselect_rules": str(env.get("GOLDEVIDENCEBENCH_UI_PRESELECT_RULES", "0")).lower()
            in {"1", "true", "yes"},
        }
        run_config = {
            "baseline": repro_metadata.get("baseline"),
            "adapter": repro_metadata.get("adapter"),
            "protocol": repro_metadata.get("protocol"),
            "state_mode": repro_metadata.get("state_mode"),
            "seed": repro_metadata.get("seed"),
            "steps": repro_metadata.get("steps"),
            "retrieval": repro_metadata.get("retrieval"),
            "config": repro_metadata.get("config"),
            "env": repro_metadata.get("env"),
            "data_path": (repro_metadata.get("config_paths") or {}).get("data_path"),
        }
        compact_path = run_dir / "compact_state.json"
        report_path = run_dir / "report.md"
        compact_state = compaction_mod.build_compact_state(
            run_dir=run_dir,
            summary=summary,
            diagnosis=diagnosis,
            context_keys=context_keys,
            thresholds=thresholds,
            report_path=report_path,
            run_config=run_config,
            gates_enabled=gates_enabled,
            rerank_mode=rerank_mode,
            authority_mode="filter_on" if authority_enabled else "filter_off",
        )
        compaction_mod.write_compact_state(compact_path, compact_state)
        reporting_mod.generate_report(
            summary_path=args.out_json,
            diagnosis_path=diagnosis_path,
            compact_state_path=compact_path,
            out_path=report_path,
            thresholds_path=thresholds_path,
        )
        thread_path = run_dir / "thread.jsonl"
        input_ref = _relpath(args.input_path, run_dir)
        thread_log_mod.append_event(
            thread_path,
            thread_log_mod.build_event(
                run_id=run_dir.name or str(run_dir),
                step=0,
                event_type="plan",
                inputs_ref=_relpath(repro_path, run_dir),
                notes="start_marker",
            ),
        )
        thread_log_mod.append_event(
            thread_path,
            thread_log_mod.build_event(
                run_id=run_dir.name or str(run_dir),
                step=1,
                event_type="observation",
                inputs_ref=input_ref,
                outputs_ref=_relpath(args.out_json, run_dir),
                notes="summary written",
            ),
        )
        thread_log_mod.append_event(
            thread_path,
            thread_log_mod.build_event(
                run_id=run_dir.name or str(run_dir),
                step=2,
                event_type="tool",
                inputs_ref=_relpath(args.out_json, run_dir),
                outputs_ref=_relpath(diagnosis_path, run_dir),
                notes="diagnosis written",
            ),
        )
        thread_log_mod.append_event(
            thread_path,
            thread_log_mod.build_event(
                run_id=run_dir.name or str(run_dir),
                step=3,
                event_type="summary",
                inputs_ref=_relpath(args.out_json, run_dir),
                outputs_ref=_relpath(compact_path, run_dir),
                notes="compact state snapshot",
            ),
        )
        thread_log_mod.append_event(
            thread_path,
            thread_log_mod.build_event(
                run_id=run_dir.name or str(run_dir),
                step=4,
                event_type="summary",
                inputs_ref=_relpath(compact_path, run_dir),
                outputs_ref=_relpath(report_path, run_dir),
                notes="report generated",
            ),
        )
        thread_log_mod.append_event(
            thread_path,
            thread_log_mod.build_event(
                run_id=run_dir.name or str(run_dir),
                step=5,
                event_type="summary",
                outputs_ref=_relpath(report_path, run_dir),
                notes="end_marker",
            ),
        )
        errors = compaction_mod.validate_compaction_artifacts(
            run_dir=run_dir,
            compact_state=compact_state,
            thread_path=thread_path,
            report_path=report_path,
        )
        if errors:
            for error in errors:
                print(f"Compaction invariant failed: {error}")
            return 1
    print(f"Wrote {args.out_csv} and {args.out_json}")
    for line in diagnosis_mod.format_diagnosis_summary(diagnosis):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
