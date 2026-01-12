import json
import subprocess
import sys
from pathlib import Path


def test_debug_ui_policy_trace_writes_output(tmp_path: Path) -> None:
    fixture_path = tmp_path / "fixture.jsonl"
    row = {
        "id": "step_0001",
        "instruction": "Click Next",
        "candidates": [
            {
                "candidate_id": "btn_next",
                "action_type": "click",
                "label": "Next",
                "role": "button",
                "app_path": "Test",
                "bbox": [0, 0, 10, 10],
                "visible": True,
                "enabled": True,
                "modal_scope": None,
            }
        ],
    }
    fixture_path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    out_path = tmp_path / "trace.json"

    script_path = Path(__file__).resolve().parents[1] / "scripts" / "debug_ui_policy_trace.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--fixture",
            str(fixture_path),
            "--row-id",
            "step_0001",
            "--out",
            str(out_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["row_id"] == "step_0001"
    assert payload["candidates_in"] == ["btn_next"]
