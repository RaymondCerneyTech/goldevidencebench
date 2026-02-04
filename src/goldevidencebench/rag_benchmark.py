from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from goldevidencebench.util import read_jsonl


@dataclass(frozen=True)
class RagBenchmarkDataset:
    dataset_id: str
    label: str
    failure_mode: str
    data_path: str


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _mean(values: list[float | None]) -> float | None:
    cleaned = [value for value in values if isinstance(value, (int, float))]
    if not cleaned:
        return None
    return sum(cleaned) / len(cleaned)


def _extract_metric(metrics: dict[str, Any], key: str) -> float | None:
    value = metrics.get(key)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _extract_float(payload: dict[str, Any], key: str) -> float | None:
    value = payload.get(key)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _norm_support_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    if isinstance(value, str):
        return [value]
    return []


def _load_gold_doc_ids(path: Path) -> dict[str, list[str]]:
    gold: dict[str, list[str]] = {}
    for row in read_jsonl(path):
        rid = row.get("id")
        if not rid:
            continue
        gold_ids = _norm_support_list(row.get("gold", {}).get("support_ids"))
        if not gold_ids:
            gold_ids = _norm_support_list(row.get("gold", {}).get("support_id"))
        if gold_ids:
            gold[str(rid)] = gold_ids
    return gold


def load_rag_benchmark_config(path: Path) -> list[RagBenchmarkDataset]:
    payload = _load_json(path)
    datasets = payload.get("datasets")
    if not isinstance(datasets, list):
        raise ValueError("rag benchmark config missing datasets list")
    loaded: list[RagBenchmarkDataset] = []
    for entry in datasets:
        if not isinstance(entry, dict):
            continue
        dataset_id = entry.get("id")
        data_path = entry.get("data")
        if not isinstance(dataset_id, str) or not isinstance(data_path, str):
            continue
        loaded.append(
            RagBenchmarkDataset(
                dataset_id=dataset_id,
                label=str(entry.get("label", dataset_id)),
                failure_mode=str(entry.get("failure_mode", "")),
                data_path=data_path,
            )
        )
    if not loaded:
        raise ValueError("rag benchmark config contains no valid datasets")
    return loaded


