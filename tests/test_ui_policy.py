from goldevidencebench.ui_policy import (
    allow_overlay_from_row,
    filter_overlay_candidates,
    preselect_candidates,
    tie_break_same_label_candidates,
)


def test_filter_overlay_candidates_drops_overlay() -> None:
    candidates = [
        {"candidate_id": "btn_base", "modal_scope": None},
        {"candidate_id": "btn_overlay", "modal_scope": "popup", "overlay": True},
    ]
    filtered = filter_overlay_candidates(candidates)
    assert [c["candidate_id"] for c in filtered] == ["btn_base"]


def test_filter_overlay_candidates_falls_back() -> None:
    candidates = [
        {"candidate_id": "btn_overlay", "modal_scope": "popup", "overlay": True},
    ]
    filtered = filter_overlay_candidates(candidates)
    assert filtered == candidates


def test_allow_overlay_from_row() -> None:
    assert allow_overlay_from_row({"allow_overlay": True}) is True
    assert allow_overlay_from_row({"meta": {"allow_overlay": True}}) is True
    assert allow_overlay_from_row({}) is False


def test_preselect_candidates_prefers_main_page() -> None:
    row = {"instruction": "Use the main page button, not the popup."}
    candidates = [
        {"candidate_id": "btn_main", "modal_scope": None},
        {"candidate_id": "btn_popup", "modal_scope": "popup", "overlay": True},
    ]
    filtered = preselect_candidates(
        row,
        candidates,
        apply_overlay_filter=False,
        apply_rules=True,
    )
    assert [c["candidate_id"] for c in filtered] == ["btn_main"]


def test_preselect_candidates_prefers_primary() -> None:
    row = {"instruction": "Click the primary Save button."}
    candidates = [
        {"candidate_id": "btn_save_secondary"},
        {"candidate_id": "btn_save_primary"},
    ]
    filtered = preselect_candidates(
        row,
        candidates,
        apply_overlay_filter=False,
        apply_rules=True,
    )
    assert [c["candidate_id"] for c in filtered] == ["btn_save_primary"]


def test_preselect_candidates_prefers_bottom() -> None:
    row = {"instruction": "Choose the bottom Next button."}
    candidates = [
        {"candidate_id": "btn_next_top", "bbox": [820, 220, 90, 28]},
        {"candidate_id": "btn_next_bottom", "bbox": [820, 620, 90, 28]},
    ]
    filtered = preselect_candidates(
        row,
        candidates,
        apply_overlay_filter=False,
        apply_rules=True,
    )
    assert [c["candidate_id"] for c in filtered] == ["btn_next_bottom"]


def test_preselect_candidates_prefers_overlay_when_requested() -> None:
    row = {"instruction": "Click the popup Continue button."}
    candidates = [
        {"candidate_id": "btn_continue_page", "modal_scope": None},
        {"candidate_id": "btn_continue_popup", "modal_scope": "popup", "overlay": True},
    ]
    filtered = preselect_candidates(
        row,
        candidates,
        apply_overlay_filter=True,
        apply_rules=True,
    )
    assert [c["candidate_id"] for c in filtered] == ["btn_continue_popup"]


def test_tie_break_same_label_candidates_bottom_right() -> None:
    candidates = [
        {
            "candidate_id": "btn_next_top",
            "label": "Next",
            "bbox": [820, 220, 90, 28],
        },
        {
            "candidate_id": "btn_next_bottom",
            "label": "Next",
            "bbox": [820, 620, 90, 28],
        },
        {
            "candidate_id": "btn_save",
            "label": "Save",
            "bbox": [120, 240, 80, 28],
        },
    ]
    filtered = tie_break_same_label_candidates(candidates)
    assert [c["candidate_id"] for c in filtered] == ["btn_next_bottom", "btn_save"]


def test_preselect_candidates_applies_tie_breaker_by_default() -> None:
    row = {}
    candidates = [
        {
            "candidate_id": "btn_next_top",
            "label": "Next",
            "bbox": [820, 220, 90, 28],
        },
        {
            "candidate_id": "btn_next_bottom",
            "label": "Next",
            "bbox": [820, 620, 90, 28],
        },
    ]
    filtered = preselect_candidates(
        row,
        candidates,
        apply_overlay_filter=False,
        apply_rules=False,
    )
    assert [c["candidate_id"] for c in filtered] == ["btn_next_bottom"]
