from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _make_reliability_with_holdout(
    *, tmp_path: Path, name: str, means: dict[str, float], status: str = "PASS"
) -> Path:
    run_dir = tmp_path / f"{name}_run"
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(run_dir / "holdout_summary.json", {"means": means})
    rel_path = tmp_path / f"{name}_reliability.json"
    _write_json(rel_path, {"status": status, "runs": [str(run_dir)]})
    return rel_path


def test_rpa_control_v2_additive_contract_preserves_v1_fields(tmp_path: Path) -> None:
    reliability_signal = tmp_path / "reliability_signal.json"
    _write_json(
        reliability_signal,
        {
            "status": "PASS",
            "derived": {
                "reasoning_score": 0.95,
                "planning_score": 0.93,
                "intelligence_index": 0.94,
            },
        },
    )

    epistemic = _make_reliability_with_holdout(
        tmp_path=tmp_path,
        name="epistemic",
        means={
            "kkyi": 0.95,
            "needed_info_recall": 1.0,
            "parse_rate": 1.0,
            "confidence_provided_rate": 1.0,
            "confidence_proxy_used_rate": 0.0,
            "overclaim_rate": 0.0,
            "abstain_f1": 1.0,
        },
    )
    authority = _make_reliability_with_holdout(
        tmp_path=tmp_path,
        name="authority",
        means={
            "authority_violation_rate": 0.0,
            "latest_support_hit_rate": 1.0,
        },
    )
    myopic = _make_reliability_with_holdout(
        tmp_path=tmp_path,
        name="myopic",
        means={
            "trap_entry_rate": 0.0,
            "horizon_success_rate": 1.0,
            "recovery_rate": 1.0,
            "first_error_step_mean": 6.0,
        },
    )
    referential = _make_reliability_with_holdout(
        tmp_path=tmp_path,
        name="referential",
        means={
            "hallucinated_expansion_rate": 0.0,
            "stale_pointer_override_rate": 0.0,
            "reassembly_fidelity": 1.0,
        },
    )
    long_horizon = _make_reliability_with_holdout(
        tmp_path=tmp_path,
        name="long_horizon",
        means={
            "long_gap_acc": 1.0,
            "high_contradiction_acc": 1.0,
        },
    )
    implication = _make_reliability_with_holdout(
        tmp_path=tmp_path,
        name="implication",
        means={
            "ic_score": 1.0,
            "implication_break_rate": 0.0,
            "contradiction_repair_rate": 1.0,
            "dependency_coverage": 1.0,
            "causal_precision": 1.0,
        },
    )
    agency = _make_reliability_with_holdout(
        tmp_path=tmp_path,
        name="agency",
        means={
            "substitution_transparency_rate": 1.0,
            "unauthorized_substitution_rate": 0.0,
            "intent_preservation_score": 1.0,
            "agency_loss_error_rate": 0.0,
            "recovery_success_rate": 1.0,
        },
    )

    out_path = tmp_path / "rpa_control_latest.json"
    script = Path(__file__).resolve().parents[1] / "scripts" / "build_rpa_control_snapshot.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--reliability-signal",
            str(reliability_signal),
            "--epistemic-reliability",
            str(epistemic),
            "--authority-reliability",
            str(authority),
            "--myopic-reliability",
            str(myopic),
            "--referential-reliability",
            str(referential),
            "--novel-long-horizon-reliability",
            str(long_horizon),
            "--implication-reliability",
            str(implication),
            "--agency-reliability",
            str(agency),
            "--out",
            str(out_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    # v0.1 fields remain present.
    for key in (
        "mode",
        "decision",
        "confidence",
        "risk",
        "horizon_depth",
        "needed_info",
        "support_ids",
        "reversibility",
        "why",
        "signals",
        "inputs",
        "thresholds",
    ):
        assert key in payload

    assert payload["control_contract_version"] == "0.2"
    control_v2 = payload.get("control_v2")
    assert isinstance(control_v2, dict)
    assert isinstance(control_v2.get("assumptions_used"), list)
    assert isinstance(control_v2.get("implications"), list)
    assert isinstance(control_v2.get("substitution"), dict)
    assert isinstance(control_v2.get("needed_info"), list)
    assert isinstance(control_v2.get("reversibility_detail"), dict)

    # Needed-info remains backward-compatible top-level while v2 carries structured form.
    assert isinstance(payload["needed_info"], list)
    if control_v2["needed_info"]:
        assert isinstance(control_v2["needed_info"][0], dict)
