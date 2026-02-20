from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_script(script_rel: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    script = _repo_root() / script_rel
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(_repo_root()),
    )


def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        rows.append(json.loads(text))
    return rows


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row))
            handle.write("\n")


def test_generate_implication_coherence_includes_hard_inference_rows(tmp_path: Path) -> None:
    out_dir = tmp_path / "implication_coherence"
    result = _run_script(
        "scripts/generate_implication_coherence_family.py",
        [
            "--out-dir",
            str(out_dir),
            "--anchors",
            "12",
            "--holdout",
            "24",
            "--canary",
            "3",
            "--overwrite",
            "--seed",
            "11",
        ],
    )
    assert result.returncode == 0, result.stderr

    holdout_rows = _read_jsonl(out_dir / "implication_coherence_holdout.jsonl")
    hard_rows = [
        row
        for row in holdout_rows
        if bool((row.get("meta") or {}).get("hard_inference_required", False))
    ]
    assert len(hard_rows) >= 8
    assert any((row.get("meta") or {}).get("contract_source") == "explicit_contract" for row in holdout_rows)

    sample_hard = hard_rows[0]
    assert "Infer latest authoritative value for `implication.contract`" in str(sample_hard.get("question", ""))
    assert (sample_hard.get("meta") or {}).get("contract_source") == "derived_policy"
    assert len((sample_hard.get("gold") or {}).get("support_ids") or []) >= 5


def test_score_implication_coherence_hard_metrics_and_thresholds(tmp_path: Path) -> None:
    data_path = tmp_path / "data.jsonl"
    preds_path = tmp_path / "preds.jsonl"
    out_path = tmp_path / "summary.json"

    data_rows = [
        {
            "id": "hard-1",
            "gold": {"value": "plan|logical", "support_ids": ["U1", "U2", "U3", "U4", "U5"]},
            "meta": {
                "profile": "hard_propagation_hotfix_chain",
                "difficulty": "hard",
                "hard_inference_required": True,
                "dependency_required": False,
                "contradiction_detected": False,
                "causal_precision_required": False,
                "propagation_required": True,
                "target_propagation_latency_steps": 1.5,
                "implication_break_if_missed": True,
            },
        },
        {
            "id": "hard-2",
            "gold": {"value": "retrieve|logical", "support_ids": ["U6", "U7", "U8", "U9", "U10"]},
            "meta": {
                "profile": "hard_contradiction_reopens_latest",
                "difficulty": "hard",
                "hard_inference_required": True,
                "dependency_required": False,
                "contradiction_detected": True,
                "causal_precision_required": False,
                "propagation_required": True,
                "target_propagation_latency_steps": 1.0,
                "implication_break_if_missed": True,
            },
        },
        {
            "id": "base-1",
            "gold": {"value": "ask|logical", "support_ids": ["U11"]},
            "meta": {
                "profile": "dependency_omission",
                "difficulty": "base",
                "hard_inference_required": False,
                "dependency_required": True,
                "contradiction_detected": False,
                "causal_precision_required": False,
                "propagation_required": False,
                "target_propagation_latency_steps": 2.0,
                "implication_break_if_missed": True,
            },
        },
    ]
    pred_rows = [
        {"id": "hard-1", "value": "plan|logical", "support_ids": ["U1", "U2", "U3", "U4", "U5"]},
        {"id": "hard-2", "value": "ask|logical", "support_ids": []},
        {"id": "base-1", "value": "ask|logical", "support_ids": ["U11"]},
    ]
    _write_jsonl(data_path, data_rows)
    _write_jsonl(preds_path, pred_rows)

    pass_result = _run_script(
        "scripts/score_implication_coherence.py",
        [
            "--data",
            str(data_path),
            "--preds",
            str(preds_path),
            "--out",
            str(out_path),
            "--min-value-acc",
            "0.60",
            "--min-hard-case-count",
            "2",
            "--min-hard-case-value-acc",
            "0.49",
            "--min-hard-case-cite-f1",
            "0.49",
            "--max-hard-implication-break-rate",
            "0.60",
            "--min-hard-ic-score",
            "0.50",
        ],
    )
    assert pass_result.returncode == 0, pass_result.stderr

    summary = json.loads(out_path.read_text(encoding="utf-8-sig"))
    means = summary["means"]
    assert means["hard_case_count"] == 2.0
    assert means["hard_case_value_acc"] == 0.5
    assert means["hard_case_cite_f1"] == 0.5
    assert means["hard_implication_break_rate"] == 0.5
    assert means["hard_ic_score"] == 0.5
    assert summary["status"] == "PASS"

    fail_result = _run_script(
        "scripts/score_implication_coherence.py",
        [
            "--data",
            str(data_path),
            "--preds",
            str(preds_path),
            "--out",
            str(out_path),
            "--min-hard-case-value-acc",
            "0.80",
        ],
    )
    assert fail_result.returncode == 1
    failed = json.loads(out_path.read_text(encoding="utf-8-sig"))
    assert failed["status"] == "FAIL"
    assert any("hard_case_value_acc" in item for item in failed["failures"])
