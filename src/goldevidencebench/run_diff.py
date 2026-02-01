from __future__ import annotations

import json
from pathlib import Path
from typing import Any


METRIC_DIRECTIONS: dict[str, str] = {
    "unsafe_commit_rate": "lower",
    "flip_rate": "lower",
    "gold_present_rate": "higher",
    "selection_rate_given_present": "higher",
    "authority_violation_rate": "lower",
    "answer_correct_given_selected": "higher",
    "drift_step_rate": "lower",
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        text = path.read_text(encoding="utf-8-sig")
        return json.loads(text)


def _normalize_run_dir(path: Path) -> Path:
    if path.is_file():
        return path.parent
    return path


def _metric_delta(
    key: str,
    base: float | None,
    other: float | None,
) -> dict[str, Any] | None:
    if base is None or other is None:
        return None
    delta = other - base
    direction = METRIC_DIRECTIONS.get(key, "higher")
    if abs(delta) < 1e-12:
        change = "flat"
    elif direction == "lower":
        change = "improved" if delta < 0 else "regressed"
    else:
        change = "improved" if delta > 0 else "regressed"
    return {
        "metric": key,
        "base": base,
        "other": other,
        "delta": delta,
        "direction": direction,
        "change": change,
    }


def _format_delta(delta: float) -> str:
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta:.4f}"


def _gate_statuses(run_dir: Path, compact_state: dict[str, Any]) -> dict[str, str | None]:
    statuses: dict[str, str | None] = {}
    gate_artifacts = (
        compact_state.get("last_known_good", {}).get("gate_artifacts") or []
    )
    if gate_artifacts:
        artifact_paths = [run_dir / path for path in gate_artifacts]
    else:
        patterns = ["*gate*.json", "*wall*.json", "*distillation*.json"]
        artifact_paths = []
        for pattern in patterns:
            artifact_paths.extend(run_dir.glob(pattern))
    for path in artifact_paths:
        if path.name in {"summary.json", "diagnosis.json", "compact_state.json"}:
            continue
        data = _load_json(path)
        statuses[path.name] = data.get("status")
    return statuses


def _model_fingerprint(repro: dict[str, Any]) -> dict[str, Any]:
    model = repro.get("model")
    if isinstance(model, dict):
        return model
    return {}


def _load_case_pack(run_dir: Path) -> dict[str, Any]:
    return _load_json(run_dir / "case_pack_summary.json")


def _find_step(summary: dict[str, Any], name: str) -> dict[str, Any] | None:
    steps = summary.get("steps") or []
    for step in steps:
        if isinstance(step, dict) and step.get("name") == name:
            return step
    return None


def _load_bad_actor_metrics(run_dir: Path, step: dict[str, Any]) -> dict[str, Any]:
    details = step.get("details", {}) if isinstance(step, dict) else {}
    expected_fail = details.get("expected_fail")
    metrics: dict[str, Any] = {
        "status": step.get("status") if isinstance(step, dict) else None,
        "expected_fail_observed": details.get("expected_fail_observed"),
        "wall_rate": details.get("wall_rate"),
    }
    holdout_gate = details.get("holdout_gate")
    step_run_dir = Path(step.get("run_dir", "")) if isinstance(step, dict) else Path()
    gate_path = (step_run_dir / holdout_gate) if holdout_gate else None
    if gate_path and gate_path.exists():
        gate = _load_json(gate_path)
        gate_status = gate.get("status")
        canary = gate.get("canary") or {}
        fix_auth = gate.get("fix_authority") or {}
        fix_pref = gate.get("fix_prefer_set_latest") or {}
        metrics.update(
            {
                "gate_status": gate_status,
                "canary_drift_step_rate": canary.get("drift_step_rate"),
                "canary_pass": canary.get("pass"),
                "fix_authority_drift_step_rate": fix_auth.get("drift_step_rate"),
                "fix_authority_pass": fix_auth.get("pass"),
                "fix_prefer_set_latest_drift_step_rate": fix_pref.get("drift_step_rate"),
                "fix_prefer_set_latest_pass": fix_pref.get("pass"),
            }
        )
        if expected_fail and gate_status:
            metrics["expected_fail_observed"] = gate_status != "PASS"
    # Prefer wall rate from the local bad_actor wall summary if present.
    wall_dir = step_run_dir / "wall"
    if wall_dir.exists():
        wall_summaries = sorted(wall_dir.rglob("summary.json"))
        if wall_summaries:
            wall_data = _load_json(wall_summaries[-1])
            drift = wall_data.get("drift") or {}
            wall_rate = drift.get("step_rate")
            if wall_rate is not None:
                metrics["wall_rate"] = wall_rate
    return metrics


