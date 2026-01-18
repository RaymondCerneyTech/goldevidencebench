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


def test_preselect_candidates_prefers_main_when_overlay_allowed() -> None:
    row = {"instruction": "Click Continue.", "allow_overlay": True}
    candidates = [
        {"candidate_id": "btn_main", "modal_scope": None},
        {"candidate_id": "btn_popup", "modal_scope": "popup", "overlay": True},
    ]
    filtered = preselect_candidates(
        row,
        candidates,
        apply_overlay_filter=True,
        apply_rules=True,
    )
    assert [c["candidate_id"] for c in filtered] == ["btn_main"]


def test_preselect_candidates_falls_back_to_overlay_when_only_overlay() -> None:
    row = {"instruction": "Click Continue.", "allow_overlay": True}
    candidates = [
        {"candidate_id": "btn_popup", "modal_scope": "popup", "overlay": True},
    ]
    filtered = preselect_candidates(
        row,
        candidates,
        apply_overlay_filter=True,
        apply_rules=True,
    )
    assert [c["candidate_id"] for c in filtered] == ["btn_popup"]


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


def test_preselect_candidates_prefers_primary_rich_label() -> None:
    row = {"instruction": "Choose the primary action to continue."}
    candidates = [
        {"candidate_id": "btn_primary_main", "label": "Primary main"},
        {"candidate_id": "btn_primary_side", "label": "Primary side"},
    ]
    filtered = preselect_candidates(
        row,
        candidates,
        apply_overlay_filter=False,
        apply_rules=True,
    )
    assert [c["candidate_id"] for c in filtered] == ["btn_primary_side"]


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


def test_preselect_candidates_prefers_overlay_confirmation_when_allowed() -> None:
    row = {"instruction": "Click the control.", "allow_overlay": True}
    candidates = [
        {"candidate_id": "btn_main", "label": "Proceed", "modal_scope": None},
        {
            "candidate_id": "btn_modal",
            "label": "Confirm",
            "overlay": True,
            "overlay_present": True,
            "modal_scope": None,
        },
    ]
    filtered = preselect_candidates(
        row,
        candidates,
        apply_overlay_filter=True,
        apply_rules=True,
    )
    assert [c["candidate_id"] for c in filtered] == ["btn_modal"]


def test_preselect_candidates_prefers_overlay_when_modal_clears() -> None:
    row = {"instruction": "Select the option.", "allow_overlay": True}
    candidates = [
        {"candidate_id": "btn_main", "label": "Continue", "modal_scope": None},
        {
            "candidate_id": "btn_dismiss",
            "label": "Dismiss",
            "overlay": True,
            "overlay_present": True,
            "modal_scope": None,
            "next_state": {"modal_cleared": True},
        },
    ]
    filtered = preselect_candidates(
        row,
        candidates,
        apply_overlay_filter=True,
        apply_rules=True,
    )
    assert [c["candidate_id"] for c in filtered] == ["btn_dismiss"]


def test_preselect_candidates_prefers_overlay_when_opens_modal() -> None:
    row = {"instruction": "Select the option.", "allow_overlay": True}
    candidates = [
        {"candidate_id": "btn_main", "label": "Continue", "modal_scope": None},
        {
            "candidate_id": "btn_modal_open",
            "label": "Advanced settings",
            "overlay": True,
            "overlay_present": True,
            "modal_scope": None,
            "next_state": {"modal_scope": "overlay", "overlay_present": True},
        },
    ]
    filtered = preselect_candidates(
        row,
        candidates,
        apply_overlay_filter=True,
        apply_rules=True,
    )
    assert [c["candidate_id"] for c in filtered] == ["btn_modal_open"]


def test_preselect_candidates_prefers_save_as_for_destination() -> None:
    row = {"instruction": "Save the file to Desktop."}
    candidates = [
        {
            "candidate_id": "file_save",
            "label": "Save",
            "next_state": {"save_dialog_open": False},
        },
        {
            "candidate_id": "file_save_as",
            "label": "Save As",
            "next_state": {"save_dialog_open": True},
        },
    ]
    filtered = preselect_candidates(
        row,
        candidates,
        apply_overlay_filter=False,
        apply_rules=True,
    )
    assert [c["candidate_id"] for c in filtered] == ["file_save_as"]


def test_preselect_candidates_prefers_required_modal_openers() -> None:
    row = {"instruction": "Select the option.", "allow_overlay": True}
    candidates = [
        {
            "candidate_id": "btn_main",
            "label": "Continue",
            "next_state": {"modal_required": False},
        },
        {
            "candidate_id": "btn_modal",
            "label": "Allow access",
            "next_state": {"modal_required": True},
        },
    ]
    filtered = preselect_candidates(
        row,
        candidates,
        apply_overlay_filter=False,
        apply_rules=True,
    )
    assert [c["candidate_id"] for c in filtered] == ["btn_modal"]


