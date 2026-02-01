from __future__ import annotations

import json
from pathlib import Path

from goldevidencebench.rag_benchmark import (
    render_rag_benchmark_report,
    summarize_rag_benchmark,
)


def _write_payload(path: Path, value_acc: float, cite_f1: float) -> None:
    payload = {
        "metrics": {
            "value_acc": value_acc,
            "cite_f1": cite_f1,
            "instruction_acc": 1.0,
            "state_integrity_rate": 1.0,
            "instr_override_rate": 0.0,
        }
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_summarize_rag_benchmark(tmp_path: Path) -> None:
    config_path = tmp_path / "rag_benchmark.json"
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()

    config = {
        "name": "rag_benchmark",
        "datasets": [
            {
                "id": "dataset_a",
                "label": "Dataset A",
                "failure_mode": "mode_a",
                "data": "data/a.jsonl",
            },
            {
                "id": "dataset_b",
                "label": "Dataset B",
                "failure_mode": "mode_b",
                "data": "data/b.jsonl",
            },
        ],
    }
    config_path.write_text(json.dumps(config), encoding="utf-8")

    _write_payload(runs_dir / "rag_dataset_a.json", 1.0, 0.5)
    _write_payload(runs_dir / "rag_dataset_b.json", 0.0, 1.0)

    summary = summarize_rag_benchmark(config_path, runs_dir)
    assert summary["datasets_total"] == 2
    assert summary["datasets_with_results"] == 2
    assert summary["missing"] == []
    assert summary["means"]["value_acc"] == 0.5
    assert summary["means"]["cite_f1"] == 0.75

    report = render_rag_benchmark_report(summary)
    assert "RAG Benchmark Report" in report
    assert "dataset_a" in report
    assert "dataset_b" in report
