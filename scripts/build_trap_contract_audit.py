from __future__ import annotations

import argparse
import glob
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a trap-contract audit scoreboard from trap-on/off run artifacts."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/trap_contract_audit_jobs.json"),
        help="Trap audit config JSON path.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Root path used for relative glob patterns.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("runs/trap_contract_audit_latest.json"),
        help="Output JSON path.",
    )
    parser.add_argument(
        "--markdown-out",
        type=Path,
        default=Path("runs/trap_contract_audit_latest.md"),
        help="Output markdown path.",
    )
    parser.add_argument(
        "--fail-on-no-data",
        action="store_true",
        help="Return non-zero if overall status is NO_DATA.",
    )
    return parser.parse_args()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object JSON at {path}")
    return payload


def _get_path(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None
    return current


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _evaluate_rule(payload: dict[str, Any], rule: dict[str, Any]) -> tuple[bool, str]:
    path = str(rule.get("path") or "").strip()
    if not path:
        return False, "missing_path"
    actual = _get_path(payload, path)
    if "eq" in rule:
        expected = rule.get("eq")
        return actual == expected, f"{path} == {expected!r}"
    if "ne" in rule:
        expected = rule.get("ne")
        return actual != expected, f"{path} != {expected!r}"
    numeric = _as_float(actual)
    if numeric is None:
        return False, f"{path} non_numeric"
    if "min" in rule:
        minimum = float(rule.get("min"))
        return numeric >= minimum, f"{path} >= {minimum}"
    if "max" in rule:
        maximum = float(rule.get("max"))
        return numeric <= maximum, f"{path} <= {maximum}"
    return False, "unsupported_rule"


def _passes_filters(payload: dict[str, Any], filters: list[dict[str, Any]]) -> bool:
    for item in filters:
        if not isinstance(item, dict):
            return False
        passed, _ = _evaluate_rule(payload, item)
        if not passed:
            return False
    return True


def _resolve_glob_paths(*, root: Path, pattern: str, latest: int) -> list[Path]:
    if not pattern.strip():
        return []
    target = Path(pattern)
    full_pattern = str(target if target.is_absolute() else (root / target))
    paths = [Path(match) for match in glob.glob(full_pattern, recursive=True)]
    existing = [path for path in paths if path.is_file()]
    existing.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    if latest > 0:
        return existing[:latest]
    return existing


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _stddev(values: list[float]) -> float | None:
    if len(values) < 2:
        return 0.0 if values else None
    mu = _mean(values)
    if mu is None:
        return None
    variance = sum((value - mu) ** 2 for value in values) / len(values)
    return math.sqrt(variance)


def _aggregate(values: list[float], mode: str) -> float | None:
    if not values:
        return None
    mode_n = mode.strip().lower()
    if mode_n == "latest":
        return values[0]
    if mode_n == "mean":
        return _mean(values)
    if mode_n == "min":
        return min(values)
    if mode_n == "max":
        return max(values)
    return None


def _status_from_checks(checks: dict[str, str]) -> str:
    values = list(checks.values())
    if any(value == "FAIL" for value in values):
        return "FAIL"
    if any(value == "NO_DATA" for value in values):
        return "NO_DATA"
    return "PASS"


@dataclass
class ConditionStats:
    n: int
    expected_met_count: int
    expected_met_rate: float | None
    metric_mean: float | None
    metric_stddev: float | None
    run_paths: list[str]


def _condition_stats(records: list[dict[str, Any]]) -> ConditionStats:
    n = len(records)
    expected_met = [1.0 if bool(item.get("expected_met")) else 0.0 for item in records]
    metrics = [value for value in (_as_float(item.get("metric")) for item in records) if value is not None]
    rate = _mean(expected_met)
    run_paths = [str(item.get("path") or "") for item in records]
    return ConditionStats(
        n=n,
        expected_met_count=int(sum(expected_met)),
        expected_met_rate=rate,
        metric_mean=_mean(metrics),
        metric_stddev=_stddev(metrics),
        run_paths=run_paths,
    )


def _load_release_family_ids(contract_path: Path) -> list[str]:
    payload = _read_json(contract_path)
    strict_release = payload.get("strict_release")
    if not isinstance(strict_release, dict):
        return []
    rows = strict_release.get("required_reliability_families")
    if not isinstance(rows, list):
        return []
    out: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        family_id = str(row.get("id") or "").strip()
        if family_id:
            out.append(family_id)
    return out


def _build_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Trap Contract Audit")
    lines.append("")
    lines.append(f"- generated_at: `{payload['generated_at_utc']}`")
    lines.append(f"- status: `{payload['status']}`")
    lines.append(f"- config: `{payload['config_path']}`")
    lines.append("")
    summary = payload.get("summary", {})
    lines.append(
        f"- traps: total={summary.get('trap_count', 0)} "
        f"pass={summary.get('pass_count', 0)} "
        f"fail={summary.get('fail_count', 0)} "
        f"no_data={summary.get('no_data_count', 0)}"
    )
    lines.append("")
    lines.append("| Trap | Status | Check1 | Check2 | Check3 | Check4 | Check5 |")
    lines.append("|---|---|---|---|---|---|---|")
    for trap in payload.get("traps", []):
        checks = trap.get("checks", {})
        lines.append(
            "| `{id}` | {status} | {c1} | {c2} | {c3} | {c4} | {c5} |".format(
                id=trap.get("id"),
                status=trap.get("status"),
                c1=checks.get("off_fails_on_passes", "NO_DATA"),
                c2=checks.get("effect_size", "NO_DATA"),
                c3=checks.get("run_stability", "NO_DATA"),
                c4=checks.get("adapter_coverage", "NO_DATA"),
                c5=checks.get("collateral_regression", "NO_DATA"),
            )
        )
    lines.append("")
    for trap in payload.get("traps", []):
        lines.append(f"## {trap.get('id')}")
        lines.append(f"- status: `{trap.get('status')}`")
        description = str(trap.get("description") or "").strip()
        if description:
            lines.append(f"- description: {description}")
        lines.append("- checks:")
        checks = trap.get("checks", {})
        lines.append(f"  - off_fails_on_passes: `{checks.get('off_fails_on_passes', 'NO_DATA')}`")
        lines.append(f"  - effect_size: `{checks.get('effect_size', 'NO_DATA')}`")
        lines.append(f"  - run_stability: `{checks.get('run_stability', 'NO_DATA')}`")
        lines.append(f"  - adapter_coverage: `{checks.get('adapter_coverage', 'NO_DATA')}`")
        lines.append(f"  - collateral_regression: `{checks.get('collateral_regression', 'NO_DATA')}`")
        adapters = trap.get("adapters", [])
        if adapters:
            lines.append("- adapters:")
            for adapter_row in adapters:
                on = adapter_row.get("on", {})
                off = adapter_row.get("off", {})
                lines.append(
                    "  - `{adapter}`: on_rate={on_rate}, off_rate={off_rate}, "
                    "on_n={on_n}, off_n={off_n}, adapter_pass={pass_status}".format(
                        adapter=adapter_row.get("adapter"),
                        on_rate=on.get("expected_met_rate"),
                        off_rate=off.get("expected_met_rate"),
                        on_n=on.get("n"),
                        off_n=off.get("n"),
                        pass_status=adapter_row.get("adapter_pass"),
                    )
                )
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    ns = _parse_args()
    config = _read_json(ns.config)
    defaults = config.get("defaults") if isinstance(config.get("defaults"), dict) else {}
    traps_cfg = config.get("traps")
    if not isinstance(traps_cfg, list):
        raise SystemExit("Config must contain a 'traps' list.")

    include_release = config.get("include_release_families")
    if isinstance(include_release, dict) and bool(include_release.get("enabled", False)):
        contract_rel = str(include_release.get("contract_path") or "configs/release_gate_contract.json")
        contract_path = Path(contract_rel)
        if not contract_path.is_absolute():
            contract_path = ns.root / contract_path
        release_ids = _load_release_family_ids(contract_path)
        existing = {str(item.get("id") or "").strip() for item in traps_cfg if isinstance(item, dict)}
        for family_id in release_ids:
            if family_id in existing:
                continue
            traps_cfg.append(
                {
                    "id": family_id,
                    "description": "No trap audit cells configured for this release family yet.",
                    "cells": [],
                }
            )

    trap_rows: list[dict[str, Any]] = []
    pass_ids: list[str] = []
    fail_ids: list[str] = []
    no_data_ids: list[str] = []

    for trap in traps_cfg:
        if not isinstance(trap, dict):
            continue
        trap_id = str(trap.get("id") or "").strip()
        if not trap_id:
            continue
        trap_desc = str(trap.get("description") or "").strip()
        trap_thresholds = dict(defaults)
        if isinstance(trap.get("thresholds"), dict):
            trap_thresholds.update(trap.get("thresholds"))

        min_on_expected_rate = float(trap_thresholds.get("min_on_expected_rate", 0.9))
        min_off_expected_rate = float(trap_thresholds.get("min_off_expected_rate", 0.9))
        min_runs_per_condition = int(trap_thresholds.get("min_runs_per_condition", 3))
        max_on_score_stddev = float(trap_thresholds.get("max_on_score_stddev", 0.15))
        max_off_score_stddev = float(trap_thresholds.get("max_off_score_stddev", 0.15))
        min_adapter_pass_count = int(trap_thresholds.get("min_adapter_pass_count", 1))

        cells = trap.get("cells")
        if not isinstance(cells, list):
            cells = []

        records_by_adapter_condition: dict[str, dict[str, list[dict[str, Any]]]] = {}
        pooled_by_condition: dict[str, list[dict[str, Any]]] = {"on": [], "off": []}

        for cell in cells:
            if not isinstance(cell, dict):
                continue
            condition = str(cell.get("condition") or "").strip().lower()
            if condition not in {"on", "off"}:
                continue
            adapter = str(cell.get("adapter") or "default").strip()
            path_glob = str(cell.get("path_glob") or "").strip()
            if not path_glob:
                continue
            latest = int(cell.get("latest", 10))
            score_path = str(cell.get("metric_path") or "").strip()
            filters = cell.get("filters")
            filter_items = [item for item in filters if isinstance(item, dict)] if isinstance(filters, list) else []

            expectation = cell.get("expect")
            if not isinstance(expectation, dict):
                expectation = {"path": "status", "eq": "PASS"}

            for artifact_path in _resolve_glob_paths(root=ns.root, pattern=path_glob, latest=latest):
                try:
                    payload = _read_json(artifact_path)
                except Exception:
                    continue
                if filter_items and not _passes_filters(payload, filter_items):
                    continue
                expected_met, expectation_note = _evaluate_rule(payload, expectation)
                metric: float | None = None
                if score_path:
                    metric = _as_float(_get_path(payload, score_path))
                if metric is None:
                    metric = 1.0 if expected_met else 0.0
                entry = {
                    "path": str(artifact_path),
                    "expected_met": expected_met,
                    "expectation_note": expectation_note,
                    "metric": metric,
                    "payload": payload,
                }
                records_by_adapter_condition.setdefault(adapter, {"on": [], "off": []})
                records_by_adapter_condition[adapter][condition].append(entry)
                pooled_by_condition[condition].append(entry)

        pooled_on = _condition_stats(pooled_by_condition["on"])
        pooled_off = _condition_stats(pooled_by_condition["off"])

        check1_status = "NO_DATA"
        check1_detail = {
            "on_expected_rate": pooled_on.expected_met_rate,
            "off_expected_rate": pooled_off.expected_met_rate,
            "on_n": pooled_on.n,
            "off_n": pooled_off.n,
            "min_on_expected_rate": min_on_expected_rate,
            "min_off_expected_rate": min_off_expected_rate,
        }
        if pooled_on.n >= min_runs_per_condition and pooled_off.n >= min_runs_per_condition:
            on_ok = (pooled_on.expected_met_rate or 0.0) >= min_on_expected_rate
            off_ok = (pooled_off.expected_met_rate or 0.0) >= min_off_expected_rate
            check1_status = "PASS" if (on_ok and off_ok) else "FAIL"

        effect_cfg = trap.get("effect_check")
        check2_status = "NO_DATA"
        check2_detail: dict[str, Any] = {}
        if isinstance(effect_cfg, dict):
            on_path = str(effect_cfg.get("on_metric_path") or "").strip()
            off_path = str(effect_cfg.get("off_metric_path") or "").strip()
            direction = str(effect_cfg.get("direction") or "off_minus_on").strip().lower()
            min_delta = float(effect_cfg.get("min_delta", 0.0))
            aggregate_mode = str(effect_cfg.get("aggregate") or "mean")

            on_values = [
                _as_float(_get_path(item["payload"], on_path))
                for item in pooled_by_condition["on"]
            ]
            on_values = [value for value in on_values if value is not None]
            off_values = [
                _as_float(_get_path(item["payload"], off_path))
                for item in pooled_by_condition["off"]
            ]
            off_values = [value for value in off_values if value is not None]
            on_metric = _aggregate(on_values, aggregate_mode)
            off_metric = _aggregate(off_values, aggregate_mode)
            check2_detail = {
                "on_metric": on_metric,
                "off_metric": off_metric,
                "direction": direction,
                "min_delta": min_delta,
                "aggregate": aggregate_mode,
            }
            if on_metric is not None and off_metric is not None:
                if direction == "on_minus_off":
                    delta = on_metric - off_metric
                else:
                    delta = off_metric - on_metric
                check2_detail["delta"] = delta
                check2_status = "PASS" if delta >= min_delta else "FAIL"

        check3_status = "NO_DATA"
        check3_detail = {
            "on_metric_stddev": pooled_on.metric_stddev,
            "off_metric_stddev": pooled_off.metric_stddev,
            "on_n": pooled_on.n,
            "off_n": pooled_off.n,
            "max_on_score_stddev": max_on_score_stddev,
            "max_off_score_stddev": max_off_score_stddev,
        }
        if pooled_on.n >= min_runs_per_condition and pooled_off.n >= min_runs_per_condition:
            on_std = pooled_on.metric_stddev
            off_std = pooled_off.metric_stddev
            if on_std is not None and off_std is not None:
                check3_status = (
                    "PASS"
                    if (on_std <= max_on_score_stddev and off_std <= max_off_score_stddev)
                    else "FAIL"
                )

        adapter_rows: list[dict[str, Any]] = []
        adapter_pass_count = 0
        for adapter_name in sorted(records_by_adapter_condition):
            adapter_records = records_by_adapter_condition[adapter_name]
            on_stats = _condition_stats(adapter_records.get("on", []))
            off_stats = _condition_stats(adapter_records.get("off", []))
            local_check1 = "NO_DATA"
            local_check2 = "NO_DATA"
            local_check3 = "NO_DATA"
            if on_stats.n >= min_runs_per_condition and off_stats.n >= min_runs_per_condition:
                on_ok = (on_stats.expected_met_rate or 0.0) >= min_on_expected_rate
                off_ok = (off_stats.expected_met_rate or 0.0) >= min_off_expected_rate
                local_check1 = "PASS" if (on_ok and off_ok) else "FAIL"
                on_std = on_stats.metric_stddev
                off_std = off_stats.metric_stddev
                if on_std is not None and off_std is not None:
                    local_check3 = (
                        "PASS"
                        if (on_std <= max_on_score_stddev and off_std <= max_off_score_stddev)
                        else "FAIL"
                    )
            if isinstance(effect_cfg, dict):
                on_path = str(effect_cfg.get("on_metric_path") or "").strip()
                off_path = str(effect_cfg.get("off_metric_path") or "").strip()
                direction = str(effect_cfg.get("direction") or "off_minus_on").strip().lower()
                min_delta = float(effect_cfg.get("min_delta", 0.0))
                aggregate_mode = str(effect_cfg.get("aggregate") or "mean")
                on_values = [
                    _as_float(_get_path(item["payload"], on_path))
                    for item in adapter_records.get("on", [])
                ]
                on_values = [value for value in on_values if value is not None]
                off_values = [
                    _as_float(_get_path(item["payload"], off_path))
                    for item in adapter_records.get("off", [])
                ]
                off_values = [value for value in off_values if value is not None]
                on_metric = _aggregate(on_values, aggregate_mode)
                off_metric = _aggregate(off_values, aggregate_mode)
                if on_metric is not None and off_metric is not None:
                    delta = (on_metric - off_metric) if direction == "on_minus_off" else (off_metric - on_metric)
                    local_check2 = "PASS" if delta >= min_delta else "FAIL"
            adapter_pass = local_check1 == "PASS" and local_check2 == "PASS" and local_check3 == "PASS"
            if adapter_pass:
                adapter_pass_count += 1
            adapter_rows.append(
                {
                    "adapter": adapter_name,
                    "on": {
                        "n": on_stats.n,
                        "expected_met_count": on_stats.expected_met_count,
                        "expected_met_rate": on_stats.expected_met_rate,
                        "metric_mean": on_stats.metric_mean,
                        "metric_stddev": on_stats.metric_stddev,
                    },
                    "off": {
                        "n": off_stats.n,
                        "expected_met_count": off_stats.expected_met_count,
                        "expected_met_rate": off_stats.expected_met_rate,
                        "metric_mean": off_stats.metric_mean,
                        "metric_stddev": off_stats.metric_stddev,
                    },
                    "check_status": {
                        "off_fails_on_passes": local_check1,
                        "effect_size": local_check2,
                        "run_stability": local_check3,
                    },
                    "adapter_pass": adapter_pass,
                }
            )

        check4_status = "NO_DATA"
        check4_detail = {
            "adapter_pass_count": adapter_pass_count,
            "min_adapter_pass_count": min_adapter_pass_count,
            "adapter_count": len(adapter_rows),
        }
        if adapter_rows:
            check4_status = "PASS" if adapter_pass_count >= min_adapter_pass_count else "FAIL"

        collateral_checks = trap.get("collateral_checks")
        collateral_rows: list[dict[str, Any]] = []
        check5_status = "PASS"
        if isinstance(collateral_checks, list) and collateral_checks:
            check5_status = "PASS"
            any_data = False
            for rule in collateral_checks:
                if not isinstance(rule, dict):
                    continue
                rule_id = str(rule.get("id") or "collateral").strip()
                aggregate_mode = str(rule.get("aggregate") or "mean").strip().lower()
                metric_path = str(rule.get("path") or "").strip()
                values: list[float] = []
                source_note = ""
                if rule.get("condition") in {"on", "off"}:
                    condition = str(rule.get("condition"))
                    for item in pooled_by_condition[condition]:
                        numeric = _as_float(_get_path(item["payload"], metric_path))
                        if numeric is not None:
                            values.append(numeric)
                    source_note = f"condition:{condition}"
                else:
                    path_glob = str(rule.get("path_glob") or "").strip()
                    latest = int(rule.get("latest", 5))
                    filters = rule.get("filters")
                    filter_items = [item for item in filters if isinstance(item, dict)] if isinstance(filters, list) else []
                    for artifact_path in _resolve_glob_paths(root=ns.root, pattern=path_glob, latest=latest):
                        try:
                            payload = _read_json(artifact_path)
                        except Exception:
                            continue
                        if filter_items and not _passes_filters(payload, filter_items):
                            continue
                        numeric = _as_float(_get_path(payload, metric_path))
                        if numeric is not None:
                            values.append(numeric)
                    source_note = f"glob:{path_glob}"

                aggregate_value = _aggregate(values, aggregate_mode)
                row_status = "NO_DATA"
                if aggregate_value is not None:
                    any_data = True
                    row_status = "PASS"
                    if "min" in rule and aggregate_value < float(rule.get("min")):
                        row_status = "FAIL"
                    if "max" in rule and aggregate_value > float(rule.get("max")):
                        row_status = "FAIL"
                collateral_rows.append(
                    {
                        "id": rule_id,
                        "status": row_status,
                        "source": source_note,
                        "metric_path": metric_path,
                        "aggregate": aggregate_mode,
                        "value": aggregate_value,
                        "min": rule.get("min"),
                        "max": rule.get("max"),
                    }
                )
            if any(row.get("status") == "FAIL" for row in collateral_rows):
                check5_status = "FAIL"
            elif any(row.get("status") == "NO_DATA" for row in collateral_rows):
                check5_status = "NO_DATA"
            elif not any_data:
                check5_status = "NO_DATA"

        checks = {
            "off_fails_on_passes": check1_status,
            "effect_size": check2_status,
            "run_stability": check3_status,
            "adapter_coverage": check4_status,
            "collateral_regression": check5_status,
        }
        trap_status = _status_from_checks(checks)
        if trap_status == "PASS":
            pass_ids.append(trap_id)
        elif trap_status == "NO_DATA":
            no_data_ids.append(trap_id)
        else:
            fail_ids.append(trap_id)

        trap_rows.append(
            {
                "id": trap_id,
                "description": trap_desc,
                "status": trap_status,
                "thresholds": {
                    "min_on_expected_rate": min_on_expected_rate,
                    "min_off_expected_rate": min_off_expected_rate,
                    "min_runs_per_condition": min_runs_per_condition,
                    "max_on_score_stddev": max_on_score_stddev,
                    "max_off_score_stddev": max_off_score_stddev,
                    "min_adapter_pass_count": min_adapter_pass_count,
                },
                "checks": checks,
                "check_details": {
                    "off_fails_on_passes": check1_detail,
                    "effect_size": check2_detail,
                    "run_stability": check3_detail,
                    "adapter_coverage": check4_detail,
                    "collateral_regression": collateral_rows,
                },
                "pooled": {
                    "on": {
                        "n": pooled_on.n,
                        "expected_met_count": pooled_on.expected_met_count,
                        "expected_met_rate": pooled_on.expected_met_rate,
                        "metric_mean": pooled_on.metric_mean,
                        "metric_stddev": pooled_on.metric_stddev,
                        "run_paths": pooled_on.run_paths,
                    },
                    "off": {
                        "n": pooled_off.n,
                        "expected_met_count": pooled_off.expected_met_count,
                        "expected_met_rate": pooled_off.expected_met_rate,
                        "metric_mean": pooled_off.metric_mean,
                        "metric_stddev": pooled_off.metric_stddev,
                        "run_paths": pooled_off.run_paths,
                    },
                },
                "adapters": adapter_rows,
            }
        )

    status = "PASS"
    if fail_ids:
        status = "FAIL"
    elif no_data_ids:
        status = "NO_DATA"

    payload = {
        "benchmark": "trap_contract_audit",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "config_path": str(ns.config),
        "summary": {
            "trap_count": len(trap_rows),
            "pass_count": len(pass_ids),
            "fail_count": len(fail_ids),
            "no_data_count": len(no_data_ids),
            "passed_traps": pass_ids,
            "failed_traps": fail_ids,
            "no_data_traps": no_data_ids,
        },
        "traps": trap_rows,
    }

    ns.out.parent.mkdir(parents=True, exist_ok=True)
    ns.markdown_out.parent.mkdir(parents=True, exist_ok=True)
    ns.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    ns.markdown_out.write_text(_build_markdown(payload), encoding="utf-8")
    print(f"Wrote {ns.out}")
    print(f"Wrote {ns.markdown_out}")
    print(f"trap_contract_audit status={status} traps={len(trap_rows)}")

    if status == "FAIL":
        return 1
    if status == "NO_DATA" and ns.fail_on_no_data:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

