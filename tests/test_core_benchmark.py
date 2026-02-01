from __future__ import annotations

import json
from pathlib import Path

from goldevidencebench.core_benchmark import (
    render_core_benchmark_report,
    summarize_core_benchmark,
)


def _write_payload(path: Path, policy_rate: float, greedy_rate: float, sa_rate: float) -> None:
    payload = {
        "rows": 3,
        "fixture": "data/fake_fixture.jsonl",
        "policy": {
            "sequence_metrics": {"task_pass_rate": policy_rate},
            "state_gate": {"state_gate_pass_rate": 1.0},
        },
        "greedy": {"sequence_metrics": {"task_pass_rate": greedy_rate}},
        "sa": {"sequence_metrics": {"task_pass_rate": sa_rate}},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_summarize_core_benchmark(tmp_path: Path) -> None:
    config_path = tmp_path / "core_benchmark.json"
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()

    config = {
        "name": "core_benchmark",
        "fixtures": [
            {
                "id": "fixture_a",
                "label": "Fixture A",
                "failure_mode": "mode_a",
                "fixture": "data/a.jsonl",
                "observed": "data/a_observed.jsonl",
            },
            {
                "id": "fixture_b",
                "label": "Fixture B",
                "failure_mode": "mode_b",
                "fixture": "data/b.jsonl",
                "observed": "data/b_observed.jsonl",
            },
        ],
    }
    config_path.write_text(json.dumps(config), encoding="utf-8")

    _write_payload(runs_dir / "bench_fixture_a.json", 1.0, 1.0, 0.0)
    _write_payload(runs_dir / "bench_fixture_b.json", 0.0, 1.0, 1.0)

    summary = summarize_core_benchmark(config_path, runs_dir)
    assert summary["fixtures_total"] == 2
    assert summary["fixtures_with_results"] == 2
    assert summary["missing"] == []
    assert summary["means"]["policy_task_pass_rate"] == 0.5

    report = render_core_benchmark_report(summary)
    assert "Core Benchmark Report" in report
    assert "fixture_a" in report
    assert "fixture_b" in report
