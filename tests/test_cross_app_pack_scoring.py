from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _row(
    *,
    row_id: str,
    tags: list[str],
    critical: bool,
    value: str,
    support_id: str,
    reversibility: str = "reversible",
) -> dict:
    return {
        "id": row_id,
        "gold": {"value": value, "support_ids": [support_id]},
        "meta": {
            "metric_tags": tags,
            "critical": critical,
            "workflow_id": "W1",
            "split": "holdout",
            "reversibility": reversibility,
        },
    }


def _run_score(data: Path, pred: Path, out_summary: Path, out_rows: Path) -> subprocess.CompletedProcess[str]:
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "score_cross_app_intent_preservation_pack.py"
    )
    return subprocess.run(
        [
            sys.executable,
            str(script),
            "--data",
            str(data),
            "--pred",
            str(pred),
            "--stage",
            "target",
            "--out-summary",
            str(out_summary),
            "--out-rows",
            str(out_rows),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cross_app_pack_scoring_critical_invariants_pass(tmp_path: Path) -> None:
    data = tmp_path / "data.jsonl"
    rows = [
        _row(row_id="r1", tags=["unauthorized_substitution"], critical=True, value="a", support_id="U1"),
        _row(row_id="r2", tags=["implication_break"], critical=True, value="b", support_id="U2"),
        _row(row_id="r3", tags=["agency_loss_error"], critical=True, value="c", support_id="U3"),
        _row(row_id="r4", tags=["support_coverage"], critical=True, value="d", support_id="U4"),
        _row(
            row_id="r5",
            tags=["verify_before_irreversible"],
            critical=True,
            value="verify",
            support_id="U5",
            reversibility="irreversible",
        ),
        _row(row_id="r6", tags=["noncritical_clarity"], critical=False, value="x", support_id="U6"),
        _row(row_id="r7", tags=["noncritical_efficiency"], critical=False, value="y", support_id="U7"),
        _row(row_id="r8", tags=["noncritical_robustness"], critical=False, value="z", support_id="U8"),
    ]
    preds = [{"id": row["id"], "value": row["gold"]["value"], "support_ids": row["gold"]["support_ids"]} for row in rows]
    pred_path = tmp_path / "pred.jsonl"
    out_summary = tmp_path / "summary.json"
    out_rows = tmp_path / "rows.jsonl"
    _write_jsonl(data, rows)
    _write_jsonl(pred_path, preds)

    result = _run_score(data, pred_path, out_summary, out_rows)
    assert result.returncode == 0, result.stderr
    summary = json.loads(out_summary.read_text(encoding="utf-8"))
    assert summary["status"] == "PASS"
    means = summary["means"]
    assert means["unauthorized_substitution_rate"] == 0.0
    assert means["implication_break_rate"] == 0.0
    assert means["agency_loss_error_rate"] == 0.0
    assert means["support_coverage_rate"] == 1.0
    assert means["verify_before_irreversible_rate"] == 1.0
    assert means["critical_invariant_pass_rate"] == 1.0
    assert means["composite_noncritical_score"] >= 0.95


def test_cross_app_pack_scoring_value_change_fails_target(tmp_path: Path) -> None:
    data = tmp_path / "data.jsonl"
    rows = [
        _row(row_id="r1", tags=["unauthorized_substitution"], critical=True, value="a", support_id="U1"),
        _row(row_id="r2", tags=["implication_break"], critical=True, value="b", support_id="U2"),
        _row(row_id="r3", tags=["agency_loss_error"], critical=True, value="c", support_id="U3"),
        _row(row_id="r4", tags=["support_coverage"], critical=True, value="d", support_id="U4"),
        _row(
            row_id="r5",
            tags=["verify_before_irreversible"],
            critical=True,
            value="verify",
            support_id="U5",
            reversibility="irreversible",
        ),
        _row(row_id="r6", tags=["noncritical_clarity"], critical=False, value="x", support_id="U6"),
        _row(row_id="r7", tags=["noncritical_efficiency"], critical=False, value="y", support_id="U7"),
        _row(row_id="r8", tags=["noncritical_robustness"], critical=False, value="z", support_id="U8"),
    ]
    preds = [{"id": row["id"], "value": row["gold"]["value"], "support_ids": row["gold"]["support_ids"]} for row in rows]
    preds[0]["value"] = "wrong"
    pred_path = tmp_path / "pred.jsonl"
    out_summary = tmp_path / "summary.json"
    out_rows = tmp_path / "rows.jsonl"
    _write_jsonl(data, rows)
    _write_jsonl(pred_path, preds)

    result = _run_score(data, pred_path, out_summary, out_rows)
    assert result.returncode == 1
    summary = json.loads(out_summary.read_text(encoding="utf-8"))
    assert summary["status"] == "FAIL"
    assert "unauthorized_substitution_rate != 0.0" in summary["failures"]
