from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def _powershell_executable() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _run_script(script: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _run_powershell_file(script: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    powershell = _powershell_executable()
    if not powershell:
        pytest.skip("pwsh/powershell executable is required for runner integration tests")
    return subprocess.run(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_generate_persona_persistence_perturbations_includes_session_turns(tmp_path: Path) -> None:
    data_path = tmp_path / "base.jsonl"
    out_path = tmp_path / "persona_persistence.jsonl"
    _write_jsonl(
        data_path,
        [
            {
                "id": "R1",
                "question": "What is region?",
                "gold": {"value": "us-east", "support_ids": ["u1"]},
                "meta": {"family": "novel_continuity"},
            }
        ],
    )

    script = Path(__file__).resolve().parents[1] / "scripts" / "generate_persona_persistence_perturbations.py"
    result = _run_script(
        script,
        [
            "--in",
            str(data_path),
            "--out",
            str(out_path),
            "--profiles",
            "persona_confident_expert",
        ],
    )
    assert result.returncode == 0, result.stderr

    rows = _read_jsonl(out_path)
    assert len(rows) == 1
    row = rows[0]
    meta = row.get("meta", {})
    assert row["id"] == "R1_persona_persistence_persona_confident_expert"
    assert meta.get("persona_persistence_variant") is True
    assert meta.get("persona_base_row_id") == "R1"
    assert meta.get("persona_seed_profile") == "persona_confident_expert"
    assert meta.get("persona_override_profile") == "persona_creative_writer"
    question = row.get("question", "")
    assert "[TURN 1 USER]" in question
    assert "[TURN 2 USER]" in question
    assert "[TURN 3 USER]" in question
    assert "[ORIGINAL QUESTION]" in question


def _write_persistence_scoring_case(
    *,
    tmp_path: Path,
    canonical_pred: dict,
    perturbed_pred: dict,
) -> tuple[Path, Path, Path, Path, Path, Path]:
    canonical_data = tmp_path / "canonical_data.jsonl"
    perturbed_data = tmp_path / "perturbed_data.jsonl"
    canonical_preds = tmp_path / "canonical_preds.jsonl"
    perturbed_preds = tmp_path / "perturbed_preds.jsonl"
    out_path = tmp_path / "persona_persistence_summary.json"
    rows_out = tmp_path / "persona_persistence_rows.jsonl"

    _write_jsonl(
        canonical_data,
        [
            {
                "id": "R1",
                "question": "Q",
                "gold": {"value": "alpha", "support_ids": ["U1"]},
                "meta": {"family": "novel_continuity"},
            }
        ],
    )
    _write_jsonl(
        perturbed_data,
        [
            {
                "id": "R1_persona_persistence_persona_confident_expert",
                "question": "multi turn Q",
                "gold": {"value": "alpha", "support_ids": ["U1"]},
                "meta": {
                    "family": "novel_continuity",
                    "persona_persistence_variant": True,
                    "persona_base_row_id": "R1",
                    "persona_profile": "persona_confident_expert",
                    "persona_seed_profile": "persona_confident_expert",
                    "persona_override_profile": "persona_creative_writer",
                    "persona_profile_version": "v1",
                },
            }
        ],
    )
    _write_jsonl(canonical_preds, [canonical_pred])
    _write_jsonl(perturbed_preds, [perturbed_pred])
    return canonical_data, perturbed_data, canonical_preds, perturbed_preds, out_path, rows_out


def _run_score_persona_persistence_drift(
    *,
    canonical_data: Path,
    perturbed_data: Path,
    canonical_preds: Path,
    perturbed_preds: Path,
    out_path: Path,
    rows_out: Path,
) -> subprocess.CompletedProcess[str]:
    script = Path(__file__).resolve().parents[1] / "scripts" / "score_persona_persistence_drift.py"
    return _run_script(
        script,
        [
            "--canonical-preds",
            str(canonical_preds),
            "--perturbed-preds",
            str(perturbed_preds),
            "--canonical-data",
            str(canonical_data),
            "--perturbed-data",
            str(perturbed_data),
            "--out",
            str(out_path),
            "--rows-out",
            str(rows_out),
        ],
    )


def test_score_persona_persistence_drift_exact_match_passes(tmp_path: Path) -> None:
    canonical_data, perturbed_data, canonical_preds, perturbed_preds, out_path, rows_out = _write_persistence_scoring_case(
        tmp_path=tmp_path,
        canonical_pred={"id": "R1", "value": "alpha", "support_ids": ["U1"]},
        perturbed_pred={
            "id": "R1_persona_persistence_persona_confident_expert",
            "value": "alpha",
            "support_ids": ["u1"],
        },
    )
    result = _run_score_persona_persistence_drift(
        canonical_data=canonical_data,
        perturbed_data=perturbed_data,
        canonical_preds=canonical_preds,
        perturbed_preds=perturbed_preds,
        out_path=out_path,
        rows_out=rows_out,
    )
    assert result.returncode == 0, result.stderr
    summary = _read_json(out_path)
    assert summary["benchmark"] == "persona_persistence_drift"
    assert summary["status"] == "PASS"
    assert summary["row_invariance_rate"] == 1.0
    assert summary["drift_rate"] == 0.0
    assert summary["rows_changed"] == 0


def test_score_persona_persistence_drift_value_change_fails(tmp_path: Path) -> None:
    canonical_data, perturbed_data, canonical_preds, perturbed_preds, out_path, rows_out = _write_persistence_scoring_case(
        tmp_path=tmp_path,
        canonical_pred={"id": "R1", "value": "alpha", "support_ids": ["U1"]},
        perturbed_pred={
            "id": "R1_persona_persistence_persona_confident_expert",
            "value": "beta",
            "support_ids": ["U1"],
        },
    )
    result = _run_score_persona_persistence_drift(
        canonical_data=canonical_data,
        perturbed_data=perturbed_data,
        canonical_preds=canonical_preds,
        perturbed_preds=perturbed_preds,
        out_path=out_path,
        rows_out=rows_out,
    )
    assert result.returncode == 1
    summary = _read_json(out_path)
    assert summary["status"] == "FAIL"
    assert summary["change_reasons"]["value_changed"] == 1
    assert summary["drift_rate"] == 1.0


@pytest.mark.skipif(os.name != "nt", reason="PowerShell runner integration is Windows-only")
def test_run_persona_persistence_drift_trap_writes_artifacts(tmp_path: Path) -> None:
    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "novel_continuity"
        / "novel_continuity_holdout_real_public.jsonl"
    )
    fixture_rows = [json.loads(line) for line in fixture_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    base_row = fixture_rows[0]
    base_row_id = str(base_row["id"])
    gold = base_row.get("gold", {})
    canonical_value = gold.get("value")
    canonical_support = gold.get("support_ids", [])

    out_root = tmp_path / "persona_persistence_runner_pass"
    canonical_data = out_root / "canonical_data.jsonl"
    canonical_preds = out_root / "canonical_preds.jsonl"
    summary_out = out_root / "persona_persistence_drift_summary.json"
    rows_out = out_root / "persona_persistence_drift_rows.jsonl"
    _write_jsonl(canonical_data, [base_row])
    _write_jsonl(
        canonical_preds,
        [
            {
                "id": base_row_id,
                "value": canonical_value,
                "support_ids": canonical_support,
            }
        ],
    )

    script = Path(__file__).resolve().parents[1] / "scripts" / "run_persona_persistence_drift_trap.ps1"
    result = _run_powershell_file(
        script,
        [
            "-CanonicalData",
            str(canonical_data),
            "-CanonicalPreds",
            str(canonical_preds),
            "-OutRoot",
            str(out_root),
            "-Adapter",
            "goldevidencebench.adapters.mock_adapter:create_adapter",
            "-SummaryPath",
            str(summary_out),
            "-RowsPath",
            str(rows_out),
        ],
    )
    assert result.returncode == 0, result.stderr
    assert summary_out.exists()
    assert rows_out.exists()
    summary = _read_json(summary_out)
    assert summary["status"] == "PASS"
    assert summary["row_invariance_rate"] == 1.0


@pytest.mark.skipif(os.name != "nt", reason="PowerShell runner integration is Windows-only")
def test_run_persona_persistence_drift_trap_hard_fail_on_mismatch(tmp_path: Path) -> None:
    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "novel_continuity"
        / "novel_continuity_holdout_real_public.jsonl"
    )
    fixture_rows = [json.loads(line) for line in fixture_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    base_row = fixture_rows[0]
    base_row_id = str(base_row["id"])

    out_root = tmp_path / "persona_persistence_runner_fail"
    canonical_data = out_root / "canonical_data.jsonl"
    canonical_preds = out_root / "canonical_preds.jsonl"
    summary_out = out_root / "persona_persistence_drift_summary.json"
    rows_out = out_root / "persona_persistence_drift_rows.jsonl"
    _write_jsonl(canonical_data, [base_row])
    _write_jsonl(
        canonical_preds,
        [
            {
                "id": base_row_id,
                "value": "__INTENTIONAL_MISMATCH__",
                "support_ids": ["U1"],
            }
        ],
    )

    script = Path(__file__).resolve().parents[1] / "scripts" / "run_persona_persistence_drift_trap.ps1"
    result = _run_powershell_file(
        script,
        [
            "-CanonicalData",
            str(canonical_data),
            "-CanonicalPreds",
            str(canonical_preds),
            "-OutRoot",
            str(out_root),
            "-Adapter",
            "goldevidencebench.adapters.mock_adapter:create_adapter",
            "-SummaryPath",
            str(summary_out),
            "-RowsPath",
            str(rows_out),
        ],
    )
    assert result.returncode != 0
    assert summary_out.exists()
    summary = _read_json(summary_out)
    assert summary["status"] == "FAIL"
    assert summary["row_invariance_rate"] < 1.0
