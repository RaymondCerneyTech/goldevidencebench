from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a non-trap capability snapshot from external-utility and demo artifacts."
        )
    )
    parser.add_argument(
        "--runs-root",
        type=Path,
        default=Path("runs"),
        help="Runs root containing latest non-trap artifacts.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("runs/capability_snapshot_latest.json"),
        help="Snapshot output path.",
    )
    parser.add_argument(
        "--archive-dir",
        type=Path,
        default=Path("runs/capability_snapshots"),
        help="Archive directory for timestamped snapshots.",
    )
    return parser.parse_args()


def _read_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return raw


def _read_json_if_exists(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, f"missing: {path}"
    try:
        return _read_json(path), None
    except Exception as exc:  # pragma: no cover - defensive
        return None, str(exc)


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y"}:
            return True
        if lowered in {"0", "false", "no", "n"}:
            return False
    return None


def _flatten_scalars(prefix: str, payload: dict[str, Any], out: dict[str, Any]) -> None:
    for key, value in payload.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            out[f"{prefix}{key}"] = value


def _resolve_path(raw_path: str, runs_root: Path) -> Path:
    normalized = raw_path.strip().strip('"').strip("'").replace("\\\\", "\\")
    candidate = Path(normalized)
    if candidate.is_absolute():
        return candidate

    candidates = [
        Path.cwd() / candidate,
        runs_root.parent / candidate,
        runs_root / candidate,
    ]
    if normalized.lower().startswith("runs\\") or normalized.lower().startswith("runs/"):
        suffix = normalized[5:]
        candidates.append(runs_root / suffix)

    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def _resolve_pointer_file(pointer_path: Path, runs_root: Path) -> tuple[Path | None, str | None]:
    if not pointer_path.exists():
        return None, f"missing_pointer:{pointer_path}"
    text = pointer_path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return None, "empty_pointer"
    resolved = _resolve_path(text, runs_root)
    if resolved.exists():
        return resolved, None
    return resolved, f"target_missing:{resolved}"


def _extract_utility(
    runs_root: Path,
    metrics: dict[str, Any],
    sources: dict[str, Any],
    failures: list[str],
) -> None:
    path = runs_root / "real_world_utility_eval_latest.json"
    payload, err = _read_json_if_exists(path)
    source = {
        "path": str(path),
        "present": payload is not None,
        "read_error": err,
        "status": "MISSING",
    }
    metrics["source.utility.present"] = payload is not None
    if payload is None:
        failures.append("missing_real_world_utility_eval")
        sources["utility"] = source
        return

    status = str(payload.get("status") or "UNKNOWN")
    source["status"] = status
    metrics["utility.status"] = status
    metrics["utility.status_is_pass"] = status == "PASS"
    task_count = _as_float(payload.get("task_count"))
    if task_count is not None:
        metrics["utility.task_count"] = task_count

    baseline = payload.get("baseline")
    if isinstance(baseline, dict):
        _flatten_scalars("utility.baseline.", baseline, metrics)
    controlled = payload.get("controlled")
    if isinstance(controlled, dict):
        _flatten_scalars("utility.controlled.", controlled, metrics)
    comparison = payload.get("comparison")
    if isinstance(comparison, dict):
        _flatten_scalars("utility.comparison.", comparison, metrics)
    pass_inputs = payload.get("pass_inputs")
    if isinstance(pass_inputs, dict):
        _flatten_scalars("utility.pass_inputs.", pass_inputs, metrics)
    pass_checks = payload.get("pass_checks")
    if isinstance(pass_checks, dict):
        _flatten_scalars("utility.checks.", pass_checks, metrics)

    if status != "PASS":
        failures.append(f"real_world_utility_eval_status_{status}")
    sources["utility"] = source


def _extract_ui_notepad(
    runs_root: Path,
    metrics: dict[str, Any],
    sources: dict[str, Any],
    failures: list[str],
) -> None:
    path = runs_root / "ui_minipilot_notepad_gate.json"
    payload, err = _read_json_if_exists(path)
    source = {
        "path": str(path),
        "present": payload is not None,
        "read_error": err,
        "status": "MISSING",
    }
    metrics["source.ui_notepad.present"] = payload is not None
    if payload is None:
        failures.append("missing_ui_minipilot_notepad_gate")
        sources["ui_notepad"] = source
        return

    source["status"] = "OK"
    rows = _as_float(payload.get("rows"))
    if rows is not None:
        metrics["ui_notepad.rows"] = rows

    gate_metrics = payload.get("metrics")
    if isinstance(gate_metrics, dict):
        _flatten_scalars("ui_notepad.metrics.", gate_metrics, metrics)
    seq_metrics = payload.get("sequence_metrics")
    if isinstance(seq_metrics, dict):
        _flatten_scalars("ui_notepad.sequence.", seq_metrics, metrics)
    sources["ui_notepad"] = source


def _extract_codex_next_step(
    runs_root: Path,
    metrics: dict[str, Any],
    sources: dict[str, Any],
    warnings: list[str],
) -> None:
    path = runs_root / "codex_next_step_report.json"
    payload, err = _read_json_if_exists(path)
    source = {
        "path": str(path),
        "present": payload is not None,
        "read_error": err,
        "status": "MISSING",
    }
    metrics["source.codex_next_step.present"] = payload is not None
    if payload is None:
        warnings.append("missing_codex_next_step_report")
        sources["codex_next_step"] = source
        return

    status = str(payload.get("status") or "UNKNOWN")
    source["status"] = status
    metrics["codex_next_step.status"] = status
    metrics["codex_next_step.status_is_pass"] = status == "PASS"
    blockers = payload.get("blockers")
    next_actions = payload.get("next_actions")
    if isinstance(blockers, list):
        metrics["codex_next_step.blocker_count"] = float(len(blockers))
    if isinstance(next_actions, list):
        metrics["codex_next_step.next_action_count"] = float(len(next_actions))

    foundation = payload.get("foundation_statuses")
    if isinstance(foundation, dict) and foundation:
        total = 0
        passed = 0
        for info in foundation.values():
            if not isinstance(info, dict):
                continue
            total += 1
            if str(info.get("status") or "") == "PASS":
                passed += 1
        if total > 0:
            metrics["codex_next_step.foundation_pass_rate"] = passed / total
    sources["codex_next_step"] = source


def _extract_rpa_control(
    runs_root: Path,
    metrics: dict[str, Any],
    sources: dict[str, Any],
    warnings: list[str],
) -> None:
    path = runs_root / "rpa_control_latest.json"
    payload, err = _read_json_if_exists(path)
    source = {
        "path": str(path),
        "present": payload is not None,
        "read_error": err,
        "status": "MISSING",
    }
    metrics["source.rpa_control.present"] = payload is not None
    if payload is None:
        warnings.append("missing_rpa_control_latest")
        sources["rpa_control"] = source
        return

    mode = str(payload.get("mode") or "")
    decision = str(payload.get("decision") or "")
    confidence = _as_float(payload.get("confidence"))
    risk = _as_float(payload.get("risk"))

    source["status"] = "OK"
    metrics["rpa_control.mode"] = mode
    metrics["rpa_control.mode_valid"] = mode in {"reason", "plan", "act"}
    metrics["rpa_control.decision"] = decision
    metrics["rpa_control.decision_not_defer"] = decision != "defer"
    if confidence is not None:
        metrics["rpa_control.confidence"] = confidence
    if risk is not None:
        metrics["rpa_control.risk"] = risk
    signals = payload.get("signals")
    if isinstance(signals, dict):
        rel_status = signals.get("reliability_signal_status")
        if isinstance(rel_status, str):
            metrics["rpa_control.reliability_signal_status"] = rel_status
    sources["rpa_control"] = source


def _extract_case_pack(
    runs_root: Path,
    metrics: dict[str, Any],
    sources: dict[str, Any],
    warnings: list[str],
) -> None:
    pointer = runs_root / "case_pack_latest.txt"
    run_dir, err = _resolve_pointer_file(pointer, runs_root)
    source: dict[str, Any] = {
        "pointer_path": str(pointer),
        "present": run_dir is not None and run_dir.exists(),
        "read_error": err,
        "run_dir": str(run_dir) if run_dir is not None else None,
        "status": "MISSING",
    }
    metrics["source.case_pack.present"] = source["present"]
    if run_dir is None or not run_dir.exists():
        warnings.append("missing_case_pack_latest")
        sources["case_pack"] = source
        return

    summary_path = run_dir / "case_pack_summary.json"
    summary, summary_err = _read_json_if_exists(summary_path)
    source["summary_path"] = str(summary_path)
    source["read_error"] = summary_err
    if summary is None:
        warnings.append("missing_case_pack_summary")
        sources["case_pack"] = source
        return

    status = str(summary.get("status") or "UNKNOWN")
    source["status"] = status
    metrics["case_pack.status"] = status
    metrics["case_pack.status_is_pass"] = status == "PASS"
    steps = summary.get("steps")
    if isinstance(steps, list):
        metrics["case_pack.step_count"] = float(len(steps))
        required_steps = [s for s in steps if isinstance(s, dict) and _as_bool(s.get("required"))]
        if required_steps:
            pass_count = 0
            for step in required_steps:
                if str(step.get("status") or "") == "PASS":
                    pass_count += 1
            metrics["case_pack.required_step_pass_rate"] = pass_count / len(required_steps)
    sources["case_pack"] = source


def _extract_trust_demo(
    runs_root: Path,
    metrics: dict[str, Any],
    sources: dict[str, Any],
    warnings: list[str],
) -> None:
    pointer = runs_root / "trust_demo_latest.txt"
    run_dir, err = _resolve_pointer_file(pointer, runs_root)
    source: dict[str, Any] = {
        "pointer_path": str(pointer),
        "present": run_dir is not None and run_dir.exists(),
        "read_error": err,
        "run_dir": str(run_dir) if run_dir is not None else None,
        "status": "MISSING",
    }
    metrics["source.trust_demo.present"] = source["present"]
    if run_dir is None or not run_dir.exists():
        warnings.append("missing_trust_demo_latest")
        sources["trust_demo"] = source
        return

    summary_path = run_dir / "trust_demo_summary.json"
    summary, summary_err = _read_json_if_exists(summary_path)
    source["summary_path"] = str(summary_path)
    source["read_error"] = summary_err
    if summary is None:
        alt_path = run_dir / "summary.json"
        summary, summary_err = _read_json_if_exists(alt_path)
        source["summary_path"] = str(alt_path)
        source["read_error"] = summary_err
    if summary is None:
        warnings.append("missing_trust_demo_summary")
        sources["trust_demo"] = source
        return

    status = str(summary.get("status") or "UNKNOWN")
    source["status"] = status
    metrics["trust_demo.status"] = status
    metrics["trust_demo.status_is_pass"] = status == "PASS"

    steps = summary.get("steps")
    if isinstance(steps, list):
        metrics["trust_demo.step_count"] = float(len(steps))
        fail_count = 0
        for step in steps:
            if not isinstance(step, dict):
                continue
            if str(step.get("status") or "") != "PASS":
                fail_count += 1
        metrics["trust_demo.steps_failed"] = float(fail_count)
    else:
        steps_failed = _as_float(summary.get("steps_failed"))
        steps_total = _as_float(summary.get("steps_total"))
        if steps_total is not None:
            metrics["trust_demo.step_count"] = steps_total
        if steps_failed is not None:
            metrics["trust_demo.steps_failed"] = steps_failed
    sources["trust_demo"] = source


def _extract_drift_baseline(
    runs_root: Path,
    metrics: dict[str, Any],
    sources: dict[str, Any],
    warnings: list[str],
) -> None:
    direct_path = runs_root / "drift_holdout_compare_latest.json"
    payload: dict[str, Any] | None = None
    resolved_path: Path | None = None
    read_error: str | None = None
    if direct_path.exists():
        payload, read_error = _read_json_if_exists(direct_path)
        resolved_path = direct_path
    else:
        pointer = runs_root / "latest_drift_holdout_compare"
        pointer_target, pointer_err = _resolve_pointer_file(pointer, runs_root)
        if pointer_target is not None and pointer_target.exists():
            payload, read_error = _read_json_if_exists(pointer_target)
            resolved_path = pointer_target
        else:
            read_error = pointer_err

    source: dict[str, Any] = {
        "path": str(direct_path),
        "present": payload is not None,
        "read_error": read_error,
        "resolved_path": str(resolved_path) if resolved_path is not None else None,
        "status": "MISSING",
    }
    metrics["source.drift_baseline.present"] = payload is not None
    if payload is None:
        warnings.append("missing_drift_holdout_compare")
        sources["drift_baseline"] = source
        return

    status = str(payload.get("status") or "UNKNOWN")
    source["status"] = status
    metrics["drift_baseline.status"] = status
    metrics["drift_baseline.status_is_pass"] = status == "PASS"
    improved = _as_bool(payload.get("improved"))
    if improved is not None:
        metrics["drift_baseline.improved"] = improved
    delta = _as_float(payload.get("delta"))
    if delta is not None:
        metrics["drift_baseline.delta"] = delta
    holdout = payload.get("holdout")
    if isinstance(holdout, str):
        metrics["drift_baseline.holdout"] = holdout
    baseline = payload.get("baseline")
    if isinstance(baseline, dict):
        rate = _as_float(baseline.get("drift_step_rate"))
        if rate is not None:
            metrics["drift_baseline.baseline_step_rate"] = rate
    fix = payload.get("fix")
    if isinstance(fix, dict):
        rate = _as_float(fix.get("drift_step_rate"))
        if rate is not None:
            metrics["drift_baseline.fix_step_rate"] = rate
    sources["drift_baseline"] = source


def main() -> int:
    ns = _parse_args()
    runs_root = ns.runs_root

    metrics: dict[str, Any] = {}
    sources: dict[str, Any] = {}
    failures: list[str] = []
    warnings: list[str] = []

    _extract_utility(runs_root, metrics, sources, failures)
    _extract_ui_notepad(runs_root, metrics, sources, failures)
    _extract_codex_next_step(runs_root, metrics, sources, warnings)
    _extract_rpa_control(runs_root, metrics, sources, warnings)
    _extract_case_pack(runs_root, metrics, sources, warnings)
    _extract_trust_demo(runs_root, metrics, sources, warnings)
    _extract_drift_baseline(runs_root, metrics, sources, warnings)

    if failures:
        status = "FAIL"
    elif warnings:
        status = "WARN"
    else:
        status = "PASS"

    payload = {
        "benchmark": "capability_snapshot",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "runs_root": str(runs_root),
        "failure_reasons": failures,
        "warning_reasons": warnings,
        "metrics": metrics,
        "sources": sources,
    }

    ns.out.parent.mkdir(parents=True, exist_ok=True)
    ns.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {ns.out}")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    archive_path = ns.archive_dir / f"capability_snapshot_{timestamp}.json"
    ns.archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {archive_path}")

    return 1 if status == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
