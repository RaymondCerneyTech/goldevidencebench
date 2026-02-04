from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from goldevidencebench import schema_validation

SCHEMA_VERSION = "1"
ARTIFACT_VERSION = "1.0.0"


def _iso_timestamp(ts: datetime | None = None) -> str:
    now = ts or datetime.now(timezone.utc)
    return now.isoformat()


def _relpath(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def _format_constraints(thresholds: dict[str, float] | None) -> list[str]:
    if not thresholds:
        return []
    mapping = [
        ("unsafe_commit_rate", "<=", "unsafe_commit_rate"),
        ("flip_rate", "<=", "flip_rate"),
        ("gold_present_rate", ">=", "gold_present_rate"),
        ("selection_rate_given_present", ">=", "selection_rate_given_present"),
        ("authority_violation_rate", "<=", "authority_violation_rate"),
        ("answer_correct_given_selected", ">=", "answer_correct_given_selected"),
        ("drift.step_rate", "<=", "drift_step_rate_max"),
    ]
    constraints: list[str] = []
    for label, op, key in mapping:
        value = thresholds.get(key)
        if value is None:
            continue
        constraints.append(f"{label} {op} {value}")
    return constraints


def _build_verified_facts(
    summary: dict[str, Any],
    diagnosis: dict[str, Any],
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    status = diagnosis.get("status")
    if status is not None:
        facts.append(
            {
                "key": "diagnosis.status",
                "value": status,
                "provenance": "diagnosis.json",
            }
        )
    bottleneck = diagnosis.get("primary_bottleneck")
    if bottleneck is not None:
        facts.append(
            {
                "key": "diagnosis.primary_bottleneck",
                "value": bottleneck,
                "provenance": "diagnosis.json",
            }
        )
    holdout_name = diagnosis.get("holdout_name")
    if holdout_name:
        facts.append(
            {
                "key": "holdout_name",
                "value": holdout_name,
                "provenance": "diagnosis.json",
            }
        )
    drift = summary.get("drift", {}).get("step_rate")
    if drift is not None:
        facts.append(
            {
                "key": "drift.step_rate",
                "value": drift,
                "provenance": "summary.json",
            }
        )
    return facts


def _find_gate_artifacts(run_dir: Path) -> list[str]:
    patterns = ["*gate*.json", "*wall*.json", "*distillation*.json"]
    artifacts: list[str] = []
    for pattern in patterns:
        for path in run_dir.glob(pattern):
            if path.name in {"summary.json", "diagnosis.json", "compact_state.json"}:
                continue
            artifacts.append(_relpath(path, run_dir))
    return sorted(set(artifacts))


def _hash_context_keys(context_keys: Iterable[str]) -> str:
    joined = "\n".join(sorted({str(key) for key in context_keys if key}))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def build_compact_state(
    *,
    run_dir: Path,
    summary: dict[str, Any],
    diagnosis: dict[str, Any],
    context_keys: Iterable[str],
    thresholds: dict[str, float] | None = None,
    current_goal: str | None = None,
    report_path: Path | None = None,
    run_config: dict[str, Any] | None = None,
    gates_enabled: dict[str, Any] | None = None,
    rerank_mode: str | None = None,
    authority_mode: str | None = None,
) -> dict[str, Any]:
    run_id = run_dir.name or str(run_dir)
    if current_goal is None:
        holdout = diagnosis.get("holdout_name")
        current_goal = f"Evaluate holdout {holdout}" if holdout else "Summarize run results"
    report_ref = _relpath(report_path, run_dir) if report_path else "report.md"
    current_context_keys = sorted({str(k) for k in context_keys if k})
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_version": ARTIFACT_VERSION,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "updated_at": _iso_timestamp(),
        "current_goal": current_goal,
        "constraints": _format_constraints(thresholds),
        "verified_facts": _build_verified_facts(summary, diagnosis),
        "open_questions": diagnosis.get("required_inputs_next_run") or [],
        "run_config": run_config or {},
        "gates_enabled": gates_enabled or {},
        "rerank_mode": rerank_mode,
        "authority_mode": authority_mode,
        "last_known_good": {
            "summary": _relpath(run_dir / "summary.json", run_dir),
            "diagnosis": _relpath(run_dir / "diagnosis.json", run_dir),
            "report": report_ref,
            "gate_artifacts": _find_gate_artifacts(run_dir),
        },
        "current_context_keys": current_context_keys,
        "context_keys_digest": _hash_context_keys(current_context_keys),
    }


def write_compact_state(path: Path, state: dict[str, Any]) -> None:
    schema_path = schema_validation.schema_path("compact_state.schema.json")
    schema_validation.validate_or_raise(state, schema_path)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=True), encoding="utf-8")


def validate_compaction_artifacts(
    *,
    run_dir: Path,
    compact_state: dict[str, Any],
    thread_path: Path,
    report_path: Path,
) -> list[str]:
    errors: list[str] = []
    required_fields = [
        "schema_version",
        "artifact_version",
        "run_config",
        "gates_enabled",
        "rerank_mode",
        "authority_mode",
        "current_context_keys",
        "context_keys_digest",
    ]
    for field in required_fields:
        if field not in compact_state:
            errors.append(f"compact_state missing '{field}'")

    if not thread_path.exists():
        errors.append("thread.jsonl missing")
    else:
        start_marker = False
        end_marker = False
        has_observation = False
        has_action = False
        schema_path = schema_validation.schema_path("thread_event.schema.json")
        for line_num, line in enumerate(thread_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                errors.append("thread.jsonl has invalid JSON line")
                break
            event_errors = schema_validation.validate_artifact(event, schema_path)
            for err in event_errors:
                errors.append(f"thread.jsonl line {line_num}: {err}")
            notes = event.get("notes")
            event_type = event.get("type")
            if notes == "start_marker":
                start_marker = True
            if notes == "end_marker":
                end_marker = True
            if event_type == "observation":
                has_observation = True
            if event_type in {"tool", "decision"}:
                has_action = True
        if not start_marker:
            errors.append("thread.jsonl missing start_marker")
        if not end_marker:
            errors.append("thread.jsonl missing end_marker")
        if not has_observation or not has_action:
            errors.append("thread.jsonl missing observation/action pair")

    if not report_path.exists():
        errors.append("report.md missing")
    else:
        report_text = report_path.read_text(encoding="utf-8")
        for entry in ["- summary.json", "- diagnosis.json", "- compact_state.json", "- thread.jsonl", "- report.md"]:
            if entry not in report_text:
                errors.append(f"report.md missing reference {entry}")
                break

    return errors
