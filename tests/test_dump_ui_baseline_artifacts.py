import json
import subprocess
import sys
from pathlib import Path


def test_dump_ui_baseline_artifacts_writes_outputs(tmp_path: Path) -> None:
    fixture_path = tmp_path / "fixture.jsonl"
    row = {
        "id": "step_0001",
        "instruction": "Click Confirm.",
        "candidates": [
            {
                "candidate_id": "btn_confirm",
                "action_type": "click",
                "label": "Confirm",
                "role": "button",
                "app_path": "Test",
                "bbox": [0, 0, 10, 10],
                "visible": True,
                "enabled": True,
                "modal_scope": None,
            }
        ],
        "gold": {"candidate_id": "btn_confirm"},
    }
    fixture_path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    baseline_path = tmp_path / "baseline.json"
    baseline = {
        "seed_runs": [
            {
                "sa_diff": {
                    "row_id": "step_0001",
                    "decoy_reasons": ["label_mismatch"],
                }
            }
        ]
    }
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

    out_dir = tmp_path / "artifacts"
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "dump_ui_baseline_artifacts.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--fixture",
            str(fixture_path),
            "--baseline",
            str(baseline_path),
            "--out-dir",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (out_dir / "policy_traces.jsonl").exists()
    assert (out_dir / "sa_diffs.json").exists()
    assert (out_dir / "meta.json").exists()