def test_preselect_candidates_prefers_overlay_when_advances_state() -> None:
    row = {"instruction": "Move to Settings.", "allow_overlay": True}
    candidates = [
        {"candidate_id": "btn_main", "label": "Continue", "modal_scope": None},
        {
            "candidate_id": "btn_overlay",
            "label": "Allow access",
            "overlay": True,
            "overlay_present": True,
            "modal_scope": None,
            "next_state": {"permission_granted": True},
        },
    ]
    filtered = preselect_candidates(
        row,
        candidates,
        apply_overlay_filter=True,
        apply_rules=True,
    )
    assert [c["candidate_id"] for c in filtered] == ["btn_overlay"]


def test_preselect_candidates_prefers_state_advances_without_label_hint() -> None:
    row = {"instruction": "Continue setup."}
    candidates = [
        {
            "candidate_id": "btn_continue",
            "label": "Continue",
            "modal_scope": None,
            "next_state": {"consent_granted": False},
        },
        {
            "candidate_id": "chk_consent",
            "label": "Continue with consent",
            "modal_scope": None,
            "next_state": {"consent_granted": True},
        },
    ]
    filtered = preselect_candidates(
        row,
        candidates,
        apply_overlay_filter=False,
        apply_rules=True,
    )
    assert [c["candidate_id"] for c in filtered] == ["chk_consent"]


def test_preselect_candidates_prefers_state_signal_when_generic_instruction() -> None:
    row = {"instruction": "Select the option."}
    candidates = [
        {
            "candidate_id": "btn_basic",
            "label": "Open details",
            "modal_scope": "main",
            "next_state": {"panel": "main", "modal_scope": "main", "overlay_present": False},
        },
        {
            "candidate_id": "btn_details",
            "label": "Details link",
            "modal_scope": "main",
            "next_state": {
                "panel": "details",
                "modal_scope": "main",
                "overlay_present": True,
                "details_open": True,
            },
        },
    ]
    filtered = preselect_candidates(
        row,
        candidates,
        apply_overlay_filter=False,
        apply_rules=True,
    )
    assert [c["candidate_id"] for c in filtered] == ["btn_details"]


def test_preselect_candidates_does_not_treat_desktop_as_top() -> None:
    row = {"instruction": "Save the file to Desktop."}
    candidates = [
        {"candidate_id": "opt_top", "label": "Alpha", "bbox": [0, 10, 10, 10]},
        {"candidate_id": "opt_bottom", "label": "Beta", "bbox": [0, 100, 10, 10]},
    ]
    filtered = preselect_candidates(
        row,
        candidates,
        apply_overlay_filter=False,
        apply_rules=True,
    )
    assert {c["candidate_id"] for c in filtered} == {"opt_top", "opt_bottom"}


def test_preselect_candidates_prefers_role_keyword() -> None:
    row = {"instruction": "Click the Start button."}
    candidates = [
        {"candidate_id": "btn_start_link", "label": "Start link", "role": "link"},
        {"candidate_id": "btn_start_button", "label": "Start button", "role": "button"},
    ]
    filtered = preselect_candidates(
        row,
        candidates,
        apply_overlay_filter=False,
        apply_rules=True,
    )
    assert [c["candidate_id"] for c in filtered] == ["btn_start_button"]


def test_tie_break_same_label_candidates_geometry() -> None:
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
    assert [c["candidate_id"] for c in filtered] == ["btn_next_top", "btn_save"]


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
    assert [c["candidate_id"] for c in filtered] == ["btn_next_top"]


def test_preselect_candidates_prefers_enabled_visible() -> None:
    row = {"instruction": "Click the Save button."}
    candidates = [
        {"candidate_id": "btn_save_disabled", "enabled": False},
        {"candidate_id": "btn_save_enabled", "enabled": True},
    ]
    filtered = preselect_candidates(
        row,
        candidates,
        apply_overlay_filter=False,
        apply_rules=True,
    )
    assert [c["candidate_id"] for c in filtered] == ["btn_save_enabled"]


def test_preselect_candidates_prefers_label_token() -> None:
    row = {"instruction": "Disable location sharing."}
    candidates = [
        {"candidate_id": "toggle_location", "label": "Location sharing"},
        {"candidate_id": "toggle_email", "label": "Email sharing"},
    ]
    filtered = preselect_candidates(
        row,
        candidates,
        apply_overlay_filter=False,
        apply_rules=True,
    )
    assert [c["candidate_id"] for c in filtered] == ["toggle_location"]


def test_preselect_candidates_prefers_label_keyword() -> None:
    row = {"instruction": "Click the Confirm button."}
    candidates = [
        {"candidate_id": "btn_confirm", "label": "Confirm"},
        {"candidate_id": "btn_cancel", "label": "Cancel"},
    ]
    filtered = preselect_candidates(
        row,
        candidates,
        apply_overlay_filter=False,
        apply_rules=True,
    )
    assert [c["candidate_id"] for c in filtered] == ["btn_confirm"]