def _case_pack_delta(base_dir: Path, other_dir: Path) -> dict[str, Any]:
    base_summary = _load_case_pack(base_dir)
    other_summary = _load_case_pack(other_dir)
    if not base_summary or not other_summary:
        return {"present": False}
    base_bad = _find_step(base_summary, "bad_actor_demo")
    other_bad = _find_step(other_summary, "bad_actor_demo")
    if not base_bad or not other_bad:
        return {"present": False}
    base_metrics = _load_bad_actor_metrics(base_dir, base_bad)
    other_metrics = _load_bad_actor_metrics(other_dir, other_bad)
    changes: list[dict[str, Any]] = []
    for key in (
        "expected_fail_observed",
        "wall_rate",
        "gate_status",
        "canary_drift_step_rate",
        "canary_pass",
        "fix_authority_drift_step_rate",
        "fix_authority_pass",
        "fix_prefer_set_latest_drift_step_rate",
        "fix_prefer_set_latest_pass",
    ):
        before = base_metrics.get(key)
        after = other_metrics.get(key)
        if before != after:
            changes.append({"metric": key, "base": before, "other": after})
    return {
        "present": True,
        "base_summary": {
            "status": base_summary.get("status"),
            "model_id": base_summary.get("model_id"),
            "source_pdf": base_summary.get("source_pdf"),
        },
        "other_summary": {
            "status": other_summary.get("status"),
            "model_id": other_summary.get("model_id"),
            "source_pdf": other_summary.get("source_pdf"),
        },
        "base_bad_actor": base_metrics,
        "other_bad_actor": other_metrics,
        "changes": changes,
    }


def compare_runs(
    *,
    base_dir: Path,
    other_dir: Path,
) -> dict[str, Any]:
    base_dir = _normalize_run_dir(base_dir)
    other_dir = _normalize_run_dir(other_dir)

    base_summary = _load_json(base_dir / "summary.json")
    base_diag = _load_json(base_dir / "diagnosis.json")
    base_compact = _load_json(base_dir / "compact_state.json")
    base_repro = _load_json(base_dir / "repro_commands.json")
    base_health = _load_json(base_dir / "health_check.json")

    other_summary = _load_json(other_dir / "summary.json")
    other_diag = _load_json(other_dir / "diagnosis.json")
    other_compact = _load_json(other_dir / "compact_state.json")
    other_repro = _load_json(other_dir / "repro_commands.json")
    other_health = _load_json(other_dir / "health_check.json")

    base_metrics = base_diag.get("supporting_metrics") or {}
    other_metrics = other_diag.get("supporting_metrics") or {}

    metric_deltas: list[dict[str, Any]] = []
    metric_values: dict[str, dict[str, Any]] = {}
    for key in METRIC_DIRECTIONS:
        base_val = base_metrics.get(key)
        other_val = other_metrics.get(key)
        metric_values[key] = {"base": base_val, "other": other_val}
        entry = _metric_delta(
            key,
            base_val,
            other_val,
        )
        if entry:
            metric_deltas.append(entry)

    regressions = [
        d for d in metric_deltas if d["change"] == "regressed"
    ]
    improvements = [
        d for d in metric_deltas if d["change"] == "improved"
    ]
    regressions.sort(key=lambda d: abs(d["delta"]), reverse=True)
    improvements.sort(key=lambda d: abs(d["delta"]), reverse=True)

    base_gates = _gate_statuses(base_dir, base_compact)
    other_gates = _gate_statuses(other_dir, other_compact)
    gate_changes: list[dict[str, Any]] = []
    for name in sorted(set(base_gates) | set(other_gates)):
        before = base_gates.get(name)
        after = other_gates.get(name)
        if before != after:
            gate_changes.append(
                {"artifact": name, "base": before, "other": after}
            )

    config_changes: list[dict[str, Any]] = []
    for key in ("authority_mode", "rerank_mode"):
        before = base_compact.get(key)
        after = other_compact.get(key)
        if before != after:
            config_changes.append(
                {"field": key, "base": before, "other": after}
            )
    base_model = _model_fingerprint(base_repro)
    other_model = _model_fingerprint(other_repro)
    if base_model or other_model:
        if base_model != other_model:
            config_changes.append(
                {"field": "model_fingerprint", "base": base_model, "other": other_model}
            )

    summary = {
        "diagnosis_status": {
            "base": base_diag.get("status"),
            "other": other_diag.get("status"),
        },
        "primary_bottleneck": {
            "base": base_diag.get("primary_bottleneck"),
            "other": other_diag.get("primary_bottleneck"),
        },
        "holdout_name": {
            "base": base_diag.get("holdout_name"),
            "other": other_diag.get("holdout_name"),
        },
        "health_overall": {
            "base": base_health.get("overall"),
            "other": other_health.get("overall"),
        },
    }

    return {
        "base_dir": str(base_dir),
        "other_dir": str(other_dir),
        "summary": summary,
        "metric_deltas": metric_deltas,
        "metric_values": metric_values,
        "top_regressions": regressions[:5],
        "top_improvements": improvements[:5],
        "gate_changes": gate_changes,
        "config_changes": config_changes,
        "case_pack": _case_pack_delta(base_dir, other_dir),
    }


