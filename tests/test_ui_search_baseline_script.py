import json
import subprocess
import sys
from pathlib import Path


def test_ui_search_baseline_fuzz_summary(tmp_path: Path) -> None:
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
            },
            {
                "candidate_id": "btn_cancel",
                "action_type": "click",
                "label": "Cancel",
                "role": "button",
                "app_path": "Test",
                "bbox": [20, 0, 10, 10],
                "visible": True,
                "enabled": True,
                "modal_scope": None,
            },
        ],
        "gold": {"candidate_id": "btn_confirm"},
    }
    fixture_path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    out_path = tmp_path / "out.json"

    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_ui_search_baseline.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--fixture",
            str(fixture_path),
            "--out",
            str(out_path),
            "--seeds",
            "1",
            "--fuzz-variants",
            "2",
            "--fuzz-seed",
            "0",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    fuzz_summary = payload.get("fuzz_summary")
    assert isinstance(fuzz_summary, dict)
    assert fuzz_summary.get("variants") == 2
