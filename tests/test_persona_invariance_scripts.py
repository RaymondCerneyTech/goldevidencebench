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


def test_generate_persona_perturbations_preserves_gold_and_ids(tmp_path: Path) -> None:
    data_path = tmp_path / "base.jsonl"
    out_path = tmp_path / "persona.jsonl"
    _write_jsonl(
        data_path,
        [
            {
                "id": "R1",
                "question": "What is region?",
                "gold": {"value": "us-east", "support_ids": ["u1"]},
                "meta": {"family": "novel_continuity"},
            },
            {
                "id": "R2",
                "question": "What is quota?",
                "gold": {"value": "500", "support_ids": ["u2"]},
                "meta": {"family": "novel_continuity"},
            },
        ],
    )

    script = Path(__file__).resolve().parents[1] / "scripts" / "generate_persona_perturbations.py"
    result = _run_script(
        script,
        [
            "--in",
            str(data_path),
            "--out",
            str(out_path),
            "--profiles",
            "persona_confident_expert,persona_ultra_brief",
        ],
    )
    assert result.returncode == 0, result.stderr

    rows = _read_jsonl(out_path)
    assert len(rows) == 4
    for row in rows:
        base_id = row["meta"]["persona_base_row_id"]
        assert row["id"].startswith(f"{base_id}_persona_")
        if base_id == "R1":
            assert row["gold"] == {"value": "us-east", "support_ids": ["u1"]}
        elif base_id == "R2":
            assert row["gold"] == {"value": "500", "support_ids": ["u2"]}
        else:
            raise AssertionError(f"Unexpected base id: {base_id}")


def test_generate_persona_perturbations_adds_meta_fields(tmp_path: Path) -> None:
    data_path = tmp_path / "base.jsonl"
    out_path = tmp_path / "persona.jsonl"
    _write_jsonl(
        data_path,
        [
            {
                "id": "X1",
                "question": "Q?",
                "gold": {"value": "A", "support_ids": ["U1"]},
                "meta": {"family": "myopic_planning_traps"},
            }
        ],
    )

    script = Path(__file__).resolve().parents[1] / "scripts" / "generate_persona_perturbations.py"
    result = _run_script(
        script,
        [
            "--in",
            str(data_path),
            "--out",
            str(out_path),
        ],
    )
    assert result.returncode == 0, result.stderr

    rows = _read_jsonl(out_path)
    assert len(rows) == 4
    for row in rows:
        meta = row.get("meta", {})
        assert meta.get("persona_variant") is True
        assert meta.get("persona_base_row_id") == "X1"
        assert meta.get("persona_profile") in {
            "persona_confident_expert",
            "persona_creative_writer",
            "persona_ultra_brief",
            "persona_overly_helpful",
        }
        assert meta.get("persona_profile_version") == "v1"
        assert "[PERSONA v1:" in row.get("question", "")


def _write_persona_scoring_case(
    *,
    tmp_path: Path,
    canonical_pred: dict,
    perturbed_pred: dict,
) -> tuple[Path, Path, Path, Path, Path, Path]:
    canonical_data = tmp_path / "canonical_data.jsonl"
    perturbed_data = tmp_path / "perturbed_data.jsonl"
    canonical_preds = tmp_path / "canonical_preds.jsonl"
    perturbed_preds = tmp_path / "perturbed_preds.jsonl"
    out_path = tmp_path / "persona_invariance_summary.json"
    rows_out = tmp_path / "persona_invariance_rows.jsonl"

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
                "id": "R1_persona_persona_confident_expert",
                "question": "persona Q",
                "gold": {"value": "alpha", "support_ids": ["U1"]},
                "meta": {
                    "family": "novel_continuity",
                    "persona_variant": True,
                    "persona_base_row_id": "R1",
                    "persona_profile": "persona_confident_expert",
                    "persona_profile_version": "v1",
                },
            }
        ],
    )
    _write_jsonl(canonical_preds, [canonical_pred])
    _write_jsonl(perturbed_preds, [perturbed_pred])
    return canonical_data, perturbed_data, canonical_preds, perturbed_preds, out_path, rows_out


def _run_score_persona_invariance(
    *,
    canonical_data: Path,
    perturbed_data: Path,
    canonical_preds: Path,
    perturbed_preds: Path,
    out_path: Path,
    rows_out: Path,
) -> subprocess.CompletedProcess[str]:
    script = Path(__file__).resolve().parents[1] / "scripts" / "score_persona_invariance.py"
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


