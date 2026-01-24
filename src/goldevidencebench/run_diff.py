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
    for key in METRIC_DIRECTIONS:
        entry = _metric_delta(
            key,
            base_metrics.get(key),
            other_metrics.get(key),
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
        "top_regressions": regressions[:5],
        "top_improvements": improvements[:5],
        "gate_changes": gate_changes,
        "config_changes": config_changes,
    }


def render_delta_report(delta: dict[str, Any]) -> str:
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
