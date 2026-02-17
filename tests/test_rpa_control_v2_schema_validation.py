from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from goldevidencebench import schema_validation


def test_rpa_control_v2_schema_validation_passes() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    out_path = repo_root / "runs" / "test_rpa_control_latest_schema.json"
    script_path = repo_root / "scripts" / "build_rpa_control_snapshot.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--out",
            str(out_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    schema_path = schema_validation.schema_path("rpa_control_latest_v0_2.schema.json")
    errors = schema_validation.validate_artifact(payload, schema_path)
    assert errors == []

    try:
        out_path.unlink(missing_ok=True)
    except Exception:
        pass


def test_rpa_control_v2_schema_validation_fails_when_control_v2_missing() -> None:
    schema_path = schema_validation.schema_path("rpa_control_latest_v0_2.schema.json")
    invalid_payload = {
        "control_contract_version": "0.2",
        "mode": "reason",
        "decision": "ask",
        "confidence": 0.5,
        "risk": 0.5,
        "horizon_depth": 1,
        "needed_info": [],
        "support_ids": [],
        "reversibility": "reversible",
        "why": [],
        "signals": {
            "reliability_signal_status": "PASS",
            "family_statuses": {
                "epistemic_calibration_suite": "PASS",
                "authority_under_interference_hardening": "PASS",
                "myopic_planning_traps": "PASS",
                "referential_indexing_suite": "PASS",
                "novel_continuity_long_horizon": "PASS",
                "implication_coherence": "PASS",
                "agency_preserving_substitution": "PASS"
            },
            "derived_scores": {
                "reasoning_score": 0.9,
                "planning_score": 0.9,
                "intelligence_index": 0.9
            },
            "epistemic_means": {},
            "authority_means": {},
            "myopic_means": {},
            "referential_means": {},
            "long_horizon_means": {},
            "implication_means": {},
            "agency_means": {}
        },
        "inputs": {
            "reliability_signal": "runs/reliability_signal_latest.json",
            "epistemic_reliability": "runs/epistemic.json",
            "authority_reliability": "runs/authority.json",
            "myopic_reliability": "runs/myopic.json",
            "referential_reliability": "runs/referential.json",
            "novel_long_horizon_reliability": "runs/novel.json",
            "implication_reliability": "runs/implication.json",
            "agency_reliability": "runs/agency.json",
            "errors": {
                "reliability_signal": None,
                "epistemic": None,
                "authority": None,
                "myopic": None,
                "referential": None,
                "novel_long_horizon": None,
                "implication": None,
                "agency": None
            }
        },
        "thresholds": {
            "confidence_floor": 0.7,
            "planning_floor": 0.9,
            "reasoning_floor": 0.9,
            "needed_info_floor": 0.75,
            "risk_floor": 0.5,
            "irreversible_confidence_floor": 0.85
        }
    }
    errors = schema_validation.validate_artifact(invalid_payload, schema_path)
    assert any("missing required 'control_v2'" in error for error in errors)
