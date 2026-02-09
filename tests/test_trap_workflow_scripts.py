from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


def _load_compare_runs_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "compare_runs.py"
    spec = importlib.util.spec_from_file_location("compare_runs_script", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_compare_runs_latest_pair_supports_filters(tmp_path: Path) -> None:
    module = _load_compare_runs_module()
    runs_root = tmp_path / "runs"
    strict_old = runs_root / "rag_benchmark_001"
    strict_new = runs_root / "rag_benchmark_002"
    other = runs_root / "core_benchmark_003"
    strict_old.mkdir(parents=True)
    strict_new.mkdir(parents=True)
    other.mkdir(parents=True)

    _write_json(strict_old / "summary.json", {"benchmark": "rag_benchmark_strict"})
    _write_json(strict_new / "summary.json", {"benchmark": "rag_benchmark_strict"})
    _write_json(other / "summary.json", {"benchmark": "core_benchmark"})

    os.utime(strict_old / "summary.json", (10, 10))
    os.utime(strict_new / "summary.json", (20, 20))
    os.utime(other / "summary.json", (30, 30))

    pair = module._latest_pair(
        runs_root=runs_root,
        require_diagnosis=False,
        require_compact_state=False,
        benchmark="rag_benchmark_strict",
        run_name_prefix="rag_benchmark_",
    )
    assert pair is not None
    base_dir, other_dir = pair
    assert base_dir == strict_old
    assert other_dir == strict_new


def test_compare_runs_rag_strict_prints_mean_deltas(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    strict_old = runs_root / "rag_benchmark_001"
    strict_new = runs_root / "rag_benchmark_002"
    strict_old.mkdir(parents=True)
    strict_new.mkdir(parents=True)

    _write_json(
        strict_old / "summary.json",
        {
            "benchmark": "rag_benchmark_strict",
            "means": {
                "value_acc": 0.90,
                "exact_acc": 0.80,
                "entailment": 0.95,
                "answer_correct_given_selected": 0.94,
                "cite_f1": 0.85,
                "instruction_acc": 0.70,
                "state_integrity_rate": 0.75,
            },
        },
    )
    _write_json(
        strict_new / "summary.json",
        {
            "benchmark": "rag_benchmark_strict",
            "means": {
                "value_acc": 0.95,
                "exact_acc": 0.82,
                "entailment": 0.97,
                "answer_correct_given_selected": 0.96,
                "cite_f1": 0.90,
                "instruction_acc": 0.76,
                "state_integrity_rate": 0.88,
            },
        },
    )
    os.utime(strict_old / "summary.json", (10, 10))
    os.utime(strict_new / "summary.json", (20, 20))

    script = Path(__file__).resolve().parents[1] / "scripts" / "compare_runs.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--runs-root",
            str(runs_root),
            "--benchmark",
            "rag_benchmark_strict",
            "--latest-pair",
            "--allow-missing-diagnosis",
            "--print",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "## RAG mean deltas" in result.stdout
    assert "value_acc: 0.900000 -> 0.950000 (+0.050000)" in result.stdout


def test_minimize_counterexample_script(tmp_path: Path) -> None:
    drilldown = tmp_path / "drilldown.jsonl"
    out_path = tmp_path / "minimized.jsonl"
    _write_jsonl(
        drilldown,
        [
            {"id": "A", "question": "q1", "key": "tag.00", "reasons": ["value_mismatch"], "exact_ok": False},
            {"id": "B", "question": "q2", "key": "tag.01", "reasons": ["citation_mismatch"], "exact_ok": False},
            {"id": "C", "question": "q3", "key": "tag.01", "reasons": ["value_mismatch"], "exact_ok": False},
        ],
    )
    script = Path(__file__).resolve().parents[1] / "scripts" / "minimize_counterexample.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--drilldown",
            str(drilldown),
            "--out",
            str(out_path),
            "--max-rows",
            "2",
            "--cover-by",
            "both",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert 1 <= len(rows) <= 2
    assert all(not row.get("exact_ok") for row in rows)


def test_promote_failures_to_anchors_script(tmp_path: Path) -> None:
    data_path = tmp_path / "data.jsonl"
    drilldown = tmp_path / "drilldown.jsonl"
    out_path = tmp_path / "anchors.jsonl"
    _write_jsonl(
        data_path,
        [
            {"id": "A", "question": "q1", "meta": {"key": "tag.00"}, "gold": {"value": "x"}},
            {"id": "B", "question": "q2", "meta": {"key": "tag.01"}, "gold": {"value": "y"}},
        ],
    )
    _write_jsonl(
        drilldown,
        [
            {"id": "A", "question": "q1", "key": "tag.00", "reasons": ["value_mismatch"], "exact_ok": False},
            {"id": "B", "question": "q2", "key": "tag.01", "reasons": ["citation_mismatch"], "exact_ok": False},
        ],
    )
    script = Path(__file__).resolve().parents[1] / "scripts" / "promote_failures_to_anchors.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--data",
            str(data_path),
            "--drilldown",
            str(drilldown),
            "--out",
            str(out_path),
            "--max-anchors",
            "2",
            "--family",
            "test_family",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 2
    assert all(row.get("meta", {}).get("promoted_trap_family") == "test_family" for row in rows)


def test_check_rag_acceptance_bands_fast_pass(tmp_path: Path) -> None:
    base_summary = tmp_path / "base_summary_compact.json"
    other_summary = tmp_path / "other_summary_compact.json"
    _write_json(
        base_summary,
        {
            "benchmark": "rag_benchmark_strict",
            "means": {
                "value_acc": 0.9970,
                "exact_acc": 0.9960,
                "entailment": 0.9970,
                "answer_correct_given_selected": 0.9969,
                "cite_f1": 0.9980,
                "instruction_acc": 0.9950,
                "state_integrity_rate": 0.9960,
            },
        },
    )
    _write_json(
        other_summary,
        {
            "benchmark": "rag_benchmark_strict",
            "means": {
                "value_acc": 0.9960,
                "exact_acc": 0.9950,
                "entailment": 0.9960,
                "answer_correct_given_selected": 0.9959,
                "cite_f1": 0.9970,
                "instruction_acc": 0.9900,
                "state_integrity_rate": 0.9955,
            },
            "datasets": [
                {"id": "domain_stale", "exact_acc": 1.0},
                {"id": "domain_authority", "exact_acc": 1.0},
                {"id": "domain_exception", "exact_acc": 1.0},
            ],
        },
    )
    script = Path(__file__).resolve().parents[1] / "scripts" / "check_rag_acceptance_bands.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--stage",
            "fast",
            "--base",
            str(base_summary),
            "--other",
            str(other_summary),
            "--strict-benchmark-name",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "RESULT: PASS" in result.stdout


def test_check_rag_acceptance_bands_fast_fails_domain_check(tmp_path: Path) -> None:
    base_summary = tmp_path / "base_summary_compact.json"
    other_summary = tmp_path / "other_summary_compact.json"
    _write_json(
        base_summary,
        {
            "benchmark": "rag_benchmark_strict",
            "means": {
                "value_acc": 0.9970,
                "exact_acc": 0.9960,
                "entailment": 0.9970,
                "answer_correct_given_selected": 0.9969,
                "cite_f1": 0.9980,
                "instruction_acc": 0.9950,
                "state_integrity_rate": 0.9960,
            },
        },
    )
    _write_json(
        other_summary,
        {
            "benchmark": "rag_benchmark_strict",
            "means": {
                "value_acc": 0.9970,
                "exact_acc": 0.9960,
                "entailment": 0.9970,
                "answer_correct_given_selected": 0.9969,
                "cite_f1": 0.9980,
                "instruction_acc": 0.9950,
                "state_integrity_rate": 0.9960,
            },
            "datasets": [
                {"id": "domain_stale", "exact_acc": 1.0},
                {"id": "domain_authority", "exact_acc": 0.99},
                {"id": "domain_exception", "exact_acc": 1.0},
            ],
        },
    )
    script = Path(__file__).resolve().parents[1] / "scripts" / "check_rag_acceptance_bands.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--stage",
            "fast",
            "--base",
            str(base_summary),
            "--other",
            str(other_summary),
            "--strict-benchmark-name",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "domain_authority.exact_acc=0.990000" in result.stdout
    assert "RESULT: FAIL" in result.stdout


def test_check_rag_acceptance_bands_full_fails_band(tmp_path: Path) -> None:
    base_summary = tmp_path / "base_summary_compact.json"
    other_summary = tmp_path / "other_summary_compact.json"
    _write_json(
        base_summary,
        {
            "benchmark": "rag_benchmark_strict",
            "means": {
                "value_acc": 0.9970,
                "exact_acc": 0.9970,
                "entailment": 0.9970,
                "answer_correct_given_selected": 0.9970,
                "cite_f1": 0.9990,
                "instruction_acc": 0.9960,
                "state_integrity_rate": 0.9960,
            },
        },
    )
    _write_json(
        other_summary,
        {
            "benchmark": "rag_benchmark_strict",
            "means": {
                "value_acc": 0.9934,
                "exact_acc": 0.9970,
                "entailment": 0.9970,
                "answer_correct_given_selected": 0.9970,
                "cite_f1": 0.9990,
                "instruction_acc": 0.9960,
                "state_integrity_rate": 0.9960,
            },
        },
    )
    script = Path(__file__).resolve().parents[1] / "scripts" / "check_rag_acceptance_bands.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--stage",
            "full",
            "--base",
            str(base_summary),
            "--other",
            str(other_summary),
            "--strict-benchmark-name",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "[FAIL] value_acc:" in result.stdout
    assert "RESULT: FAIL" in result.stdout


def test_generate_compression_loss_bounded_family_script(tmp_path: Path) -> None:
    out_dir = tmp_path / "compression_loss_bounded"
    script = Path(__file__).resolve().parents[1] / "scripts" / "generate_compression_loss_bounded_family.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--out-dir",
            str(out_dir),
            "--anchors",
            "3",
            "--holdout",
            "5",
            "--canary",
            "2",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    anchors = [json.loads(line) for line in (out_dir / "compression_loss_bounded_anchors.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    holdout = [json.loads(line) for line in (out_dir / "compression_loss_bounded_holdout.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    canary = [json.loads(line) for line in (out_dir / "compression_loss_bounded_canary.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(anchors) == 3
    assert len(holdout) == 5
    assert len(canary) == 2
    assert anchors[0].get("meta", {}).get("family") == "compression_loss_bounded"
    assert isinstance(anchors[0].get("episode_id"), str)
    assert "## State Ledger" in str(anchors[0].get("book", ""))
    assert all(row.get("meta", {}).get("expected_fail") for row in canary)


def test_score_compression_loss_bounded_script(tmp_path: Path) -> None:
    data_path = tmp_path / "compression_loss_bounded_anchors.jsonl"
    preds_path = tmp_path / "preds.jsonl"
    out_path = tmp_path / "summary.json"
    rows_out = tmp_path / "rows.jsonl"
    _write_jsonl(
        data_path,
        [
            {
                "id": "A",
                "gold": {
                    "compact_state": {"retention_days_us": "45", "region_primary": "us-east"},
                    "value": "{\"compact_state\":{\"retention_days_us\":\"45\",\"region_primary\":\"us-east\"}}",
                },
            },
            {
                "id": "B",
                "gold": {
                    "compact_state": {"quota_gb": "500"},
                    "value": "{\"compact_state\":{\"quota_gb\":\"500\"}}",
                },
            },
        ],
    )
    _write_jsonl(
        preds_path,
        [
            {"id": "A", "value": "{\"compact_state\":{\"retention_days_us\":\"45\",\"region_primary\":\"us-east\"}}"},
            {"id": "B", "value": "{\"compact_state\":{\"quota_gb\":\"500\",\"extra\":\"1\"}}"},
        ],
    )
    script = Path(__file__).resolve().parents[1] / "scripts" / "score_compression_loss_bounded.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--data",
            str(data_path),
            "--preds",
            str(preds_path),
            "--out",
            str(out_path),
            "--rows-out",
            str(rows_out),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads(out_path.read_text(encoding="utf-8"))
    assert summary["status"] == "PASS"
    assert abs(summary["means"]["precision"] - 0.75) < 1e-9
    assert abs(summary["means"]["recall"] - 1.0) < 1e-9
    assert abs(summary["means"]["bloat"] - 0.5) < 1e-9


def test_score_compression_loss_bounded_threshold_fail(tmp_path: Path) -> None:
    data_path = tmp_path / "compression_loss_bounded_anchors.jsonl"
    preds_path = tmp_path / "preds.jsonl"
    out_path = tmp_path / "summary.json"
    _write_jsonl(
        data_path,
        [
            {
                "id": "A",
                "gold": {
                    "compact_state": {"quota_gb": "500"},
                    "value": "{\"compact_state\":{\"quota_gb\":\"500\"}}",
                },
            }
        ],
    )
    _write_jsonl(
        preds_path,
        [
            {"id": "A", "value": "{\"compact_state\":{\"quota_gb\":\"500\",\"extra\":\"1\"}}"},
        ],
    )
    script = Path(__file__).resolve().parents[1] / "scripts" / "score_compression_loss_bounded.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--data",
            str(data_path),
            "--preds",
            str(preds_path),
            "--out",
            str(out_path),
            "--max-bloat",
            "0.1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    summary = json.loads(out_path.read_text(encoding="utf-8"))
    assert summary["status"] == "FAIL"


def test_generate_compression_recoverability_family_script(tmp_path: Path) -> None:
    out_dir = tmp_path / "compression_recoverability"
    script = Path(__file__).resolve().parents[1] / "scripts" / "generate_compression_recoverability_family.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--out-dir",
            str(out_dir),
            "--anchors",
            "4",
            "--holdout",
            "6",
            "--canary",
            "4",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    anchors = [
        json.loads(line)
        for line in (out_dir / "compression_recoverability_anchors.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    holdout = [
        json.loads(line)
        for line in (out_dir / "compression_recoverability_holdout.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    canary = [
        json.loads(line)
        for line in (out_dir / "compression_recoverability_canary.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(anchors) == 4
    assert len(holdout) == 6
    assert len(canary) == 4
    assert anchors[0].get("meta", {}).get("family") == "compression_recoverability"
    assert isinstance(anchors[0].get("meta", {}).get("key"), str)
    assert anchors[0].get("meta", {}).get("derived_op") == "reports"
    assert isinstance(anchors[0].get("document"), str)
    assert "## State Ledger" in str(anchors[0].get("book", ""))
    assert all(row.get("meta", {}).get("expected_fail") for row in canary)
    assert all(row.get("meta", {}).get("query_position") == "tail" for row in canary)
    assert all(int(row.get("meta", {}).get("snapshot_key_count", 0)) >= 24 for row in canary)
    assert any(row.get("gold", {}).get("value") is None for row in canary)
    assert any(row.get("gold", {}).get("value") is not None for row in canary)


def test_score_compression_recoverability_script(tmp_path: Path) -> None:
    data_path = tmp_path / "compression_recoverability_anchors.jsonl"
    preds_path = tmp_path / "preds.jsonl"
    out_path = tmp_path / "summary.json"
    rows_out = tmp_path / "rows.jsonl"
    _write_jsonl(
        data_path,
        [
            {"id": "A", "gold": {"value": "us-east", "support_ids": ["U1"]}},
            {"id": "B", "gold": {"value": None, "support_ids": ["U2"]}},
        ],
    )
    _write_jsonl(
        preds_path,
        [
            {"id": "A", "value": "us-east", "support_ids": ["U1"]},
            {"id": "B", "value": None, "support_ids": ["U2"]},
        ],
    )
    script = Path(__file__).resolve().parents[1] / "scripts" / "score_compression_recoverability.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--data",
            str(data_path),
            "--preds",
            str(preds_path),
            "--out",
            str(out_path),
            "--rows-out",
            str(rows_out),
            "--min-value-acc",
            "0.90",
            "--min-exact-acc",
            "0.90",
            "--min-cite-f1",
            "0.90",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads(out_path.read_text(encoding="utf-8"))
    assert summary["status"] == "PASS"
    assert abs(summary["means"]["value_acc"] - 1.0) < 1e-9
    assert abs(summary["means"]["cite_f1"] - 1.0) < 1e-9


def test_score_compression_recoverability_threshold_fail(tmp_path: Path) -> None:
    data_path = tmp_path / "compression_recoverability_holdout.jsonl"
    preds_path = tmp_path / "preds.jsonl"
    out_path = tmp_path / "summary.json"
    _write_jsonl(
        data_path,
        [
            {"id": "A", "gold": {"value": "us-east", "support_ids": ["U1"]}},
        ],
    )
    _write_jsonl(
        preds_path,
        [
            {"id": "A", "value": "us-west", "support_ids": ["U9"]},
        ],
    )
    script = Path(__file__).resolve().parents[1] / "scripts" / "score_compression_recoverability.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--data",
            str(data_path),
            "--preds",
            str(preds_path),
            "--out",
            str(out_path),
            "--min-value-acc",
            "0.90",
            "--min-cite-f1",
            "0.90",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    summary = json.loads(out_path.read_text(encoding="utf-8"))
    assert summary["status"] == "FAIL"


def test_check_compression_reliability_pass(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_a = runs_root / "compression_families_a"
    run_b = runs_root / "compression_families_b"
    run_a.mkdir(parents=True)
    run_b.mkdir(parents=True)

    base = {
        "benchmark": "compression_families",
        "hard_gate_status": "PASS",
        "families": {
            "compression_loss_bounded": {
                "hard_gate_status": "PASS",
                "anchors": {"status": "PASS", "means": {"precision": 0.95, "recall": 0.95, "bloat": 0.0}},
                "holdout": {"status": "PASS", "means": {"precision": 0.95, "recall": 0.95, "bloat": 0.0}},
            },
            "compression_recoverability": {
                "hard_gate_status": "PASS",
                "anchors": {"status": "PASS", "means": {"value_acc": 0.95, "exact_acc": 0.95, "cite_f1": 0.95}},
                "holdout": {"status": "PASS", "means": {"value_acc": 0.95, "exact_acc": 0.95, "cite_f1": 0.95}},
            },
        },
    }
    other = {
        "benchmark": "compression_families",
        "hard_gate_status": "PASS",
        "families": {
            "compression_loss_bounded": {
                "hard_gate_status": "PASS",
                "anchors": {"status": "PASS", "means": {"precision": 0.94, "recall": 0.94, "bloat": 0.0}},
                "holdout": {"status": "PASS", "means": {"precision": 0.94, "recall": 0.94, "bloat": 0.0}},
            },
            "compression_recoverability": {
                "hard_gate_status": "PASS",
                "anchors": {"status": "PASS", "means": {"value_acc": 0.94, "exact_acc": 0.94, "cite_f1": 0.94}},
                "holdout": {"status": "PASS", "means": {"value_acc": 0.94, "exact_acc": 0.94, "cite_f1": 0.94}},
            },
        },
    }
    _write_json(run_a / "compression_families_summary.json", base)
    _write_json(run_b / "compression_families_summary.json", other)

    script = Path(__file__).resolve().parents[1] / "scripts" / "check_compression_reliability.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--run-dirs",
            str(run_a),
            str(run_b),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "RESULT: PASS" in result.stdout


def test_check_compression_reliability_fails_on_jitter(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_a = runs_root / "compression_families_a"
    run_b = runs_root / "compression_families_b"
    run_a.mkdir(parents=True)
    run_b.mkdir(parents=True)

    low = {
        "benchmark": "compression_families",
        "hard_gate_status": "PASS",
        "families": {
            "compression_loss_bounded": {
                "hard_gate_status": "PASS",
                "anchors": {"status": "PASS", "means": {"precision": 0.95, "recall": 0.95, "bloat": 0.0}},
                "holdout": {"status": "PASS", "means": {"precision": 0.90, "recall": 0.90, "bloat": 0.0}},
            },
            "compression_recoverability": {
                "hard_gate_status": "PASS",
                "anchors": {"status": "PASS", "means": {"value_acc": 0.95, "exact_acc": 0.95, "cite_f1": 0.95}},
                "holdout": {"status": "PASS", "means": {"value_acc": 0.90, "exact_acc": 0.90, "cite_f1": 0.95}},
            },
        },
    }
    high = {
        "benchmark": "compression_families",
        "hard_gate_status": "PASS",
        "families": {
            "compression_loss_bounded": {
                "hard_gate_status": "PASS",
                "anchors": {"status": "PASS", "means": {"precision": 0.96, "recall": 0.96, "bloat": 0.0}},
                "holdout": {"status": "PASS", "means": {"precision": 0.98, "recall": 0.98, "bloat": 0.0}},
            },
            "compression_recoverability": {
                "hard_gate_status": "PASS",
                "anchors": {"status": "PASS", "means": {"value_acc": 0.96, "exact_acc": 0.96, "cite_f1": 0.96}},
                "holdout": {"status": "PASS", "means": {"value_acc": 0.98, "exact_acc": 0.98, "cite_f1": 0.96}},
            },
        },
    }
    _write_json(run_a / "compression_families_summary.json", low)
    _write_json(run_b / "compression_families_summary.json", high)

    script = Path(__file__).resolve().parents[1] / "scripts" / "check_compression_reliability.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--run-dirs",
            str(run_a),
            str(run_b),
            "--clb-max-precision-jitter",
            "0.05",
            "--crv-max-value-acc-jitter",
            "0.03",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "RESULT: FAIL" in result.stdout


def test_check_compression_reliability_handles_bom_json(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_a = runs_root / "compression_families_a"
    run_b = runs_root / "compression_families_b"
    run_a.mkdir(parents=True)
    run_b.mkdir(parents=True)

    payload = {
        "benchmark": "compression_families",
        "hard_gate_status": "PASS",
        "families": {
            "compression_loss_bounded": {
                "hard_gate_status": "PASS",
                "anchors": {"status": "PASS", "means": {"precision": 0.95, "recall": 0.95, "bloat": 0.0}},
                "holdout": {"status": "PASS", "means": {"precision": 0.95, "recall": 0.95, "bloat": 0.0}},
            },
            "compression_recoverability": {
                "hard_gate_status": "PASS",
                "anchors": {"status": "PASS", "means": {"value_acc": 0.95, "exact_acc": 0.95, "cite_f1": 0.95}},
                "holdout": {"status": "PASS", "means": {"value_acc": 0.95, "exact_acc": 0.95, "cite_f1": 0.95}},
            },
        },
    }
    # Write with UTF-8 BOM to match Windows PowerShell UTF8 output behavior.
    (run_a / "compression_families_summary.json").write_text(json.dumps(payload), encoding="utf-8-sig")
    _write_json(run_b / "compression_families_summary.json", payload)

    script = Path(__file__).resolve().parents[1] / "scripts" / "check_compression_reliability.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--run-dirs",
            str(run_a),
            str(run_b),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "RESULT: PASS" in result.stdout


def test_generate_novel_continuity_family_script(tmp_path: Path) -> None:
    out_dir = tmp_path / "novel_continuity"
    script = Path(__file__).resolve().parents[1] / "scripts" / "generate_novel_continuity_family.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--out-dir",
            str(out_dir),
            "--anchors",
            "4",
            "--holdout",
            "6",
            "--canary",
            "3",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    anchors = [json.loads(line) for line in (out_dir / "novel_continuity_anchors.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    holdout = [json.loads(line) for line in (out_dir / "novel_continuity_holdout.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    canary = [json.loads(line) for line in (out_dir / "novel_continuity_canary.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(anchors) == 4
    assert len(holdout) == 6
    assert len(canary) == 3
    assert anchors[0].get("meta", {}).get("family") == "novel_continuity"
    assert isinstance(anchors[0].get("episode_id"), str)
    assert "## State Ledger" in str(anchors[0].get("book", ""))
    assert all(row.get("meta", {}).get("expected_fail") for row in canary)


def test_score_novel_continuity_script(tmp_path: Path) -> None:
    data_path = tmp_path / "novel_continuity_anchors.jsonl"
    preds_path = tmp_path / "preds.jsonl"
    out_path = tmp_path / "summary.json"
    rows_out = tmp_path / "rows.jsonl"
    _write_jsonl(
        data_path,
        [
            {"id": "A", "gold": {"value": "rook", "support_ids": ["U1"]}, "meta": {"dimension": "identity"}},
            {"id": "B", "gold": {"value": "tuesday", "support_ids": ["U2"]}, "meta": {"dimension": "timeline"}},
            {"id": "C", "gold": {"value": None, "support_ids": ["U3"]}, "meta": {"dimension": "constraint"}},
        ],
    )
    _write_jsonl(
        preds_path,
        [
            {"id": "A", "value": "rook", "support_ids": ["U1"]},
            {"id": "B", "value": "tuesday", "support_ids": ["U2"]},
            {"id": "C", "value": None, "support_ids": ["U3"]},
        ],
    )
    script = Path(__file__).resolve().parents[1] / "scripts" / "score_novel_continuity.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--data",
            str(data_path),
            "--preds",
            str(preds_path),
            "--out",
            str(out_path),
            "--rows-out",
            str(rows_out),
            "--min-value-acc",
            "0.90",
            "--min-exact-acc",
            "0.90",
            "--min-cite-f1",
            "0.90",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads(out_path.read_text(encoding="utf-8"))
    assert summary["status"] == "PASS"
    assert abs(summary["means"]["value_acc"] - 1.0) < 1e-9
    assert abs(summary["means"]["identity_acc"] - 1.0) < 1e-9


def test_check_novel_continuity_reliability_pass(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_a = runs_root / "novel_continuity_a"
    run_b = runs_root / "novel_continuity_b"
    run_a.mkdir(parents=True)
    run_b.mkdir(parents=True)

    payload_a = {
        "benchmark": "novel_continuity",
        "hard_gate_status": "PASS",
        "anchors": {"status": "PASS", "means": {"value_acc": 0.9, "exact_acc": 0.9, "cite_f1": 0.9}},
        "holdout": {
            "status": "PASS",
            "means": {
                "value_acc": 0.90,
                "exact_acc": 0.90,
                "cite_f1": 0.90,
                "identity_acc": 0.85,
                "timeline_acc": 0.85,
                "constraint_acc": 0.85,
            },
        },
    }
    payload_b = {
        "benchmark": "novel_continuity",
        "hard_gate_status": "PASS",
        "anchors": {"status": "PASS", "means": {"value_acc": 0.91, "exact_acc": 0.91, "cite_f1": 0.91}},
        "holdout": {
            "status": "PASS",
            "means": {
                "value_acc": 0.91,
                "exact_acc": 0.91,
                "cite_f1": 0.91,
                "identity_acc": 0.86,
                "timeline_acc": 0.86,
                "constraint_acc": 0.86,
            },
        },
    }
    _write_json(run_a / "novel_continuity_summary.json", payload_a)
    _write_json(run_b / "novel_continuity_summary.json", payload_b)

    script = Path(__file__).resolve().parents[1] / "scripts" / "check_novel_continuity_reliability.py"
    result = subprocess.run(
        [sys.executable, str(script), "--run-dirs", str(run_a), str(run_b)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "RESULT: PASS" in result.stdout


def test_check_novel_continuity_reliability_default_ignores_cite_floor(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_a = runs_root / "novel_continuity_a"
    run_b = runs_root / "novel_continuity_b"
    run_a.mkdir(parents=True)
    run_b.mkdir(parents=True)

    payload = {
        "benchmark": "novel_continuity",
        "hard_gate_status": "PASS",
        "anchors": {"status": "PASS", "means": {"value_acc": 1.0, "exact_acc": 1.0, "cite_f1": 0.0}},
        "holdout": {
            "status": "PASS",
            "means": {
                "value_acc": 1.0,
                "exact_acc": 1.0,
                "cite_f1": 0.0,
                "identity_acc": 1.0,
                "timeline_acc": 1.0,
                "constraint_acc": 1.0,
            },
        },
    }
    _write_json(run_a / "novel_continuity_summary.json", payload)
    _write_json(run_b / "novel_continuity_summary.json", payload)

    script = Path(__file__).resolve().parents[1] / "scripts" / "check_novel_continuity_reliability.py"
    result = subprocess.run(
        [sys.executable, str(script), "--run-dirs", str(run_a), str(run_b)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "RESULT: PASS" in result.stdout


def test_check_novel_continuity_reliability_target_stage_enforces_cite_floor(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_a = runs_root / "novel_continuity_a"
    run_b = runs_root / "novel_continuity_b"
    run_a.mkdir(parents=True)
    run_b.mkdir(parents=True)

    payload = {
        "benchmark": "novel_continuity",
        "hard_gate_status": "PASS",
        "anchors": {"status": "PASS", "means": {"value_acc": 1.0, "exact_acc": 1.0, "cite_f1": 0.0}},
        "holdout": {
            "status": "PASS",
            "means": {
                "value_acc": 1.0,
                "exact_acc": 1.0,
                "cite_f1": 0.0,
                "identity_acc": 1.0,
                "timeline_acc": 1.0,
                "constraint_acc": 1.0,
            },
        },
    }
    _write_json(run_a / "novel_continuity_summary.json", payload)
    _write_json(run_b / "novel_continuity_summary.json", payload)

    script = Path(__file__).resolve().parents[1] / "scripts" / "check_novel_continuity_reliability.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--run-dirs",
            str(run_a),
            str(run_b),
            "--cite-stage",
            "target",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "RESULT: FAIL" in result.stdout


def test_check_reliability_signal_pass(tmp_path: Path) -> None:
    strict_run = tmp_path / "rag_benchmark_001"
    strict_run.mkdir(parents=True)
    _write_json(
        strict_run / "summary_compact.json",
        {
            "benchmark": "rag_benchmark_strict",
            "status": "PASS",
            "means": {
                "value_acc": 0.99,
                "exact_acc": 0.99,
                "cite_f1": 0.99,
                "instruction_acc": 0.99,
                "state_integrity_rate": 0.99,
            },
            "datasets": [
                {"id": "domain_stale", "exact_acc": 1.0},
                {"id": "domain_authority", "exact_acc": 1.0},
                {"id": "domain_exception", "exact_acc": 1.0},
            ],
        },
    )
    strict_ptr = tmp_path / "latest_rag_strict"
    strict_ptr.write_text(str(strict_run), encoding="utf-8")

    compression = tmp_path / "compression_reliability_latest.json"
    novel = tmp_path / "novel_continuity_reliability_latest.json"
    authority = tmp_path / "authority_under_interference_reliability_latest.json"
    _write_json(compression, {"status": "PASS"})
    _write_json(novel, {"status": "PASS"})
    _write_json(authority, {"status": "PASS"})
    out = tmp_path / "reliability_signal_latest.json"

    script = Path(__file__).resolve().parents[1] / "scripts" / "check_reliability_signal.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--strict",
            str(strict_ptr),
            "--compression-reliability",
            str(compression),
            "--novel-reliability",
            str(novel),
            "--authority-interference-reliability",
            str(authority),
            "--compression-roundtrip-reliability",
            str(tmp_path / "missing_roundtrip.json"),
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "RESULT: PASS" in result.stdout
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"


def test_check_reliability_signal_fails_on_component_status(tmp_path: Path) -> None:
    strict_run = tmp_path / "rag_benchmark_001"
    strict_run.mkdir(parents=True)
    _write_json(
        strict_run / "summary_compact.json",
        {
            "benchmark": "rag_benchmark_strict",
            "status": "PASS",
            "means": {
                "value_acc": 0.99,
                "exact_acc": 0.99,
                "cite_f1": 0.99,
                "instruction_acc": 0.99,
                "state_integrity_rate": 0.99,
            },
            "datasets": [
                {"id": "domain_stale", "exact_acc": 1.0},
                {"id": "domain_authority", "exact_acc": 1.0},
                {"id": "domain_exception", "exact_acc": 1.0},
            ],
        },
    )
    strict_ptr = tmp_path / "latest_rag_strict"
    strict_ptr.write_text(str(strict_run), encoding="utf-8")

    compression = tmp_path / "compression_reliability_latest.json"
    novel = tmp_path / "novel_continuity_reliability_latest.json"
    authority = tmp_path / "authority_under_interference_reliability_latest.json"
    _write_json(compression, {"status": "FAIL"})
    _write_json(novel, {"status": "PASS"})
    _write_json(authority, {"status": "PASS"})

    script = Path(__file__).resolve().parents[1] / "scripts" / "check_reliability_signal.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--strict",
            str(strict_ptr),
            "--compression-reliability",
            str(compression),
            "--novel-reliability",
            str(novel),
            "--authority-interference-reliability",
            str(authority),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "RESULT: FAIL" in result.stdout


def test_check_reliability_signal_fails_on_authority_status(tmp_path: Path) -> None:
    strict_run = tmp_path / "rag_benchmark_001"
    strict_run.mkdir(parents=True)
    _write_json(
        strict_run / "summary_compact.json",
        {
            "benchmark": "rag_benchmark_strict",
            "status": "PASS",
            "means": {
                "value_acc": 0.99,
                "exact_acc": 0.99,
                "cite_f1": 0.99,
                "instruction_acc": 0.99,
                "state_integrity_rate": 0.99,
            },
            "datasets": [
                {"id": "domain_stale", "exact_acc": 1.0},
                {"id": "domain_authority", "exact_acc": 1.0},
                {"id": "domain_exception", "exact_acc": 1.0},
            ],
        },
    )
    strict_ptr = tmp_path / "latest_rag_strict"
    strict_ptr.write_text(str(strict_run), encoding="utf-8")

    compression = tmp_path / "compression_reliability_latest.json"
    novel = tmp_path / "novel_continuity_reliability_latest.json"
    authority = tmp_path / "authority_under_interference_reliability_latest.json"
    _write_json(compression, {"status": "PASS"})
    _write_json(novel, {"status": "PASS"})
    _write_json(authority, {"status": "FAIL"})

    script = Path(__file__).resolve().parents[1] / "scripts" / "check_reliability_signal.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--strict",
            str(strict_ptr),
            "--compression-reliability",
            str(compression),
            "--novel-reliability",
            str(novel),
            "--authority-interference-reliability",
            str(authority),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "RESULT: FAIL" in result.stdout


def _seed_reliability_signal_with_derived_components(tmp_path: Path) -> dict[str, Path]:
    strict_run = tmp_path / "rag_benchmark_001"
    strict_run.mkdir(parents=True)
    _write_json(
        strict_run / "summary_compact.json",
        {
            "benchmark": "rag_benchmark_strict",
            "status": "PASS",
            "means": {
                "value_acc": 0.99,
                "exact_acc": 0.99,
                "cite_f1": 0.99,
                "instruction_acc": 0.99,
                "state_integrity_rate": 0.99,
            },
            "datasets": [
                {"id": "domain_stale", "exact_acc": 1.0},
                {"id": "domain_authority", "exact_acc": 1.0},
                {"id": "domain_exception", "exact_acc": 1.0},
            ],
        },
    )
    strict_ptr = tmp_path / "latest_rag_strict"
    strict_ptr.write_text(str(strict_run), encoding="utf-8")

    compression = tmp_path / "compression_reliability_latest.json"
    novel = tmp_path / "novel_continuity_reliability_latest.json"
    authority = tmp_path / "authority_under_interference_reliability_latest.json"
    compression_roundtrip = tmp_path / "compression_roundtrip_generalization_reliability_latest.json"
    long_horizon = tmp_path / "novel_continuity_long_horizon_reliability_latest.json"
    myopic = tmp_path / "myopic_planning_traps_reliability_latest.json"
    referential = tmp_path / "referential_indexing_suite_reliability_latest.json"
    epistemic = tmp_path / "epistemic_calibration_suite_reliability_latest.json"
    authority_hardening = tmp_path / "authority_under_interference_hardening_reliability_latest.json"

    _write_json(compression, {"status": "PASS"})

    novel_run = tmp_path / "runs" / "novel_continuity_r1"
    novel_run.mkdir(parents=True)
    _write_json(
        novel_run / "novel_continuity_summary.json",
        {
            "holdout": {
                "status": "PASS",
                "means": {"identity_acc": 1.0, "timeline_acc": 1.0, "constraint_acc": 1.0},
            }
        },
    )
    _write_json(
        novel,
        {"benchmark": "novel_continuity_reliability", "status": "PASS", "runs": [str(novel_run)]},
    )

    authority_run = tmp_path / "runs" / "authority_under_interference_r1"
    authority_run.mkdir(parents=True)
    _write_json(
        authority_run / "authority_under_interference_summary.json",
        {
            "holdout": {
                "status": "PASS",
                "means": {
                    "latest_support_hit_rate": 1.0,
                    "cite_f1": 1.0,
                    "authority_violation_rate": 0.0,
                },
            }
        },
    )
    _write_json(
        authority,
        {
            "benchmark": "authority_under_interference_reliability",
            "status": "PASS",
            "runs": [str(authority_run)],
        },
    )

    roundtrip_run = tmp_path / "runs" / "compression_roundtrip_generalization_r1"
    roundtrip_run.mkdir(parents=True)
    _write_json(
        roundtrip_run / "compression_roundtrip_generalization_summary.json",
        {
            "holdout": {
                "status": "PASS",
                "means": {
                    "value_acc": 1.0,
                    "exact_acc": 1.0,
                    "cite_f1": 1.0,
                    "exception_acc": 1.0,
                    "tail_key_acc": 1.0,
                    "nonnull_target_acc": 1.0,
                },
            }
        },
    )
    _write_json(
        compression_roundtrip,
        {
            "benchmark": "compression_roundtrip_generalization_reliability",
            "status": "PASS",
            "runs": [str(roundtrip_run)],
        },
    )

    long_horizon_run = tmp_path / "runs" / "novel_continuity_long_horizon_r1"
    long_horizon_run.mkdir(parents=True)
    _write_json(
        long_horizon_run / "novel_continuity_long_horizon_summary.json",
        {
            "holdout": {
                "status": "PASS",
                "means": {
                    "identity_acc": 1.0,
                    "timeline_acc": 1.0,
                    "constraint_acc": 1.0,
                    "long_gap_acc": 1.0,
                    "high_contradiction_acc": 1.0,
                    "delayed_dependency_acc": 1.0,
                    "repair_transition_acc": 1.0,
                },
            }
        },
    )
    _write_json(
        long_horizon,
        {
            "benchmark": "novel_continuity_long_horizon_reliability",
            "status": "PASS",
            "runs": [str(long_horizon_run)],
        },
    )

    myopic_run = tmp_path / "runs" / "myopic_planning_traps_r1"
    myopic_run.mkdir(parents=True)
    _write_json(
        myopic_run / "myopic_planning_traps_summary.json",
        {
            "holdout": {
                "status": "PASS",
                "means": {
                    "horizon_success_rate": 1.0,
                    "recovery_rate": 1.0,
                    "trap_entry_rate": 0.0,
                    "first_error_step_mean": 5.0,
                },
            }
        },
    )
    _write_json(
        myopic,
        {"benchmark": "myopic_planning_traps_reliability", "status": "PASS", "runs": [str(myopic_run)]},
    )

    referential_run = tmp_path / "runs" / "referential_indexing_suite_r1"
    referential_run.mkdir(parents=True)
    _write_json(
        referential_run / "referential_indexing_suite_summary.json",
        {
            "holdout": {
                "status": "PASS",
                "means": {
                    "reassembly_fidelity": 1.0,
                    "part_coverage_recall": 1.0,
                    "pointer_precision": 1.0,
                    "pointer_recall": 1.0,
                    "hallucinated_expansion_rate": 0.0,
                    "stale_pointer_override_rate": 0.0,
                },
            }
        },
    )
    _write_json(
        referential,
        {
            "benchmark": "referential_indexing_suite_reliability",
            "status": "PASS",
            "runs": [str(referential_run)],
        },
    )

    epistemic_run = tmp_path / "runs" / "epistemic_calibration_suite_r1"
    epistemic_run.mkdir(parents=True)
    _write_json(
        epistemic_run / "epistemic_calibration_suite_summary.json",
        {
            "holdout": {
                "status": "PASS",
                "means": {
                    "kkyi": 1.0,
                    "abstain_f1": 1.0,
                    "selective_accuracy_at_coverage": 1.0,
                    "needed_info_recall": 1.0,
                    "overclaim_rate": 0.0,
                    "ece": 0.0,
                },
            }
        },
    )
    _write_json(
        epistemic,
        {
            "benchmark": "epistemic_calibration_suite_reliability",
            "status": "PASS",
            "runs": [str(epistemic_run)],
        },
    )

    authority_hardening_run = tmp_path / "runs" / "authority_under_interference_hardening_r1"
    authority_hardening_run.mkdir(parents=True)
    _write_json(
        authority_hardening_run / "authority_under_interference_hardening_summary.json",
        {
            "holdout": {
                "status": "PASS",
                "means": {
                    "latest_support_hit_rate": 1.0,
                    "cite_f1": 1.0,
                    "authority_violation_rate": 0.0,
                },
            }
        },
    )
    _write_json(
        authority_hardening,
        {
            "benchmark": "authority_under_interference_hardening_reliability",
            "status": "PASS",
            "runs": [str(authority_hardening_run)],
        },
    )

    return {
        "strict": strict_ptr,
        "compression": compression,
        "novel": novel,
        "authority": authority,
        "compression_roundtrip": compression_roundtrip,
        "novel_long_horizon": long_horizon,
        "myopic": myopic,
        "referential": referential,
        "epistemic": epistemic,
        "authority_hardening": authority_hardening,
    }


def test_check_reliability_signal_passes_with_derived_thresholds(tmp_path: Path) -> None:
    paths = _seed_reliability_signal_with_derived_components(tmp_path)
    out = tmp_path / "reliability_signal_latest.json"
    script = Path(__file__).resolve().parents[1] / "scripts" / "check_reliability_signal.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--strict",
            str(paths["strict"]),
            "--compression-reliability",
            str(paths["compression"]),
            "--novel-reliability",
            str(paths["novel"]),
            "--authority-interference-reliability",
            str(paths["authority"]),
            "--compression-roundtrip-reliability",
            str(paths["compression_roundtrip"]),
            "--novel-long-horizon-reliability",
            str(paths["novel_long_horizon"]),
            "--myopic-planning-reliability",
            str(paths["myopic"]),
            "--referential-indexing-reliability",
            str(paths["referential"]),
            "--epistemic-reliability",
            str(paths["epistemic"]),
            "--authority-hardening-reliability",
            str(paths["authority_hardening"]),
            "--require-compression-roundtrip",
            "--require-novel-long-horizon",
            "--require-myopic-planning",
            "--require-referential-indexing",
            "--require-epistemic",
            "--require-authority-hardening",
            "--min-reasoning-score",
            "0.90",
            "--min-planning-score",
            "0.90",
            "--min-intelligence-index",
            "0.90",
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "RESULT: PASS" in result.stdout
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"
    assert payload["derived"]["intelligence_index"] is not None
    assert payload["derived"]["intelligence_index"] >= 0.9


def test_check_reliability_signal_fails_when_derived_threshold_too_high(tmp_path: Path) -> None:
    paths = _seed_reliability_signal_with_derived_components(tmp_path)
    script = Path(__file__).resolve().parents[1] / "scripts" / "check_reliability_signal.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--strict",
            str(paths["strict"]),
            "--compression-reliability",
            str(paths["compression"]),
            "--novel-reliability",
            str(paths["novel"]),
            "--authority-interference-reliability",
            str(paths["authority"]),
            "--compression-roundtrip-reliability",
            str(paths["compression_roundtrip"]),
            "--novel-long-horizon-reliability",
            str(paths["novel_long_horizon"]),
            "--myopic-planning-reliability",
            str(paths["myopic"]),
            "--referential-indexing-reliability",
            str(paths["referential"]),
            "--epistemic-reliability",
            str(paths["epistemic"]),
            "--authority-hardening-reliability",
            str(paths["authority_hardening"]),
            "--require-compression-roundtrip",
            "--require-novel-long-horizon",
            "--require-myopic-planning",
            "--require-referential-indexing",
            "--require-epistemic",
            "--require-authority-hardening",
            "--min-intelligence-index",
            "1.01",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "derived.intelligence_index" in result.stdout
    assert "RESULT: FAIL" in result.stdout


def test_build_ui_sa_distillation_report_quiet(tmp_path: Path) -> None:
    variants_dir = tmp_path / "variants"
    variants_dir.mkdir(parents=True)
    summary_path = variants_dir / "summary.json"
    variant_out_path = variants_dir / "variant_a_search.json"
    report_out = variants_dir / "distillation_report.json"

    _write_json(
        summary_path,
        {
            "holdout_name": "",
            "variants": [
                {
                    "name": "variant_a",
                    "out": str(variant_out_path),
                }
            ],
        },
    )
    _write_json(
        variant_out_path,
        {
            "seed_runs": [
                {
                    "sa_beats_greedy": False,
                    "policy": {"sequence_metrics": {"task_pass_rate": 1.0}},
                    "greedy": {"sequence_metrics": {"task_pass_rate": 1.0}},
                    "sa": {
                        "sequence_metrics": {"task_pass_rate": 1.0},
                        "telemetry": {"move_stats": {}},
                    },
                }
            ]
        },
    )

    script = Path(__file__).resolve().parents[1] / "scripts" / "build_ui_sa_distillation_report.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--variants-dir",
            str(variants_dir),
            "--out",
            str(report_out),
            "--quiet",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().startswith("ui_sa_distillation_report:")
    assert report_out.exists()


def test_score_authority_under_interference_pass(tmp_path: Path) -> None:
    data_path = tmp_path / "aui_data.jsonl"
    preds_path = tmp_path / "aui_preds.jsonl"
    out_path = tmp_path / "aui_summary.json"
    rows_out = tmp_path / "aui_rows.jsonl"
    _write_jsonl(
        data_path,
        [
            {
                "id": "AUI-001",
                "gold": {"value": "30", "support_ids": ["UAAAA01"]},
                "meta": {
                    "latest_support_ids": ["UAAAA01"],
                    "note_support_ids": ["UNOTE01"],
                    "stale_support_ids": ["USTALE1", "USTALE2"],
                },
            },
            {
                "id": "AUI-002",
                "gold": {"value": None, "support_ids": ["UAAAA02"]},
                "meta": {
                    "latest_support_ids": ["UAAAA02"],
                    "note_support_ids": ["UNOTE02"],
                    "stale_support_ids": ["USTALE3"],
                },
            },
        ],
    )
    _write_jsonl(
        preds_path,
        [
            {"id": "AUI-001", "value": "30", "support_ids": ["UAAAA01"]},
            {"id": "AUI-002", "value": None, "support_ids": ["UAAAA02"]},
        ],
    )

    script = Path(__file__).resolve().parents[1] / "scripts" / "score_authority_under_interference.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--data",
            str(data_path),
            "--preds",
            str(preds_path),
            "--out",
            str(out_path),
            "--rows-out",
            str(rows_out),
            "--min-value-acc",
            "0.90",
            "--min-exact-acc",
            "0.90",
            "--min-cite-f1",
            "0.90",
            "--min-latest-support-hit-rate",
            "0.90",
            "--max-note-citation-rate",
            "0.00",
            "--max-stale-citation-rate",
            "0.00",
            "--max-authority-violation-rate",
            "0.00",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads(out_path.read_text(encoding="utf-8"))
    assert summary["status"] == "PASS"
    assert abs(summary["means"]["value_acc"] - 1.0) < 1e-9
    assert abs(summary["means"]["latest_support_hit_rate"] - 1.0) < 1e-9
    assert abs(summary["means"]["authority_violation_rate"] - 0.0) < 1e-9


def test_check_authority_under_interference_reliability_pass(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_a = runs_root / "aui_a"
    run_b = runs_root / "aui_b"
    run_a.mkdir(parents=True)
    run_b.mkdir(parents=True)

    payload_a = {
        "benchmark": "authority_under_interference",
        "hard_gate_status": "PASS",
        "canary_exact_rate": 0.75,
        "anchors": {"status": "PASS", "means": {"value_acc": 0.95, "exact_acc": 0.95, "cite_f1": 0.9}},
        "holdout": {
            "status": "PASS",
            "means": {
                "value_acc": 0.95,
                "exact_acc": 0.95,
                "cite_f1": 0.90,
                "latest_support_hit_rate": 0.95,
                "note_citation_rate": 0.00,
                "stale_citation_rate": 0.00,
                "authority_violation_rate": 0.00,
            },
        },
    }
    payload_b = {
        "benchmark": "authority_under_interference",
        "hard_gate_status": "PASS",
        "canary_exact_rate": 0.75,
        "anchors": {"status": "PASS", "means": {"value_acc": 0.96, "exact_acc": 0.96, "cite_f1": 0.91}},
        "holdout": {
            "status": "PASS",
            "means": {
                "value_acc": 0.96,
                "exact_acc": 0.96,
                "cite_f1": 0.91,
                "latest_support_hit_rate": 0.96,
                "note_citation_rate": 0.00,
                "stale_citation_rate": 0.00,
                "authority_violation_rate": 0.00,
            },
        },
    }
    _write_json(run_a / "authority_under_interference_summary.json", payload_a)
    _write_json(run_b / "authority_under_interference_summary.json", payload_b)

    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "check_authority_under_interference_reliability.py"
    )
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--run-dirs",
            str(run_a),
            str(run_b),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "RESULT: PASS" in result.stdout


def test_check_authority_under_interference_reliability_fails_on_canary_rate(
    tmp_path: Path,
) -> None:
    runs_root = tmp_path / "runs"
    run_a = runs_root / "aui_a"
    run_b = runs_root / "aui_b"
    run_a.mkdir(parents=True)
    run_b.mkdir(parents=True)

    payload = {
        "benchmark": "authority_under_interference",
        "hard_gate_status": "PASS",
        "canary_exact_rate": 1.00,
        "anchors": {"status": "PASS", "means": {"value_acc": 1.0, "exact_acc": 1.0, "cite_f1": 1.0}},
        "holdout": {
            "status": "PASS",
            "means": {
                "value_acc": 1.0,
                "exact_acc": 1.0,
                "cite_f1": 1.0,
                "latest_support_hit_rate": 1.0,
                "note_citation_rate": 0.0,
                "stale_citation_rate": 0.0,
                "authority_violation_rate": 0.0,
            },
        },
    }
    _write_json(run_a / "authority_under_interference_summary.json", payload)
    _write_json(run_b / "authority_under_interference_summary.json", payload)

    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "check_authority_under_interference_reliability.py"
    )
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--run-dirs",
            str(run_a),
            str(run_b),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "RESULT: FAIL" in result.stdout


def test_generate_novel_continuity_long_horizon_family_script(tmp_path: Path) -> None:
    out_dir = tmp_path / "novel_continuity_long_horizon"
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "generate_novel_continuity_long_horizon_family.py"
    )
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--out-dir",
            str(out_dir),
            "--anchors",
            "4",
            "--holdout",
            "6",
            "--canary",
            "3",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    anchors = [
        json.loads(line)
        for line in (out_dir / "novel_continuity_long_horizon_anchors.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    holdout = [
        json.loads(line)
        for line in (out_dir / "novel_continuity_long_horizon_holdout.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    canary = [
        json.loads(line)
        for line in (out_dir / "novel_continuity_long_horizon_canary.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert len(anchors) == 4
    assert len(holdout) == 6
    assert len(canary) == 3
    assert anchors[0].get("meta", {}).get("family") == "novel_continuity_long_horizon"
    assert "## State Ledger" in str(anchors[0].get("book", ""))
    assert isinstance(anchors[0].get("meta", {}).get("callback_gap_steps"), int)
    assert all(row.get("meta", {}).get("expected_fail") for row in canary)


def test_score_novel_continuity_long_horizon_script(tmp_path: Path) -> None:
    data_path = tmp_path / "novel_continuity_long_horizon_anchors.jsonl"
    preds_path = tmp_path / "preds.jsonl"
    out_path = tmp_path / "summary.json"
    _write_jsonl(
        data_path,
        [
            {
                "id": "LH-A",
                "gold": {"value": "rook", "support_ids": ["U1"]},
                "meta": {
                    "dimension": "identity",
                    "callback_gap_steps": 9,
                    "contradiction_pressure_count": 4,
                    "delayed_dependency": True,
                    "repair_transition": True,
                },
            },
            {
                "id": "LH-B",
                "gold": {"value": "tuesday", "support_ids": ["U2"]},
                "meta": {
                    "dimension": "timeline",
                    "callback_gap_steps": 10,
                    "contradiction_pressure_count": 4,
                    "delayed_dependency": False,
                    "repair_transition": True,
                },
            },
            {
                "id": "LH-C",
                "gold": {"value": None, "support_ids": ["U3"]},
                "meta": {
                    "dimension": "constraint",
                    "callback_gap_steps": 8,
                    "contradiction_pressure_count": 5,
                    "delayed_dependency": True,
                    "repair_transition": False,
                },
            },
        ],
    )
    _write_jsonl(
        preds_path,
        [
            {"id": "LH-A", "value": "rook", "support_ids": ["U1"]},
            {"id": "LH-B", "value": "tuesday", "support_ids": ["U2"]},
            {"id": "LH-C", "value": None, "support_ids": ["U3"]},
        ],
    )
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "score_novel_continuity_long_horizon.py"
    )
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--data",
            str(data_path),
            "--preds",
            str(preds_path),
            "--out",
            str(out_path),
            "--min-value-acc",
            "0.90",
            "--min-exact-acc",
            "0.90",
            "--min-cite-f1",
            "0.90",
            "--min-long-gap-acc",
            "0.90",
            "--min-high-contradiction-acc",
            "0.90",
            "--min-delayed-dependency-acc",
            "0.90",
            "--min-repair-transition-acc",
            "0.90",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads(out_path.read_text(encoding="utf-8"))
    assert summary["status"] == "PASS"
    assert abs(summary["means"]["value_acc"] - 1.0) < 1e-9
    assert abs(summary["means"]["long_gap_acc"] - 1.0) < 1e-9
    assert abs(summary["means"]["high_contradiction_acc"] - 1.0) < 1e-9


def test_check_novel_continuity_long_horizon_reliability_pass(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_a = runs_root / "nclh_a"
    run_b = runs_root / "nclh_b"
    run_a.mkdir(parents=True)
    run_b.mkdir(parents=True)

    payload = {
        "benchmark": "novel_continuity_long_horizon",
        "hard_gate_status": "PASS",
        "anchors": {"status": "PASS", "means": {"value_acc": 1.0, "exact_acc": 1.0, "cite_f1": 1.0}},
        "holdout": {
            "status": "PASS",
            "means": {
                "value_acc": 0.95,
                "exact_acc": 0.95,
                "cite_f1": 0.95,
                "identity_acc": 0.90,
                "timeline_acc": 0.90,
                "constraint_acc": 0.90,
                "long_gap_acc": 0.90,
                "high_contradiction_acc": 0.90,
                "delayed_dependency_acc": 0.90,
                "repair_transition_acc": 0.90,
            },
        },
    }
    _write_json(run_a / "novel_continuity_long_horizon_summary.json", payload)
    _write_json(run_b / "novel_continuity_long_horizon_summary.json", payload)

    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "check_novel_continuity_long_horizon_reliability.py"
    )
    result = subprocess.run(
        [sys.executable, str(script), "--run-dirs", str(run_a), str(run_b), "--cite-stage", "target"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "RESULT: PASS" in result.stdout


def test_check_reliability_signal_pass_when_optional_long_horizon_missing(tmp_path: Path) -> None:
    strict_run = tmp_path / "rag_benchmark_001"
    strict_run.mkdir(parents=True)
    _write_json(
        strict_run / "summary_compact.json",
        {
            "benchmark": "rag_benchmark_strict",
            "status": "PASS",
            "means": {
                "value_acc": 0.99,
                "exact_acc": 0.99,
                "cite_f1": 0.99,
                "instruction_acc": 0.99,
                "state_integrity_rate": 0.99,
            },
            "datasets": [
                {"id": "domain_stale", "exact_acc": 1.0},
                {"id": "domain_authority", "exact_acc": 1.0},
                {"id": "domain_exception", "exact_acc": 1.0},
            ],
        },
    )
    strict_ptr = tmp_path / "latest_rag_strict"
    strict_ptr.write_text(str(strict_run), encoding="utf-8")

    compression = tmp_path / "compression_reliability_latest.json"
    novel = tmp_path / "novel_continuity_reliability_latest.json"
    authority = tmp_path / "authority_under_interference_reliability_latest.json"
    _write_json(compression, {"status": "PASS"})
    _write_json(novel, {"status": "PASS"})
    _write_json(authority, {"status": "PASS"})

    script = Path(__file__).resolve().parents[1] / "scripts" / "check_reliability_signal.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--strict",
            str(strict_ptr),
            "--compression-reliability",
            str(compression),
            "--novel-reliability",
            str(novel),
            "--authority-interference-reliability",
            str(authority),
            "--compression-roundtrip-reliability",
            str(tmp_path / "missing_roundtrip.json"),
            "--novel-long-horizon-reliability",
            str(tmp_path / "missing_long_horizon.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "RESULT: PASS" in result.stdout
    assert "novel_continuity_long_horizon.status - optional artifact missing" in result.stdout


def test_check_reliability_signal_require_long_horizon_fails_when_missing(tmp_path: Path) -> None:
    strict_run = tmp_path / "rag_benchmark_001"
    strict_run.mkdir(parents=True)
    _write_json(
        strict_run / "summary_compact.json",
        {
            "benchmark": "rag_benchmark_strict",
            "status": "PASS",
            "means": {
                "value_acc": 0.99,
                "exact_acc": 0.99,
                "cite_f1": 0.99,
                "instruction_acc": 0.99,
                "state_integrity_rate": 0.99,
            },
            "datasets": [
                {"id": "domain_stale", "exact_acc": 1.0},
                {"id": "domain_authority", "exact_acc": 1.0},
                {"id": "domain_exception", "exact_acc": 1.0},
            ],
        },
    )
    strict_ptr = tmp_path / "latest_rag_strict"
    strict_ptr.write_text(str(strict_run), encoding="utf-8")

    compression = tmp_path / "compression_reliability_latest.json"
    novel = tmp_path / "novel_continuity_reliability_latest.json"
    authority = tmp_path / "authority_under_interference_reliability_latest.json"
    _write_json(compression, {"status": "PASS"})
    _write_json(novel, {"status": "PASS"})
    _write_json(authority, {"status": "PASS"})

    script = Path(__file__).resolve().parents[1] / "scripts" / "check_reliability_signal.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--strict",
            str(strict_ptr),
            "--compression-reliability",
            str(compression),
            "--novel-reliability",
            str(novel),
            "--authority-interference-reliability",
            str(authority),
            "--novel-long-horizon-reliability",
            str(tmp_path / "missing_long_horizon.json"),
            "--require-novel-long-horizon",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "RESULT: FAIL" in result.stdout


def test_generate_compression_roundtrip_generalization_family_script(tmp_path: Path) -> None:
    out_dir = tmp_path / "compression_roundtrip_generalization"
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "generate_compression_roundtrip_generalization_family.py"
    )
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--out-dir",
            str(out_dir),
            "--anchors",
            "4",
            "--holdout",
            "6",
            "--canary",
            "3",
            "--canary-key-count",
            "64",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    anchors = [
        json.loads(line)
        for line in (out_dir / "compression_roundtrip_generalization_anchors.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    holdout = [
        json.loads(line)
        for line in (out_dir / "compression_roundtrip_generalization_holdout.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    canary = [
        json.loads(line)
        for line in (out_dir / "compression_roundtrip_generalization_canary.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert len(anchors) == 4
    assert len(holdout) == 6
    assert len(canary) == 3
    assert anchors[0].get("meta", {}).get("family") == "compression_roundtrip_generalization"
    assert anchors[0].get("meta", {}).get("query_type") in {"direct", "aggregate", "exception", "negation"}
    assert "## State Ledger" in str(anchors[0].get("book", ""))
    assert all(row.get("meta", {}).get("expected_fail") for row in canary)


def test_score_compression_roundtrip_generalization_script(tmp_path: Path) -> None:
    data_path = tmp_path / "compression_roundtrip_generalization_anchors.jsonl"
    preds_path = tmp_path / "preds.jsonl"
    out_path = tmp_path / "summary.json"
    _write_jsonl(
        data_path,
        [
            {
                "id": "CRG-A",
                "gold": {"value": "us-east", "support_ids": ["U1"]},
                "meta": {
                    "query_type": "direct",
                    "query_position": "tail",
                    "query_target_type": "nonnull",
                    "snapshot_key_count": 72,
                },
            },
            {
                "id": "CRG-B",
                "gold": {"value": "2", "support_ids": ["U2", "U3", "U4"]},
                "meta": {
                    "query_type": "aggregate",
                    "query_position": "mixed",
                    "query_target_type": "nonnull",
                    "snapshot_key_count": 72,
                },
            },
            {
                "id": "CRG-C",
                "gold": {"value": "0", "support_ids": ["U5", "U6"]},
                "meta": {
                    "query_type": "exception",
                    "query_position": "head",
                    "query_target_type": "nonnull",
                    "snapshot_key_count": 72,
                },
            },
            {
                "id": "CRG-D",
                "gold": {"value": None, "support_ids": ["U7"]},
                "meta": {
                    "query_type": "negation",
                    "query_position": "tail",
                    "query_target_type": "null",
                    "snapshot_key_count": 72,
                },
            },
        ],
    )
    _write_jsonl(
        preds_path,
        [
            {"id": "CRG-A", "value": "us-east", "support_ids": ["U1"]},
            {"id": "CRG-B", "value": "2", "support_ids": ["U2", "U3", "U4"]},
            {"id": "CRG-C", "value": "0", "support_ids": ["U5", "U6"]},
            {"id": "CRG-D", "value": None, "support_ids": ["U7"]},
        ],
    )
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "score_compression_roundtrip_generalization.py"
    )
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--data",
            str(data_path),
            "--preds",
            str(preds_path),
            "--out",
            str(out_path),
            "--min-value-acc",
            "0.90",
            "--min-exact-acc",
            "0.90",
            "--min-cite-f1",
            "0.90",
            "--min-direct-acc",
            "0.90",
            "--min-aggregate-acc",
            "0.90",
            "--min-exception-acc",
            "0.90",
            "--min-negation-acc",
            "0.90",
            "--min-tail-key-acc",
            "0.90",
            "--min-null-target-acc",
            "0.90",
            "--min-nonnull-target-acc",
            "0.90",
            "--min-large-snapshot-acc",
            "0.90",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads(out_path.read_text(encoding="utf-8"))
    assert summary["status"] == "PASS"
    assert abs(summary["means"]["value_acc"] - 1.0) < 1e-9
    assert abs(summary["means"]["direct_acc"] - 1.0) < 1e-9
    assert abs(summary["means"]["aggregate_acc"] - 1.0) < 1e-9
    assert abs(summary["means"]["exception_acc"] - 1.0) < 1e-9
    assert abs(summary["means"]["negation_acc"] - 1.0) < 1e-9
    assert abs(summary["means"]["tail_key_acc"] - 1.0) < 1e-9
    assert abs(summary["means"]["null_target_acc"] - 1.0) < 1e-9
    assert abs(summary["means"]["nonnull_target_acc"] - 1.0) < 1e-9
    assert abs(summary["means"]["large_snapshot_acc"] - 1.0) < 1e-9


def test_check_compression_roundtrip_generalization_reliability_pass(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_a = runs_root / "crg_a"
    run_b = runs_root / "crg_b"
    run_a.mkdir(parents=True)
    run_b.mkdir(parents=True)

    payload = {
        "benchmark": "compression_roundtrip_generalization",
        "hard_gate_status": "PASS",
        "anchors": {"status": "PASS", "means": {"value_acc": 0.95, "exact_acc": 0.95, "cite_f1": 0.95}},
        "holdout": {
            "status": "PASS",
            "means": {
                "value_acc": 0.95,
                "exact_acc": 0.95,
                "cite_f1": 0.95,
                "direct_acc": 0.90,
                "aggregate_acc": 0.90,
                "exception_acc": 0.90,
                "negation_acc": 0.90,
                "tail_key_acc": 0.90,
                "null_target_acc": 0.90,
                "nonnull_target_acc": 0.90,
                "large_snapshot_acc": 0.90,
            },
        },
    }
    _write_json(run_a / "compression_roundtrip_generalization_summary.json", payload)
    _write_json(run_b / "compression_roundtrip_generalization_summary.json", payload)

    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "check_compression_roundtrip_generalization_reliability.py"
    )
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--run-dirs",
            str(run_a),
            str(run_b),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "RESULT: PASS" in result.stdout


def test_check_reliability_signal_pass_when_optional_roundtrip_missing(tmp_path: Path) -> None:
    strict_run = tmp_path / "rag_benchmark_001"
    strict_run.mkdir(parents=True)
    _write_json(
        strict_run / "summary_compact.json",
        {
            "benchmark": "rag_benchmark_strict",
            "status": "PASS",
            "means": {
                "value_acc": 0.99,
                "exact_acc": 0.99,
                "cite_f1": 0.99,
                "instruction_acc": 0.99,
                "state_integrity_rate": 0.99,
            },
            "datasets": [
                {"id": "domain_stale", "exact_acc": 1.0},
                {"id": "domain_authority", "exact_acc": 1.0},
                {"id": "domain_exception", "exact_acc": 1.0},
            ],
        },
    )
    strict_ptr = tmp_path / "latest_rag_strict"
    strict_ptr.write_text(str(strict_run), encoding="utf-8")

    compression = tmp_path / "compression_reliability_latest.json"
    novel = tmp_path / "novel_continuity_reliability_latest.json"
    authority = tmp_path / "authority_under_interference_reliability_latest.json"
    _write_json(compression, {"status": "PASS"})
    _write_json(novel, {"status": "PASS"})
    _write_json(authority, {"status": "PASS"})

    script = Path(__file__).resolve().parents[1] / "scripts" / "check_reliability_signal.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--strict",
            str(strict_ptr),
            "--compression-reliability",
            str(compression),
            "--novel-reliability",
            str(novel),
            "--authority-interference-reliability",
            str(authority),
            "--compression-roundtrip-reliability",
            str(tmp_path / "missing_roundtrip.json"),
            "--novel-long-horizon-reliability",
            str(tmp_path / "missing_long_horizon.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "RESULT: PASS" in result.stdout
    assert "compression_roundtrip_generalization.status - optional artifact missing" in result.stdout


def test_check_reliability_signal_require_roundtrip_fails_when_missing(tmp_path: Path) -> None:
    strict_run = tmp_path / "rag_benchmark_001"
    strict_run.mkdir(parents=True)
    _write_json(
        strict_run / "summary_compact.json",
        {
            "benchmark": "rag_benchmark_strict",
            "status": "PASS",
            "means": {
                "value_acc": 0.99,
                "exact_acc": 0.99,
                "cite_f1": 0.99,
                "instruction_acc": 0.99,
                "state_integrity_rate": 0.99,
            },
            "datasets": [
                {"id": "domain_stale", "exact_acc": 1.0},
                {"id": "domain_authority", "exact_acc": 1.0},
                {"id": "domain_exception", "exact_acc": 1.0},
            ],
        },
    )
    strict_ptr = tmp_path / "latest_rag_strict"
    strict_ptr.write_text(str(strict_run), encoding="utf-8")

    compression = tmp_path / "compression_reliability_latest.json"
    novel = tmp_path / "novel_continuity_reliability_latest.json"
    authority = tmp_path / "authority_under_interference_reliability_latest.json"
    _write_json(compression, {"status": "PASS"})
    _write_json(novel, {"status": "PASS"})
    _write_json(authority, {"status": "PASS"})

    script = Path(__file__).resolve().parents[1] / "scripts" / "check_reliability_signal.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--strict",
            str(strict_ptr),
            "--compression-reliability",
            str(compression),
            "--novel-reliability",
            str(novel),
            "--authority-interference-reliability",
            str(authority),
            "--compression-roundtrip-reliability",
            str(tmp_path / "missing_roundtrip.json"),
            "--require-compression-roundtrip",
            "--novel-long-horizon-reliability",
            str(tmp_path / "missing_long_horizon.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "RESULT: FAIL" in result.stdout