def test_score_persona_invariance_exact_match_passes(tmp_path: Path) -> None:
    canonical_data, perturbed_data, canonical_preds, perturbed_preds, out_path, rows_out = _write_persona_scoring_case(
        tmp_path=tmp_path,
        canonical_pred={"id": "R1", "value": {"k": "v"}, "support_ids": ["u1"]},
        perturbed_pred={
            "id": "R1_persona_persona_confident_expert",
            "value": "{\"k\": \"v\"}",
            "support_ids": ["U1"],
        },
    )
    result = _run_score_persona_invariance(
        canonical_data=canonical_data,
        perturbed_data=perturbed_data,
        canonical_preds=canonical_preds,
        perturbed_preds=perturbed_preds,
        out_path=out_path,
        rows_out=rows_out,
    )
    assert result.returncode == 0, result.stderr
    summary = _read_json(out_path)
    assert summary["status"] == "PASS"
    assert summary["row_invariance_rate"] == 1.0
    assert summary["rows_changed"] == 0


def test_score_persona_invariance_value_change_fails(tmp_path: Path) -> None:
    canonical_data, perturbed_data, canonical_preds, perturbed_preds, out_path, rows_out = _write_persona_scoring_case(
        tmp_path=tmp_path,
        canonical_pred={"id": "R1", "value": "alpha", "support_ids": ["U1"]},
        perturbed_pred={
            "id": "R1_persona_persona_confident_expert",
            "value": "beta",
            "support_ids": ["U1"],
        },
    )
    result = _run_score_persona_invariance(
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


def test_score_persona_invariance_support_change_fails(tmp_path: Path) -> None:
    canonical_data, perturbed_data, canonical_preds, perturbed_preds, out_path, rows_out = _write_persona_scoring_case(
        tmp_path=tmp_path,
        canonical_pred={"id": "R1", "value": "alpha", "support_ids": ["U1"]},
        perturbed_pred={
            "id": "R1_persona_persona_confident_expert",
            "value": "alpha",
            "support_ids": ["U2"],
        },
    )
    result = _run_score_persona_invariance(
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
    assert summary["change_reasons"]["support_changed"] == 1


def test_score_persona_invariance_parse_change_classified(tmp_path: Path) -> None:
    canonical_data, perturbed_data, canonical_preds, perturbed_preds, out_path, rows_out = _write_persona_scoring_case(
        tmp_path=tmp_path,
        canonical_pred={"id": "R1", "value": "alpha", "support_ids": ["U1"]},
        perturbed_pred={
            "id": "R1_persona_persona_confident_expert",
            "value": "alpha",
        },
    )
    result = _run_score_persona_invariance(
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
    assert summary["change_reasons"]["parse_changed"] == 1
    rows = _read_jsonl(rows_out)
    assert rows[0]["invariant"] is False
    assert "parse_changed" in rows[0]["change_reasons"]


def test_score_persona_invariance_epistemic_abstain_equivalence_passes(tmp_path: Path) -> None:
    canonical_data = tmp_path / "canonical_data.jsonl"
    perturbed_data = tmp_path / "perturbed_data.jsonl"
    canonical_preds = tmp_path / "canonical_preds.jsonl"
    perturbed_preds = tmp_path / "perturbed_preds.jsonl"
    out_path = tmp_path / "persona_invariance_summary.json"
    rows_out = tmp_path / "persona_invariance_rows.jsonl"

    _write_jsonl(
        canonical_data,
        [
            {
                "id": "E1",
                "question": "Q",
                "gold": {"value": None, "support_ids": []},
                "meta": {"family": "epistemic_calibration_suite"},
            }
        ],
    )
    _write_jsonl(
        perturbed_data,
        [
            {
                "id": "E1_persona_persona_confident_expert",
                "question": "persona Q",
                "gold": {"value": None, "support_ids": []},
                "meta": {
                    "family": "epistemic_calibration_suite",
                    "persona_variant": True,
                    "persona_base_row_id": "E1",
                    "persona_profile": "persona_confident_expert",
                    "persona_profile_version": "v1",
                },
            }
        ],
    )
    _write_jsonl(
        canonical_preds,
        [
            {
                "id": "E1",
                "value": {
                    "decision": "retrieve",
                    "answer": None,
                    "confidence": 1.0,
                    "needed_info": ["policy.region_override_cap"],
                    "support_ids": [],
                },
                "support_ids": [],
            }
        ],
    )
    _write_jsonl(
        perturbed_preds,
        [
            {
                "id": "E1_persona_persona_confident_expert",
                "value": {
                    "decision": "abstain",
                    "answer": None,
                    "confidence": 1.0,
                    "needed_info": ["policy region override cap"],
                    "support_ids": [],
                },
                "support_ids": [],
            }
        ],
    )

    result = _run_score_persona_invariance(
        canonical_data=canonical_data,
        perturbed_data=perturbed_data,
        canonical_preds=canonical_preds,
        perturbed_preds=perturbed_preds,
        out_path=out_path,
        rows_out=rows_out,
    )
    assert result.returncode == 0, result.stderr
    summary = _read_json(out_path)
    assert summary["status"] == "PASS"
    assert summary["rows_changed"] == 0


def _write_family_summary(run_dir: Path, family: str, rate: float) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "benchmark": family,
        "persona_invariance": {
            "status": "PASS" if rate == 1.0 else "FAIL",
            "row_invariance_rate": rate,
            "rows_total": 10,
            "rows_changed": 0 if rate == 1.0 else 1,
        },
    }
    (run_dir / f"{family}_summary.json").write_text(json.dumps(payload), encoding="utf-8")


def test_check_persona_invariance_gate_fails_when_any_family_drifts(tmp_path: Path) -> None:
    run_a = tmp_path / "runs" / "novel_run"
    run_b = tmp_path / "runs" / "myopic_run"
    _write_family_summary(run_a, "novel_continuity", 1.0)
    _write_family_summary(run_b, "myopic_planning_traps", 0.9)

    rel_a = tmp_path / "novel_reliability.json"
    rel_b = tmp_path / "myopic_reliability.json"
    rel_a.write_text(json.dumps({"runs": [str(run_a)]}), encoding="utf-8")
    rel_b.write_text(json.dumps({"runs": [str(run_b)]}), encoding="utf-8")

    out_path = tmp_path / "persona_gate_summary.json"
    rows_out = tmp_path / "persona_gate_rows.jsonl"
    script = Path(__file__).resolve().parents[1] / "scripts" / "check_persona_invariance_gate.py"
    result = _run_script(
        script,
        [
            "--inputs",
            f"novel_continuity={rel_a}",
            f"myopic_planning_traps={rel_b}",
            "--out",
            str(out_path),
            "--rows-out",
            str(rows_out),
        ],
    )
    assert result.returncode == 1
    summary = _read_json(out_path)
    assert summary["status"] == "FAIL"
    assert summary["overall"]["min_row_invariance_rate"] == 0.9


def test_check_persona_invariance_gate_passes_when_all_families_pass(tmp_path: Path) -> None:
    run_a = tmp_path / "runs" / "novel_run"
    run_b = tmp_path / "runs" / "myopic_run"
    _write_family_summary(run_a, "novel_continuity", 1.0)
    _write_family_summary(run_b, "myopic_planning_traps", 1.0)

    rel_a = tmp_path / "novel_reliability.json"
    rel_b = tmp_path / "myopic_reliability.json"
    rel_a.write_text(json.dumps({"runs": [str(run_a)]}), encoding="utf-8")
    rel_b.write_text(json.dumps({"runs": [str(run_b)]}), encoding="utf-8")

    out_path = tmp_path / "persona_gate_summary.json"
    rows_out = tmp_path / "persona_gate_rows.jsonl"
    script = Path(__file__).resolve().parents[1] / "scripts" / "check_persona_invariance_gate.py"
    result = _run_script(
        script,
        [
            "--inputs",
            f"novel_continuity={rel_a}",
            f"myopic_planning_traps={rel_b}",
            "--out",
            str(out_path),
            "--rows-out",
            str(rows_out),
        ],
    )
    assert result.returncode == 0, result.stderr
    summary = _read_json(out_path)
    assert summary["status"] == "PASS"
    assert summary["overall"]["min_row_invariance_rate"] == 1.0


@pytest.mark.skipif(os.name != "nt", reason="PowerShell runner integration is Windows-only")
def test_run_persona_invariance_trap_writes_artifacts(tmp_path: Path) -> None:
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

    out_root = tmp_path / "persona_runner_pass"
    canonical_data = out_root / "canonical_data.jsonl"
    canonical_preds = out_root / "canonical_preds.jsonl"
    summary_out = out_root / "persona_invariance_summary.json"
    rows_out = out_root / "persona_invariance_rows.jsonl"
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

    script = Path(__file__).resolve().parents[1] / "scripts" / "run_persona_invariance_trap.ps1"
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
def test_run_persona_invariance_trap_hard_fail_on_mismatch(tmp_path: Path) -> None:
    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "novel_continuity"
        / "novel_continuity_holdout_real_public.jsonl"
    )
    fixture_rows = [json.loads(line) for line in fixture_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    base_row = fixture_rows[0]
    base_row_id = str(base_row["id"])

    out_root = tmp_path / "persona_runner_fail"
    canonical_data = out_root / "canonical_data.jsonl"
    canonical_preds = out_root / "canonical_preds.jsonl"
    summary_out = out_root / "persona_invariance_summary.json"
    rows_out = out_root / "persona_invariance_rows.jsonl"
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

    script = Path(__file__).resolve().parents[1] / "scripts" / "run_persona_invariance_trap.ps1"
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
