from pathlib import Path
import json

from goldevidencebench.ui_fixture import validate_ui_fixture_path, validate_ui_rows


def test_ui_fixture_passes() -> None:
    fixture_path = Path("data/ui_same_label_fixture.jsonl")
    errors = validate_ui_fixture_path(fixture_path)
    assert errors == []


def test_ui_fixture_missing_candidate_id() -> None:
    rows = [
        {
            "id": "step_0001",
            "candidates": [
                {
                    "candidate_id": "",
                    "action_type": "click",
                    "label": "Next",
                    "role": "button",
                    "app_path": "Checkout > Cart",
                    "bbox": [0, 0, 10, 10],
                    "visible": True,
                    "enabled": True,
                    "modal_scope": None,
                }
            ],
            "gold": {"candidate_id": "btn_next"},
            "expected_delta": {"page": "checkout_shipping"},
        }
    ]
    errors = validate_ui_rows(rows)
    assert any("candidate_id must be a non-empty string" in error for error in errors)


def test_ui_fixture_invalid_task_fields() -> None:
    rows = [
        {
            "id": "step_0001",
            "task_id": " ",
            "step_index": 0,
            "candidates": [
                {
                    "candidate_id": "btn_next",
                    "action_type": "click",
                    "label": "Next",
                    "role": "button",
                    "app_path": "Checkout > Cart",
                    "bbox": [0, 0, 10, 10],
                    "visible": True,
                    "enabled": True,
                    "modal_scope": None,
                }
            ],
            "gold": {"candidate_id": "btn_next"},
            "expected_delta": {"page": "checkout_shipping"},
        }
    ]
    errors = validate_ui_rows(rows)
    assert any("task_id" in error for error in errors)
    assert any("step_index" in error for error in errors)


def test_ui_fixture_invalid_min_steps() -> None:
    rows = [
        {
            "id": "step_0001",
            "min_steps": 0,
            "candidates": [
                {
                    "candidate_id": "btn_next",
                    "action_type": "click",
                    "label": "Next",
                    "role": "button",
                    "app_path": "Checkout > Cart",
                    "bbox": [0, 0, 10, 10],
                    "visible": True,
                    "enabled": True,
                    "modal_scope": None,
                }
            ],
            "gold": {"candidate_id": "btn_next"},
            "expected_delta": {"page": "checkout_shipping"},
        }
    ]
    errors = validate_ui_rows(rows)
    assert any("min_steps" in error for error in errors)


def test_ui_fixture_bom_is_accepted(tmp_path: Path) -> None:
    row = {
        "id": "step_0001",
        "candidates": [
            {
                "candidate_id": "btn_next",
                "action_type": "click",
                "label": "Next",
                "role": "button",
                "app_path": "Checkout > Cart",
                "bbox": [0, 0, 10, 10],
                "visible": True,
                "enabled": True,
                "modal_scope": None,
            }
        ],
        "gold": {"candidate_id": "btn_next"},
        "expected_delta": {"page": "checkout_shipping"},
    }
    fixture_path = tmp_path / "fixture.jsonl"
    payload = b"\xef\xbb\xbf" + (json.dumps(row) + "\n").encode("utf-8")
    fixture_path.write_bytes(payload)
    errors = validate_ui_fixture_path(fixture_path)
    assert errors == []