def summarize_rag_benchmark(config_path: Path, runs_dir: Path) -> dict[str, Any]:
    datasets = load_rag_benchmark_config(config_path)
    results: list[dict[str, Any]] = []
    missing: list[str] = []
    value_accs: list[float | None] = []
    exact_accs: list[float | None] = []
    entailment_rates: list[float | None] = []
    answer_corrects: list[float | None] = []
    cite_f1s: list[float | None] = []
    instruction_accs: list[float | None] = []
    state_integrity_rates: list[float | None] = []
    retrieval_hit_rates: list[float | None] = []
    wall_s_total = 0.0
    wall_s_per_q: list[float | None] = []
    tokens_per_q: list[float | None] = []

    for dataset in datasets:
        result_path = runs_dir / f"rag_{dataset.dataset_id}.json"
        if not result_path.exists():
            missing.append(dataset.dataset_id)
            results.append(
                {
                    "id": dataset.dataset_id,
                    "label": dataset.label,
                    "failure_mode": dataset.failure_mode,
                    "data": dataset.data_path,
                    "result_path": str(result_path),
                    "status": "missing",
                }
            )
            continue
        payload = _load_json(result_path)
        metrics = payload.get("metrics") or {}
        if not isinstance(metrics, dict):
            metrics = {}
        efficiency = payload.get("efficiency") or {}
        if not isinstance(efficiency, dict):
            efficiency = {}
        value_acc = _extract_metric(metrics, "value_acc")
        exact_acc = _extract_metric(metrics, "exact_acc")
        entailment = _extract_metric(metrics, "entailment")
        answer_correct_given_selected = _extract_metric(metrics, "answer_correct_given_selected")
        cite_f1 = _extract_metric(metrics, "cite_f1")
        instruction_acc = _extract_metric(metrics, "instruction_acc")
        state_integrity_rate = _extract_metric(metrics, "state_integrity_rate")
        instr_override_rate = _extract_metric(metrics, "instr_override_rate")
        wall_s = _extract_float(efficiency, "wall_s")
        wall_s_q = _extract_float(efficiency, "wall_s_per_q")
        tokens_q = _extract_float(efficiency, "tokens_per_q")
        if wall_s is not None:
            wall_s_total += wall_s
        wall_s_per_q.append(wall_s_q)
        tokens_per_q.append(tokens_q)

        retrieval_hit_rate = None
        retrieval_stats = payload.get("retrieval_stats")
        if isinstance(retrieval_stats, list):
            gold_map = _load_gold_doc_ids(Path(dataset.data_path))
            hits = 0
            total = 0
            for diag in retrieval_stats:
                if not isinstance(diag, dict):
                    continue
                rid = diag.get("id")
                top_ids = diag.get("top_ids")
                if not rid or not isinstance(top_ids, list):
                    continue
                gold_ids = gold_map.get(str(rid))
                if not gold_ids:
                    continue
                total += 1
                if any(doc_id in top_ids for doc_id in gold_ids):
                    hits += 1
            if total:
                retrieval_hit_rate = hits / total

        value_accs.append(value_acc)
        exact_accs.append(exact_acc)
        entailment_rates.append(entailment)
        answer_corrects.append(answer_correct_given_selected)
        cite_f1s.append(cite_f1)
        instruction_accs.append(instruction_acc)
        state_integrity_rates.append(state_integrity_rate)
        retrieval_hit_rates.append(retrieval_hit_rate)

        results.append(
            {
                "id": dataset.dataset_id,
                "label": dataset.label,
                "failure_mode": dataset.failure_mode,
                "data": dataset.data_path,
                "result_path": str(result_path),
                "status": "ok",
                "value_acc": value_acc,
                "exact_acc": exact_acc,
                "entailment": entailment,
                "answer_correct_given_selected": answer_correct_given_selected,
                "cite_f1": cite_f1,
                "instruction_acc": instruction_acc,
                "state_integrity_rate": state_integrity_rate,
                "instr_override_rate": instr_override_rate,
                "retrieval_hit_rate": retrieval_hit_rate,
                "wall_s": wall_s,
                "wall_s_per_q": wall_s_q,
                "tokens_per_q": tokens_q,
            }
        )

    generated_at = datetime.now(timezone.utc).isoformat()
    summary = {
        "artifact_version": "1.0",
        "benchmark": config_path.stem,
        "config_path": str(config_path),
        "runs_dir": str(runs_dir),
        "generated_at": generated_at,
        "datasets_total": len(datasets),
        "datasets_with_results": len(datasets) - len(missing),
        "missing": missing,
        "means": {
            "value_acc": _mean(value_accs),
            "exact_acc": _mean(exact_accs),
            "entailment": _mean(entailment_rates),
            "answer_correct_given_selected": _mean(answer_corrects),
            "cite_f1": _mean(cite_f1s),
            "instruction_acc": _mean(instruction_accs),
            "state_integrity_rate": _mean(state_integrity_rates),
            "retrieval_hit_rate": _mean(retrieval_hit_rates),
        },
        "runtime": {
            "wall_s_total": wall_s_total if wall_s_total else None,
            "wall_s_per_q": _mean(wall_s_per_q),
            "tokens_per_q": _mean(tokens_per_q),
        },
        "results": results,
    }
    return summary


