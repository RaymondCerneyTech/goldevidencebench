from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from goldevidencebench import diagnosis as diagnosis_mod
from goldevidencebench.util import read_jsonl

STATUS_MAP = {
    "PASS": "PASS",
    "FAIL": "FAIL",
    "UNSTABLE": "WARN",
}


def _load_json(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        text = path.read_text(encoding="utf-8-sig")
        return json.loads(text)


def _format_metric(value: float | None, threshold: float | None, comparator: str) -> str:
    if value is None or threshold is None:
        return "n/a"
    status = "PASS" if _compare(value, threshold, comparator) else "FAIL"
    return f"{value:.4f} ({comparator} {threshold:.4f}) {status}"


def _compare(value: float, threshold: float, comparator: str) -> bool:
    if comparator == "<=":
        return value <= threshold
    if comparator == ">=":
        return value >= threshold
    return False


def _format_plain(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _find_decision_event(thread_path: Path, case_id: str | None) -> dict[str, Any] | None:
    if not case_id or not thread_path.exists():
        return None
    try:
        with thread_path.open("r", encoding="utf-8-sig") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (
                    isinstance(event, dict)
                    and event.get("type") == "decision"
                    and str(event.get("case_id")) == case_id
                ):
                    return event
    except OSError:
        return None
    return None


def _find_jsonl_row(path: Path, case_id: str | None) -> dict[str, Any] | None:
    if not case_id or not path.exists():
        return None
    try:
        for row in read_jsonl(path):
            if str(row.get("id")) == case_id:
                return row
    except (OSError, json.JSONDecodeError):
        return None
    return None


def _build_decision_audit(run_dir: Path, case_id: str | None) -> dict[str, Any] | None:
    event = _find_decision_event(run_dir / "thread.jsonl", case_id)
    if not event:
        return None
    inputs_ref = event.get("inputs_ref")
    outputs_ref = event.get("outputs_ref")
    data_row = _find_jsonl_row(run_dir / inputs_ref, case_id) if inputs_ref else None
    pred_row = _find_jsonl_row(run_dir / outputs_ref, case_id) if outputs_ref else None
    gold_value = None
    if isinstance(data_row, dict):
        gold_block = data_row.get("gold") or {}
        if isinstance(gold_block, dict):
            gold_value = gold_block.get("value")
    pred_value = pred_row.get("value") if isinstance(pred_row, dict) else None
    return {
        "case_id": case_id,
        "selected_id": event.get("selected_id"),
        "gold_id": event.get("gold_id"),
        "pred_value": pred_value,
        "gold_value": gold_value,
    }


def _metric_rows(
    supporting: dict[str, Any],
    thresholds: dict[str, float],
) -> list[tuple[str, str]]:
    mapping = [
        ("unsafe_commit_rate", "unsafe_commit_rate", "<="),
        ("flip_rate", "flip_rate", "<="),
        ("gold_present_rate", "gold_present_rate", ">="),
        ("selection_rate_given_present", "selection_rate_given_present", ">="),
        ("authority_violation_rate", "authority_violation_rate", "<="),
        ("answer_correct_given_selected", "answer_correct_given_selected", ">="),
        ("drift.step_rate", "drift_step_rate_max", "<=", "drift_step_rate"),
    ]
    rows: list[tuple[str, str]] = []
    for entry in mapping:
        if len(entry) == 3:
            label, threshold_key, comparator = entry
            metric_key = threshold_key
        else:
            label, threshold_key, comparator, metric_key = entry
        value = supporting.get(metric_key)
        threshold = thresholds.get(threshold_key)
        rows.append((label, _format_metric(value, threshold, comparator)))
    return rows


def _load_repro_commands(run_dir: Path) -> str | None:
    text_candidates = [
        "repro_commands.txt",
        "run_command.txt",
        "command.txt",
    ]
    json_candidates = [
        "repro_commands.json",
        "run_commands.json",
    ]
    for name in text_candidates:
        path = run_dir / name
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    for name in json_candidates:
        path = run_dir / name
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            return "\n".join(str(item) for item in data)
        if isinstance(data, dict):
            commands = data.get("commands")
            if isinstance(commands, list):
                return "\n".join(str(item) for item in commands)
            if isinstance(commands, str):
                return commands
    return None


def generate_report(
    *,
    summary_path: Path,
    diagnosis_path: Path,
    compact_state_path: Path,
    out_path: Path,
    thresholds_path: Path | None = None,
) -> None:
    summary = _load_json(summary_path)
    diagnosis_missing = False
    if diagnosis_path.exists():
        diagnosis = _load_json(diagnosis_path)
    else:
        diagnosis_missing = True
        diagnosis = {
            "status": "UNKNOWN",
            "primary_bottleneck": "unknown",
            "supporting_metrics": {},
            "required_inputs_next_run": [
                "Generate diagnosis.json (run summarizer or a release/gate workflow)."
            ],
        }
    compact_state = _load_json(compact_state_path) if compact_state_path.exists() else {}
    thresholds = diagnosis_mod.load_thresholds(thresholds_path)

    status_raw = diagnosis.get("status", "UNKNOWN")
    status = STATUS_MAP.get(status_raw, status_raw)
    primary = diagnosis.get("primary_bottleneck", "unknown")
    holdout = diagnosis.get("holdout_name")
    failure_case_id = diagnosis.get("failure_case_id")
    supporting = diagnosis.get("supporting_metrics") or {}

    metric_lines = _metric_rows(supporting, thresholds)
    repro_commands = _load_repro_commands(summary_path.parent)
    decision_audit = _build_decision_audit(summary_path.parent, failure_case_id)

    rationale = None
    prescription = diagnosis.get("prescription") or {}
    if prescription:
        rationale = prescription.get("rationale")
    if diagnosis_missing:
        why = "Diagnosis missing; rerun a workflow that writes diagnosis.json."
    elif status == "PASS":
        why = "No bottleneck detected; thresholds passed for applicable metrics."
    else:
        why = rationale or f"Primary bottleneck = {primary}."

    report_lines = [
        "# Run Report",
        "",
        f"Overall: {status}",
        f"Primary bottleneck: {primary}",
    ]
    if holdout:
        report_lines.append(f"Holdout: {holdout}")
    report_lines.append(f"Failure case: {_format_plain(failure_case_id)}")
    report_lines.extend(
        [
            "",
            "## Key metrics vs thresholds",
        ]
    )
    for label, entry in metric_lines:
        report_lines.append(f"- {label}: {entry}")
    report_lines.extend(
        [
            "",
            "## What failed and why",
            why,
        ]
    )
    report_lines.extend(
        [
            "",
            "## Decision audit",
        ]
    )
    if decision_audit:
        report_lines.append(f"- case_id: {_format_plain(decision_audit.get('case_id'))}")
        report_lines.append(f"- selected_id: {_format_plain(decision_audit.get('selected_id'))}")
        report_lines.append(f"- gold_id: {_format_plain(decision_audit.get('gold_id'))}")
        report_lines.append(f"- pred_value: {_format_plain(decision_audit.get('pred_value'))}")
        gold_value = decision_audit.get("gold_value")
        gold_value_line = _format_plain(gold_value)
        if gold_value is None:
            gold_value_line = f"{gold_value_line} (not provided by fixture)"
        report_lines.append(f"- gold_value: {gold_value_line}")
    else:
        report_lines.append("Decision audit not available (missing thread log or case id).")
    report_lines.extend(
        [
            "",
            "## Repro commands",
        ]
    )
    if repro_commands:
        report_lines.append("```")
        report_lines.append(repro_commands)
        report_lines.append("```")
    else:
        report_lines.append("Repro commands not recorded.")
    report_lines.extend(
        [
            "",
            "## Artifacts",
            "- summary.json",
            "- diagnosis.json",
            "- compact_state.json",
            "- thread.jsonl",
            "- report.md",
        ]
    )
    gate_artifacts = compact_state.get("last_known_good", {}).get("gate_artifacts") or []
    if gate_artifacts:
        report_lines.append("- gate_artifacts:")
        for artifact in gate_artifacts:
            artifact_path = summary_path.parent / artifact
            status = None
            if artifact_path.exists():
                try:
                    artifact_data = _load_json(artifact_path)
                    status = artifact_data.get("status")
                except json.JSONDecodeError:
                    status = None
            suffix = f" (status={status})" if status else ""
            report_lines.append(f"  - {artifact}{suffix}")
    else:
        report_lines.append("- gate_artifacts: none")

    out_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
