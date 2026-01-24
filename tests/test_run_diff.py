from __future__ import annotations

import json
from pathlib import Path

from goldevidencebench import run_diff


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_compare_runs_delta_and_report(tmp_path: Path) -> None:
    base_dir = tmp_path / "run_a"
    other_dir = tmp_path / "run_b"
    base_dir.mkdir()
    other_dir.mkdir()

    _write_json(
        base_dir / "diagnosis.json",
        {
            "status": "PASS",
            "primary_bottleneck": "answering",
            "holdout_name": None,
            "supporting_metrics": {
                "authority_violation_rate": 0.0,
                "drift_step_rate": 0.0,
            },
        },
    )
    _write_json(
        other_dir / "diagnosis.json",
        {
            "status": "FAIL",
            "primary_bottleneck": "authority",
            "holdout_name": "stale_tab_state",
            "supporting_metrics": {
                "authority_violation_rate": 0.2,
                "drift_step_rate": 0.5,
            },
        },
    )
    _write_json(
        base_dir / "compact_state.json",
        {
            "authority_mode": "filter_on",
            "rerank_mode": "latest_step",
            "last_known_good": {"gate_artifacts": ["drift_holdout_gate.json"]},
        },
    )
    _write_json(
        other_dir / "compact_state.json",
        {
            "authority_mode": "filter_off",
            "rerank_mode": "prefer_set_latest",
            "last_known_good": {"gate_artifacts": ["drift_holdout_gate.json"]},
        },
    )
    _write_json(base_dir / "drift_holdout_gate.json", {"status": "PASS"})
    _write_json(other_dir / "drift_holdout_gate.json", {"status": "FAIL"})
    _write_json(base_dir / "repro_commands.json", {"model": {"path": "a"}})
    _write_json(other_dir / "repro_commands.json", {"model": {"path": "b"}})

    delta = run_diff.compare_runs(base_dir=base_dir, other_dir=other_dir)
    regressions = {entry["metric"] for entry in delta["top_regressions"]}
    assert "authority_violation_rate" in regressions
    assert delta["gate_changes"][0]["artifact"] == "drift_holdout_gate.json"
    config_fields = {entry["field"] for entry in delta["config_changes"]}
    assert "authority_mode" in config_fields
    assert "rerank_mode" in config_fields

    report = run_diff.render_delta_report(delta)
    assert "Run Delta Report" in report
    assert "Top regressions" in report
