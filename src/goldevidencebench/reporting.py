from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from goldevidencebench import diagnosis as diagnosis_mod

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
    supporting = diagnosis.get("supporting_metrics") or {}

    metric_lines = _metric_rows(supporting, thresholds)
    repro_commands = _load_repro_commands(summary_path.parent)

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
