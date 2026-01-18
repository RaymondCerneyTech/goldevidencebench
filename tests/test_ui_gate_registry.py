import json
from pathlib import Path

from goldevidencebench.ui_gate_registry import load_gate_model_map, match_gate_model


def _write_model(path: Path) -> None:
    payload = {
        "feature_names": ["bias"],
        "weights": [0.0],
        "bias": 0.0,
        "min_score": 0.5,
        "min_margin": 0.0,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_gate_model_map_prefers_longer_match(tmp_path: Path) -> None:
    model_a = tmp_path / "apply.json"
    model_b = tmp_path / "confirm_then_apply.json"
    _write_model(model_a)
    _write_model(model_b)
    map_path = tmp_path / "gate_map.json"
    map_path.write_text(
        json.dumps(
            {
                "apply": str(model_a),
                "confirm then apply": str(model_b),
            }
        ),
        encoding="utf-8",
    )

    entries = load_gate_model_map(map_path)
    row = {"instruction": "Confirm then apply changes."}
    candidates = [{"candidate_id": "btn_apply", "label": "Apply"}]
    entry = match_gate_model(row, candidates, entries)
    assert entry is not None
    assert entry.pattern == "confirm then apply"
