from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a next-step execution report for RPA/intent/noise-control "
            "expansion on top of current reliability artifacts."
        )
    )
    parser.add_argument(
        "--reliability-signal",
        type=Path,
        default=Path("runs/reliability_signal_latest.json"),
        help="Unified reliability signal JSON.",
    )
    parser.add_argument(
        "--rpa-control",
        type=Path,
        default=Path("runs/rpa_control_latest.json"),
        help="Runtime RPA controller snapshot JSON.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("runs/codex_next_step_report.json"),
        help="Output report JSON.",
    )
    return parser.parse_args()


def _read_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid JSON object: {path}")
    return raw


def _read_json_if_exists(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, f"missing: {path}"
    try:
        return _read_json(path), None
    except Exception as exc:  # pragma: no cover - defensive
        return None, str(exc)


def _status_for(path: Path) -> tuple[str, str | None]:
    summary, err = _read_json_if_exists(path)
    if summary is None:
        return "MISSING", err
    status = summary.get("status")
    if isinstance(status, str):
        return status, None
    return "INVALID", "missing status field"


def _file_presence(paths: dict[str, str]) -> dict[str, bool]:
    return {name: Path(p).exists() for name, p in paths.items()}


def main() -> int:
    ns = _parse_args()

    reliability_signal, reliability_err = _read_json_if_exists(ns.reliability_signal)
    rpa_control, rpa_err = _read_json_if_exists(ns.rpa_control)

    foundation_paths = {
        "compression_roundtrip_generalization": "runs/compression_roundtrip_generalization_reliability_latest.json",
        "novel_continuity_long_horizon": "runs/novel_continuity_long_horizon_reliability_latest.json",
        "myopic_planning_traps": "runs/myopic_planning_traps_reliability_latest.json",
        "referential_indexing_suite": "runs/referential_indexing_suite_reliability_latest.json",
        "epistemic_calibration_suite": "runs/epistemic_calibration_suite_reliability_latest.json",
        "authority_under_interference_hardening": "runs/authority_under_interference_hardening_reliability_latest.json",
    }
    foundation_statuses: dict[str, dict[str, Any]] = {}
    for family, rel_path in foundation_paths.items():
        status, err = _status_for(Path(rel_path))
        foundation_statuses[family] = {"status": status, "error": err, "path": rel_path}

    proposed_families = {
        "rpa_mode_switch": {
            "generator": "scripts/generate_rpa_mode_switch_family.py",
            "scorer": "scripts/score_rpa_mode_switch.py",
            "wrapper": "scripts/run_rpa_mode_switch_family.ps1",
            "checker": "scripts/check_rpa_mode_switch_reliability.py",
        },
        "intent_spec_layer": {
            "generator": "scripts/generate_intent_spec_family.py",
            "scorer": "scripts/score_intent_spec.py",
            "wrapper": "scripts/run_intent_spec_family.ps1",
            "checker": "scripts/check_intent_spec_reliability.py",
        },
        "noise_escalation": {
            "generator": "scripts/generate_noise_escalation_family.py",
            "scorer": "scripts/score_noise_escalation.py",
            "wrapper": "scripts/run_noise_escalation_family.ps1",
            "checker": "scripts/check_noise_escalation_reliability.py",
        },
    }

    scaffold_status: dict[str, dict[str, Any]] = {}
    for family, paths in proposed_families.items():
        presence = _file_presence(paths)
        ready = all(presence.values())
        scaffold_status[family] = {
            "ready": ready,
            "paths": paths,
            "present": presence,
            "missing": [k for k, exists in presence.items() if not exists],
        }

    blockers: list[str] = []
    next_actions: list[str] = []

    reliability_status = (
        str(reliability_signal.get("status")) if isinstance(reliability_signal, dict) else "MISSING"
    )
    if reliability_status != "PASS":
        blockers.append("Unified reliability signal is not PASS.")
        next_actions.append("Stabilize required families and rerun scripts/check_reliability_signal.ps1.")

    if reliability_signal is None and reliability_err:
        blockers.append(f"Unable to read reliability signal: {reliability_err}")

    for family, info in foundation_statuses.items():
        if info["status"] != "PASS":
            blockers.append(f"Foundation family not PASS: {family} ({info['status']}).")

    if rpa_control is None:
        blockers.append("RPA control snapshot is missing.")
        next_actions.append("Run scripts/run_rpa_control_snapshot.ps1 to emit controller contract.")
    else:
        if rpa_control.get("decision") == "defer":
            blockers.append("RPA control currently recommends DEFER.")
        if rpa_control.get("mode") not in ("reason", "plan", "act"):
            blockers.append("RPA control payload mode is invalid.")

    for family, info in scaffold_status.items():
        if not info["ready"]:
            blockers.append(f"Scaffold incomplete for {family}: missing {', '.join(info['missing'])}.")

    if not any("rpa_mode_switch" in x for x in blockers):
        next_actions.append("Run staged triplets for rpa_mode_switch and add to unified reliability signal.")
    if not any("intent_spec_layer" in x for x in blockers):
        next_actions.append("Run staged triplets for intent_spec_layer and measure user-burden reduction.")
    if not any("noise_escalation" in x for x in blockers):
        next_actions.append("Run staged triplets for noise_escalation and enforce noise_slope ceilings.")

    if not next_actions:
        next_actions = [
            "Promote rpa_mode_switch/intent_spec_layer/noise_escalation from observe->ramp->target.",
            "Add require flags in scripts/check_reliability_signal.ps1 once target PASS is stable.",
        ]

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if not blockers else "FAIL",
        "inputs": {
            "reliability_signal": str(ns.reliability_signal),
            "rpa_control": str(ns.rpa_control),
        },
        "reliability_signal_status": reliability_status,
        "foundation_statuses": foundation_statuses,
        "rpa_control_summary": {
            "mode": (rpa_control or {}).get("mode"),
            "decision": (rpa_control or {}).get("decision"),
            "confidence": (rpa_control or {}).get("confidence"),
            "risk": (rpa_control or {}).get("risk"),
            "why": (rpa_control or {}).get("why"),
            "read_error": rpa_err,
        },
        "proposed_family_scaffolds": scaffold_status,
        "blockers": blockers,
        "next_actions": next_actions,
    }

    ns.out.parent.mkdir(parents=True, exist_ok=True)
    ns.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {ns.out}")
    print(f"Status: {payload['status']}")
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
