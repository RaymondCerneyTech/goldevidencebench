from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CoreBenchmarkFixture:
    fixture_id: str
    label: str
    failure_mode: str
    fixture_path: str
    observed_path: str


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _mean(values: list[float | None]) -> float | None:
    cleaned = [value for value in values if isinstance(value, (int, float))]
    if not cleaned:
        return None
    return sum(cleaned) / len(cleaned)


def _extract_task_pass_rate(payload: dict[str, Any], strategy: str) -> float | None:
    block = payload.get(strategy)
    if isinstance(block, dict):
        seq = block.get("sequence_metrics")
        if isinstance(seq, dict):
            value = seq.get("task_pass_rate")
            if isinstance(value, (int, float)):
                return float(value)
    summary = payload.get("strategy_summary")
    if isinstance(summary, dict):
        strat = summary.get(strategy)
        if isinstance(strat, dict):
            value = strat.get("task_pass_rate")
            if isinstance(value, (int, float)):
                return float(value)
    return None


def _extract_state_gate_rate(payload: dict[str, Any], strategy: str) -> float | None:
    block = payload.get(strategy)
    if isinstance(block, dict):
        gate = block.get("state_gate")
        if isinstance(gate, dict):
            value = gate.get("state_gate_pass_rate")
            if isinstance(value, (int, float)):
                return float(value)
    return None


def load_core_benchmark_config(path: Path) -> list[CoreBenchmarkFixture]:
    payload = _load_json(path)
    fixtures = payload.get("fixtures")
    if not isinstance(fixtures, list):
        raise ValueError("core benchmark config missing fixtures list")
    loaded: list[CoreBenchmarkFixture] = []
    for entry in fixtures:
        if not isinstance(entry, dict):
            continue
        fixture_id = entry.get("id")
        fixture_path = entry.get("fixture")
        observed_path = entry.get("observed")
        if not isinstance(fixture_id, str) or not isinstance(fixture_path, str):
            continue
        loaded.append(
            CoreBenchmarkFixture(
                fixture_id=fixture_id,
                label=str(entry.get("label", fixture_id)),
                failure_mode=str(entry.get("failure_mode", "")),
                fixture_path=fixture_path,
                observed_path=str(observed_path or ""),
            )
        )
    if not loaded:
        raise ValueError("core benchmark config contains no valid fixtures")
    return loaded


def summarize_core_benchmark(config_path: Path, runs_dir: Path) -> dict[str, Any]:
    fixtures = load_core_benchmark_config(config_path)
    results: list[dict[str, Any]] = []
    missing: list[str] = []
    policy_rates: list[float | None] = []
    greedy_rates: list[float | None] = []
    sa_rates: list[float | None] = []
    state_gate_rates: list[float | None] = []

    for fixture in fixtures:
        result_path = runs_dir / f"bench_{fixture.fixture_id}.json"
        if not result_path.exists():
            missing.append(fixture.fixture_id)
            results.append(
                {
                    "id": fixture.fixture_id,
                    "label": fixture.label,
                    "failure_mode": fixture.failure_mode,
                    "fixture": fixture.fixture_path,
                    "observed": fixture.observed_path,
                    "result_path": str(result_path),
                    "status": "missing",
                }
            )
            continue
        payload = _load_json(result_path)
        policy_rate = _extract_task_pass_rate(payload, "policy")
        greedy_rate = _extract_task_pass_rate(payload, "greedy")
        sa_rate = _extract_task_pass_rate(payload, "sa")
        state_gate_rate = _extract_state_gate_rate(payload, "policy")

        policy_rates.append(policy_rate)
        greedy_rates.append(greedy_rate)
        sa_rates.append(sa_rate)
        state_gate_rates.append(state_gate_rate)

        results.append(
            {
                "id": fixture.fixture_id,
                "label": fixture.label,
                "failure_mode": fixture.failure_mode,
                "fixture": fixture.fixture_path,
                "observed": fixture.observed_path,
                "result_path": str(result_path),
                "status": "ok",
                "policy_task_pass_rate": policy_rate,
                "greedy_task_pass_rate": greedy_rate,
                "sa_task_pass_rate": sa_rate,
                "policy_state_gate_pass_rate": state_gate_rate,
            }
        )

    generated_at = datetime.now(timezone.utc).isoformat()
    summary = {
        "artifact_version": "1.0",
        "benchmark": config_path.stem,
        "config_path": str(config_path),
        "runs_dir": str(runs_dir),
        "generated_at": generated_at,
        "fixtures_total": len(fixtures),
        "fixtures_with_results": len(fixtures) - len(missing),
        "missing": missing,
        "means": {
            "policy_task_pass_rate": _mean(policy_rates),
            "greedy_task_pass_rate": _mean(greedy_rates),
            "sa_task_pass_rate": _mean(sa_rates),
            "policy_state_gate_pass_rate": _mean(state_gate_rates),
        },
        "results": results,
    }
    return summary


def render_core_benchmark_report(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Core Benchmark Report")
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
    lines.append("")
    means = summary.get("means", {})
    lines.append("## Means")
    lines.append(
        f"- policy_task_pass_rate: {means.get('policy_task_pass_rate', 'n/a')}"
    )
    lines.append(
        f"- greedy_task_pass_rate: {means.get('greedy_task_pass_rate', 'n/a')}"
    )
    lines.append(f"- sa_task_pass_rate: {means.get('sa_task_pass_rate', 'n/a')}")
    lines.append(
        f"- policy_state_gate_pass_rate: {means.get('policy_state_gate_pass_rate', 'n/a')}"
    )
    lines.append("")
    lines.append("## Fixtures")
    lines.append("| ID | Label | Failure mode | Policy pass | Greedy pass | SA pass | Status |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for entry in summary.get("results", []):
        if not isinstance(entry, dict):
            continue
        lines.append(
            "| {id} | {label} | {failure} | {policy} | {greedy} | {sa} | {status} |".format(
                id=entry.get("id", ""),
                label=entry.get("label", ""),
                failure=entry.get("failure_mode", ""),
                policy=_fmt_rate(entry.get("policy_task_pass_rate")),
                greedy=_fmt_rate(entry.get("greedy_task_pass_rate")),
                sa=_fmt_rate(entry.get("sa_task_pass_rate")),
                status=entry.get("status", ""),
            )
        )
    lines.append("")
    missing = summary.get("missing") or []
    if missing:
        lines.append("## Missing results")
        for fixture_id in missing:
            lines.append(f"- {fixture_id}")
        lines.append("")
    failures = summary.get("failures") or []
    if failures:
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
