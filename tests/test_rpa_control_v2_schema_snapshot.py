from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _make_reliability_with_holdout(
    *, root: Path, name: str, means: dict[str, float], status: str = "PASS"
) -> str:
    run_dir = root / f"{name}_run"
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(run_dir / "holdout_summary.json", {"means": means})
    rel_path = root / f"{name}_reliability.json"
    _write_json(rel_path, {"status": status, "runs": [run_dir.name]})
    return rel_path.name


def _first_item_keys(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        return []
    first = value[0]
    if not isinstance(first, dict):
        return []
    return sorted(first.keys())


def _schema_snapshot(payload: dict) -> dict:
    control_v2 = payload.get("control_v2") if isinstance(payload, dict) else None
    signals = payload.get("signals") if isinstance(payload, dict) else None
    inputs = payload.get("inputs") if isinstance(payload, dict) else None
    thresholds = payload.get("thresholds") if isinstance(payload, dict) else None

    control_v2 = control_v2 if isinstance(control_v2, dict) else {}
    signals = signals if isinstance(signals, dict) else {}
    inputs = inputs if isinstance(inputs, dict) else {}
    thresholds = thresholds if isinstance(thresholds, dict) else {}

    policy = control_v2.get("policy")
    policy = policy if isinstance(policy, dict) else {}
    substitution = control_v2.get("substitution")
    substitution = substitution if isinstance(substitution, dict) else {}
    reversibility_detail = control_v2.get("reversibility_detail")
    reversibility_detail = reversibility_detail if isinstance(reversibility_detail, dict) else {}

    family_statuses = signals.get("family_statuses")
    family_statuses = family_statuses if isinstance(family_statuses, dict) else {}
    derived_scores = signals.get("derived_scores")
    derived_scores = derived_scores if isinstance(derived_scores, dict) else {}
    input_errors = inputs.get("errors")
    input_errors = input_errors if isinstance(input_errors, dict) else {}

    return {
        "control_contract_version_type": type(payload.get("control_contract_version")).__name__,
        "top_level_keys": sorted(payload.keys()),
        "control_v2": {
            "keys": sorted(control_v2.keys()),
            "assumptions_used_item_keys": _first_item_keys(control_v2.get("assumptions_used")),
            "implications_item_keys": _first_item_keys(control_v2.get("implications")),
            "needed_info_item_keys": _first_item_keys(control_v2.get("needed_info")),
            "policy_keys": sorted(policy.keys()),
            "policy_reason_item_keys": _first_item_keys(policy.get("reasons")),
            "substitution_keys": sorted(substitution.keys()),
            "reversibility_detail_keys": sorted(reversibility_detail.keys()),
        },
        "signals_keys": sorted(signals.keys()),
        "family_status_keys": sorted(family_statuses.keys()),
        "derived_score_keys": sorted(derived_scores.keys()),
        "inputs_keys": sorted(inputs.keys()),
        "input_error_keys": sorted(input_errors.keys()),
        "threshold_keys": sorted(thresholds.keys()),
    }


def test_rpa_control_v2_schema_golden_snapshot(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "reliability_signal.json",
        {
            "status": "PASS",
            "derived": {
                "reasoning_score": 0.90,
                "planning_score": 0.65,
                "intelligence_index": 0.88,
            },
        },
    )
    _make_reliability_with_holdout(
        root=tmp_path,
        name="epistemic",
        means={
            "kkyi": 0.80,
            "needed_info_recall": 0.40,
            "parse_rate": 0.80,
            "confidence_provided_rate": 0.80,
            "confidence_proxy_used_rate": 0.30,
            "overclaim_rate": 0.10,
            "abstain_f1": 0.60,
        },
    )
    _make_reliability_with_holdout(
        root=tmp_path,
        name="authority",
        means={"authority_violation_rate": 0.10, "latest_support_hit_rate": 0.70},
    )
    _make_reliability_with_holdout(
        root=tmp_path,
        name="myopic",
        means={
            "trap_entry_rate": 0.20,
            "horizon_success_rate": 0.60,
            "recovery_rate": 0.60,
            "first_error_step_mean": 3.0,
        },
    )
    _make_reliability_with_holdout(
        root=tmp_path,
        name="referential",
        means={
            "stale_pointer_override_rate": 0.10,
            "hallucinated_expansion_rate": 0.10,
            "reassembly_fidelity": 0.70,
        },
    )
    _make_reliability_with_holdout(
        root=tmp_path,
        name="long_horizon",
        means={"long_gap_acc": 0.70, "high_contradiction_acc": 0.70},
    )
    _make_reliability_with_holdout(
        root=tmp_path,
        name="implication",
        means={
            "ic_score": 0.60,
            "implication_break_rate": 0.20,
            "contradiction_repair_rate": 0.70,
            "dependency_coverage": 0.70,
            "causal_precision": 0.70,
        },
    )
    _make_reliability_with_holdout(
        root=tmp_path,
        name="agency",
        means={
            "substitution_transparency_rate": 0.80,
            "unauthorized_substitution_rate": 0.00,
            "intent_preservation_score": 0.80,
            "agency_loss_error_rate": 0.10,
            "recovery_success_rate": 0.70,
        },
    )

    script = Path(__file__).resolve().parents[1] / "scripts" / "build_rpa_control_snapshot.py"
    out_path = tmp_path / "rpa_control_latest.json"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--reliability-signal",
            "reliability_signal.json",
            "--epistemic-reliability",
            "epistemic_reliability.json",
            "--authority-reliability",
            "authority_reliability.json",
            "--myopic-reliability",
            "myopic_reliability.json",
            "--referential-reliability",
            "referential_reliability.json",
            "--novel-long-horizon-reliability",
            "long_horizon_reliability.json",
            "--implication-reliability",
            "implication_reliability.json",
            "--agency-reliability",
            "agency_reliability.json",
            "--out",
            "rpa_control_latest.json",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    snapshot = _schema_snapshot(payload)

    golden_path = (
        Path(__file__).parent / "golden" / "rpa_control_latest_v02_schema_snapshot.json"
    )
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    assert snapshot == golden
