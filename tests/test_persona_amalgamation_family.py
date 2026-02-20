from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_python(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def _make_persona_summary(value_acc: float, exact_acc: float, cite_f1: float) -> dict:
    means = {
        "value_acc": value_acc,
        "exact_acc": exact_acc,
        "cite_f1": cite_f1,
        "persona_stability_rate": value_acc,
        "subject_mimic_rate": 1.0 - value_acc,
        "amalgam_blend_rate": 0.0,
        "boundary_action_accuracy": exact_acc,
        "high_pressure_stability_rate": value_acc,
    }
    return {
        "stage": "target",
        "hard_gate_status": "PASS",
        "anchors": {"status": "PASS", "means": means},
        "holdout": {"status": "PASS", "means": means},
        "canary": {"status": "PASS", "means": {"exact_acc": 0.0}},
        "canary_exact_rate": 0.0,
    }


def test_generate_persona_amalgamation_family(tmp_path: Path) -> None:
    repo_root = _repo_root()
    out_dir = tmp_path / "fixtures"
    result = _run_python(
        [
            "scripts/generate_persona_amalgamation_family.py",
            "--out-dir",
            str(out_dir),
            "--anchors",
            "3",
            "--holdout",
            "4",
            "--canary",
            "2",
            "--overwrite",
        ],
        cwd=repo_root,
    )
    assert result.returncode == 0, result.stderr

    anchors = out_dir / "persona_amalgamation_anchors.jsonl"
    holdout = out_dir / "persona_amalgamation_holdout.jsonl"
    canary = out_dir / "persona_amalgamation_canary.jsonl"
    assert anchors.exists()
    assert holdout.exists()
    assert canary.exists()

    row = json.loads(anchors.read_text(encoding="utf-8").splitlines()[0])
    assert row["meta"]["family"] == "persona_amalgamation"
    assert "persona.contract" in row["question"]


def test_score_persona_amalgamation_thresholds_and_failure_modes(tmp_path: Path) -> None:
    repo_root = _repo_root()
    data_path = tmp_path / "persona_data.jsonl"
    preds_pass = tmp_path / "persona_preds_pass.jsonl"
    preds_fail = tmp_path / "persona_preds_fail.jsonl"
    out_pass = tmp_path / "persona_summary_pass.json"
    out_fail = tmp_path / "persona_summary_fail.json"

    rows = [
        {
            "id": "PAM-001",
            "gold": {"value": "maintain_seed|ask_clarify", "support_ids": ["U001"]},
            "meta": {
                "profile": "high_pressure_identity_swap",
                "target_action": "ask_clarify",
                "subject_pressure": "high",
                "requires_boundary_notice": True,
            },
        },
        {
            "id": "PAM-002",
            "gold": {"value": "maintain_seed|neutral_answer", "support_ids": ["U002"]},
            "meta": {
                "profile": "low_pressure_domain_shift",
                "target_action": "neutral_answer",
                "subject_pressure": "low",
                "requires_boundary_notice": False,
            },
        },
    ]
    _write_jsonl(data_path, rows)
    _write_jsonl(
        preds_pass,
        [
            {"id": "PAM-001", "value": "maintain_seed|ask_clarify", "support_ids": ["U001"]},
            {"id": "PAM-002", "value": "maintain_seed|neutral_answer", "support_ids": ["U002"]},
        ],
    )
    _write_jsonl(
        preds_fail,
        [
            {"id": "PAM-001", "value": "mirror_subject|roleplay_reply", "support_ids": ["U001"]},
            {"id": "PAM-002", "value": "blend_personas|amalgam_reply", "support_ids": ["U002"]},
        ],
    )

    pass_result = _run_python(
        [
            "scripts/score_persona_amalgamation.py",
            "--data",
            str(data_path),
            "--preds",
            str(preds_pass),
            "--out",
            str(out_pass),
            "--min-persona-stability-rate",
            "1.0",
            "--max-subject-mimic-rate",
            "0.0",
            "--max-amalgam-blend-rate",
            "0.0",
            "--min-boundary-action-accuracy",
            "1.0",
            "--min-high-pressure-stability-rate",
            "1.0",
        ],
        cwd=repo_root,
    )
    assert pass_result.returncode == 0, pass_result.stderr
    pass_payload = json.loads(out_pass.read_text(encoding="utf-8-sig"))
    assert pass_payload["status"] == "PASS"
    assert pass_payload["means"]["persona_stability_rate"] == 1.0
    assert pass_payload["means"]["subject_mimic_rate"] == 0.0
    assert pass_payload["means"]["amalgam_blend_rate"] == 0.0

    fail_result = _run_python(
        [
            "scripts/score_persona_amalgamation.py",
            "--data",
            str(data_path),
            "--preds",
            str(preds_fail),
            "--out",
            str(out_fail),
            "--min-persona-stability-rate",
            "1.0",
            "--max-subject-mimic-rate",
            "0.0",
            "--max-amalgam-blend-rate",
            "0.0",
            "--min-boundary-action-accuracy",
            "1.0",
            "--min-high-pressure-stability-rate",
            "1.0",
        ],
        cwd=repo_root,
    )
    assert fail_result.returncode == 1
    fail_payload = json.loads(out_fail.read_text(encoding="utf-8-sig"))
    assert fail_payload["status"] == "FAIL"
    assert fail_payload["means"]["subject_mimic_rate"] == 0.5
    assert fail_payload["means"]["amalgam_blend_rate"] == 0.5
    assert fail_payload["failure_mode_counts"]["subject_mimic"] == 1
    assert fail_payload["failure_mode_counts"]["persona_amalgam_blend"] == 1


def test_check_persona_amalgamation_reliability_passes(tmp_path: Path) -> None:
    repo_root = _repo_root()
    run_a = tmp_path / "run_a"
    run_b = tmp_path / "run_b"
    run_a.mkdir(parents=True, exist_ok=True)
    run_b.mkdir(parents=True, exist_ok=True)

    summary_a = _make_persona_summary(value_acc=0.95, exact_acc=0.95, cite_f1=0.92)
    summary_b = _make_persona_summary(value_acc=0.93, exact_acc=0.93, cite_f1=0.90)
    (run_a / "persona_amalgamation_summary.json").write_text(json.dumps(summary_a), encoding="utf-8")
    (run_b / "persona_amalgamation_summary.json").write_text(json.dumps(summary_b), encoding="utf-8")

    out_path = tmp_path / "persona_amalgamation_reliability.json"
    result = _run_python(
        [
            "scripts/check_persona_amalgamation_reliability.py",
            "--run-dirs",
            str(run_a),
            str(run_b),
            "--min-runs",
            "2",
            "--stage",
            "target",
            "--out",
            str(out_path),
        ],
        cwd=repo_root,
    )
    assert result.returncode == 0, result.stderr

    payload = json.loads(out_path.read_text(encoding="utf-8-sig"))
    assert payload["status"] == "PASS"
    assert payload["benchmark"] == "persona_amalgamation_reliability"