def test_preselect_candidates_prefers_label_keyword_prefix() -> None:
    row = {"instruction": "Confirm the action."}
    candidates = [
        {"candidate_id": "btn_confirm", "label": "Confirmation"},
        {"candidate_id": "btn_cancel", "label": "Cancel"},
    ]
    filtered = preselect_candidates(
        row,
        candidates,
        apply_overlay_filter=False,
        apply_rules=True,
    )
    assert [c["candidate_id"] for c in filtered] == ["btn_confirm"]


def test_preselect_candidates_prefers_label_keyword_synonym() -> None:
    row = {"instruction": "Click OK to finish."}
    candidates = [
        {"candidate_id": "btn_confirm", "label": "Confirm"},
        {"candidate_id": "btn_cancel", "label": "Cancel"},
    ]
    filtered = preselect_candidates(
        row,
        candidates,
        apply_overlay_filter=False,
        apply_rules=True,
    )
    assert [c["candidate_id"] for c in filtered] == ["btn_confirm"]


def test_preselect_candidates_prefers_label_keyword_synonym_commit() -> None:
    row = {"instruction": "Commit the changes."}
    candidates = [
        {"candidate_id": "btn_apply", "label": "Apply"},
        {"candidate_id": "btn_ok", "label": "OK"},
    ]
    filtered = preselect_candidates(
        row,
        candidates,
        apply_overlay_filter=False,
        apply_rules=True,
    )
    assert [c["candidate_id"] for c in filtered] == ["btn_apply"]


def test_preselect_candidates_prefers_label_keyword_synonym_finalize() -> None:
    row = {"instruction": "Finalize the update."}
    candidates = [
        {"candidate_id": "btn_apply", "label": "Apply"},
        {"candidate_id": "btn_cancel", "label": "Cancel"},
    ]
    filtered = preselect_candidates(
        row,
        candidates,
        apply_overlay_filter=False,
        apply_rules=True,
    )
    assert [c["candidate_id"] for c in filtered] == ["btn_apply"]


def test_preselect_candidates_prefers_app_path_keyword() -> None:
    row = {"instruction": "Open the Billing section."}
    candidates = [
        {
            "candidate_id": "btn_profile",
            "label": "Open profile",
            "app_path": "Settings > Profile",
        },
        {
            "candidate_id": "btn_billing",
            "label": "Open account",
            "app_path": "Settings > Billing",
        },
    ]
    filtered = preselect_candidates(
        row,
        candidates,
        apply_overlay_filter=False,
        apply_rules=True,
    )
    assert [c["candidate_id"] for c in filtered] == ["btn_billing"]


def test_preselect_candidates_abstains_on_ambiguous_duplicates() -> None:
    row = {"instruction": "Click Save."}
    candidates = [
        {"candidate_id": "btn_save_a", "label": "Save"},
        {"candidate_id": "btn_save_b", "label": "Save"},
    ]
    filtered = preselect_candidates(
        row,
        candidates,
        apply_overlay_filter=False,
        apply_rules=True,
    )
    assert filtered == []


def test_preselect_candidates_abstains_when_expected() -> None:
    row = {"instruction": "Click Save.", "abstain_expected": True}
    candidates = [
        {"candidate_id": "btn_save_a", "label": "Save"},
        {"candidate_id": "btn_save_b", "label": "Save"},
    ]
    filtered = preselect_candidates(
        row,
        candidates,
        apply_overlay_filter=False,
        apply_rules=True,
    )
    assert filtered == []


def test_preselect_candidates_prefers_accessible_name_keyword() -> None:
    row = {"instruction": "Select the reader option."}
    candidates = [
        {
            "candidate_id": "btn_access",
            "label": "Accessibility",
            "accessible_name": "Reader option",
            "modal_scope": "panel",
        },
        {
            "candidate_id": "btn_settings",
            "label": "Settings",
            "modal_scope": "main",
        },
    ]
    filtered = preselect_candidates(
        row,
        candidates,
        apply_overlay_filter=False,
        apply_rules=True,
    )
    assert [c["candidate_id"] for c in filtered] == ["btn_access"]


def test_preselect_candidates_skips_aria_disabled() -> None:
    row = {"instruction": "Select the option."}
    candidates = [
        {
            "candidate_id": "btn_primary",
            "label": "Continue",
            "modal_scope": "main",
            "aria_disabled": True,
            "enabled": True,
            "clickable": True,
        },
        {
            "candidate_id": "btn_secondary",
            "label": "Proceed",
            "modal_scope": "panel",
            "aria_disabled": False,
            "enabled": True,
            "clickable": True,
        },
    ]
    filtered = preselect_candidates(
        row,
        candidates,
        apply_overlay_filter=False,
        apply_rules=True,
    )
    assert [c["candidate_id"] for c in filtered] == ["btn_secondary"]
