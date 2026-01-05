from pathlib import Path

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