def render_rag_benchmark_report(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# RAG Benchmark Report")
    lines.append("")
    lines.append(f"Runs dir: {summary.get('runs_dir')}")
    lines.append(f"Config: {summary.get('config_path')}")
    lines.append(f"Generated: {summary.get('generated_at')}")
    status = summary.get("status")
    if status:
        lines.append(f"Status: {status}")
    lines.append("")
    thresholds = summary.get("thresholds")
    if isinstance(thresholds, dict) and thresholds:
        lines.append("## Thresholds")
        for key, value in thresholds.items():
            lines.append(f"- {key}: {value}")
        lines.append("")
        lines.append("## Contract")
        contract_bits = []
        if thresholds.get("value_acc") is not None:
            contract_bits.append(f"value_acc >= {thresholds.get('value_acc')}")
        if thresholds.get("exact_acc") is not None:
            contract_bits.append(f"exact_acc >= {thresholds.get('exact_acc')}")
        if thresholds.get("entailment") is not None:
            contract_bits.append(f"entailment >= {thresholds.get('entailment')}")
        if thresholds.get("answer_correct_given_selected") is not None:
            contract_bits.append(
                "answer_correct_given_selected >= {0}".format(
                    thresholds.get("answer_correct_given_selected")
                )
            )
        if thresholds.get("cite_f1") is not None:
            contract_bits.append(f"cite_f1 >= {thresholds.get('cite_f1')}")
        if contract_bits:
            lines.append(f"PASS if all datasets meet: {', '.join(contract_bits)}.")
            lines.append("FAIL otherwise.")
        lines.append("")
    runtime = summary.get("runtime") or {}
    if isinstance(runtime, dict):
        lines.append("## Runtime")
        lines.append(f"- wall_s_total: {runtime.get('wall_s_total', 'n/a')}")
        lines.append(f"- wall_s_per_q: {runtime.get('wall_s_per_q', 'n/a')}")
        lines.append(f"- tokens_per_q: {runtime.get('tokens_per_q', 'n/a')}")
        lines.append("")
    lines.append("## Means")
    means = summary.get("means", {})
    lines.append(f"- value_acc: {means.get('value_acc', 'n/a')}")
    lines.append(f"- exact_acc: {means.get('exact_acc', 'n/a')}")
    lines.append(f"- entailment: {means.get('entailment', 'n/a')}")
    lines.append(f"- answer_correct_given_selected: {means.get('answer_correct_given_selected', 'n/a')}")
    lines.append(f"- cite_f1: {means.get('cite_f1', 'n/a')}")
    lines.append(f"- retrieval_hit_rate: {means.get('retrieval_hit_rate', 'n/a')}")
    lines.append(f"- instruction_acc: {means.get('instruction_acc', 'n/a')}")
    lines.append(f"- state_integrity_rate: {means.get('state_integrity_rate', 'n/a')}")
    lines.append("")
    lines.append("## Datasets")
    lines.append(
        "| ID | Label | Failure mode | value_acc | exact_acc | entailment | answer_correct | cite_f1 | retrieval_hit | wall_s_per_q | tokens_per_q | Status |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for entry in summary.get("results", []):
        if not isinstance(entry, dict):
            continue
        lines.append(
            "| {id} | {label} | {failure} | {value} | {exact} | {entailment} | {answer} | {cite} | {retrieval} | {wall} | {tokens} | {status} |".format(
                id=entry.get("id", ""),
                label=entry.get("label", ""),
                failure=entry.get("failure_mode", ""),
                value=_fmt_rate(entry.get("value_acc")),
                exact=_fmt_rate(entry.get("exact_acc")),
                entailment=_fmt_rate(entry.get("entailment")),
                answer=_fmt_rate(entry.get("answer_correct_given_selected")),
                cite=_fmt_rate(entry.get("cite_f1")),
                retrieval=_fmt_rate(entry.get("retrieval_hit_rate")),
                wall=_fmt_rate(entry.get("wall_s_per_q")),
                tokens=_fmt_rate(entry.get("tokens_per_q")),
                status=entry.get("status", ""),
            )
        )
    lines.append("")
    missing = summary.get("missing") or []
    if missing:
        lines.append("## Missing results")
        for dataset_id in missing:
            lines.append(f"- {dataset_id}")
        lines.append("")
    failures = summary.get("failures") or []
    if failures:
        top_failures = summary.get("top_failures") or []
        if top_failures:
            lines.append("## Top failing datasets")
            for entry in top_failures:
                if not isinstance(entry, dict):
                    continue
                lines.append(f"- {entry.get('id', '')}: {entry.get('count', 0)} failures")
            lines.append("")
        lines.append("## Threshold failures")
        for entry in failures:
            if not isinstance(entry, dict):
                continue
            lines.append(
                "- {id}: {reason}".format(
                    id=entry.get("id", ""),
                    reason=entry.get("reason", ""),
                )
            )
        lines.append("")
    return "\n".join(lines)


def _fmt_rate(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.4f}"
    return "n/a"