def render_delta_report(delta: dict[str, Any], *, full: bool = False) -> str:
    case_pack = delta.get("case_pack", {})
    if case_pack.get("present"):
        lines = [
            "# Case Pack Delta Report",
            "",
            f"Base: {delta['base_dir']}",
            f"Other: {delta['other_dir']}",
            "",
            "## Case pack summary",
        ]
        base_summary = case_pack.get("base_summary", {})
        other_summary = case_pack.get("other_summary", {})
        lines.append(
            f"- status: {base_summary.get('status')} -> {other_summary.get('status')}"
        )
        lines.append(
            f"- model_id: {base_summary.get('model_id')} -> {other_summary.get('model_id')}"
        )
        if base_summary.get("source_pdf") or other_summary.get("source_pdf"):
            lines.append(
                f"- source_pdf: {base_summary.get('source_pdf')} -> {other_summary.get('source_pdf')}"
            )

        if full:
            base_bad = case_pack.get("base_bad_actor", {})
            other_bad = case_pack.get("other_bad_actor", {})
            lines.extend(["", "## Case pack (bad-actor metrics)"])
            for key in (
                "status",
                "gate_status",
                "expected_fail_observed",
                "wall_rate",
                "canary_drift_step_rate",
                "canary_pass",
                "fix_authority_drift_step_rate",
                "fix_authority_pass",
                "fix_prefer_set_latest_drift_step_rate",
                "fix_prefer_set_latest_pass",
            ):
                lines.append(
                    f"- {key}: {base_bad.get(key)} -> {other_bad.get(key)}"
                )
        else:
            changes = case_pack.get("changes", [])
            lines.extend(["", "## Case pack changes"])
            if changes:
                for entry in changes:
                    lines.append(
                        f"- {entry['metric']}: {entry.get('base')} -> {entry.get('other')}"
                    )
            else:
                lines.append("- none (no bad-actor metric deltas)")

        config_changes = delta.get("config_changes", [])
        if config_changes:
            lines.extend(["", "## Config changes"])
            for entry in config_changes:
                lines.append(
                    f"- {entry['field']}: {entry.get('base')} -> {entry.get('other')}"
                )
        return "\n".join(lines) + "\n"

    lines = [
        "# Run Delta Report",
        "",
        f"Base: {delta['base_dir']}",
        f"Other: {delta['other_dir']}",
        "",
        "## Summary",
    ]
    summary = delta.get("summary", {})
    for key in ("diagnosis_status", "primary_bottleneck", "holdout_name", "health_overall"):
        entry = summary.get(key, {})
        base_val = entry.get("base")
        other_val = entry.get("other")
        if base_val != other_val:
            lines.append(f"- {key}: {base_val} -> {other_val}")
        else:
            lines.append(f"- {key}: {base_val}")

    lines.extend(["", "## Top regressions"])
    regressions = delta.get("top_regressions", [])
    if regressions:
        for entry in regressions:
            lines.append(
                f"- {entry['metric']}: {_format_delta(entry['delta'])} ({entry['base']:.4f} -> {entry['other']:.4f})"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## Top improvements"])
    improvements = delta.get("top_improvements", [])
    if improvements:
        for entry in improvements:
            lines.append(
                f"- {entry['metric']}: {_format_delta(entry['delta'])} ({entry['base']:.4f} -> {entry['other']:.4f})"
            )
    else:
        lines.append("- none")

    if full:
        lines.extend(["", "## Metric deltas (all)"])
        metric_values = delta.get("metric_values", {})
        for key in METRIC_DIRECTIONS:
            entry = metric_values.get(key, {})
            base_val = entry.get("base")
            other_val = entry.get("other")
            if base_val is None and other_val is None:
                continue
            if base_val is None or other_val is None:
                lines.append(f"- {key}: {base_val} -> {other_val}")
            else:
                delta_val = other_val - base_val
                lines.append(
                    f"- {key}: {_format_delta(delta_val)} ({base_val:.4f} -> {other_val:.4f})"
                )

    lines.extend(["", "## Gate status changes"])
    gate_changes = delta.get("gate_changes", [])
    if gate_changes:
        for entry in gate_changes:
            lines.append(
                f"- {entry['artifact']}: {entry.get('base')} -> {entry.get('other')}"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## Config changes"])
    config_changes = delta.get("config_changes", [])
    if config_changes:
        for entry in config_changes:
            lines.append(
                f"- {entry['field']}: {entry.get('base')} -> {entry.get('other')}"
            )
    else:
        lines.append("- none")

    return "\n".join(lines) + "\n"
