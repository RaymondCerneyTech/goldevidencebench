# Trap Families Backlog

This list tracks implemented trap families and a backlog of untried ones.
Use `scripts/next_trap_family.ps1` to pick the next backlog item to implement.

## Implemented

- local_optimum_base
- local_optimum_role_mismatch
- local_optimum_blocking_modal
- local_optimum_blocking_modal_detour
- local_optimum_blocking_modal_unmentioned
- local_optimum_blocking_modal_required
- local_optimum_blocking_modal_permission
- local_optimum_blocking_modal_consent
- local_optimum_blocking_modal_unprompted_confirm
- local_optimum_destructive_confirm
- local_optimum_tab_detour
- local_optimum_panel_toggle
- local_optimum_accessibility_label
- local_optimum_checkbox_gate
- local_optimum_section_path
- local_optimum_section_path_conflict
- local_optimum_delayed_solvable
- local_optimum_overlay
- local_optimum_primary
- local_optimum_role_conflict

Ambiguity-only companions (abstain_expected):

- local_optimum_delayed_ambiguous
- local_optimum_blocking_modal_unmentioned_ambiguous
- local_optimum_blocking_modal_required_ambiguous
- local_optimum_blocking_modal_permission_ambiguous
- local_optimum_blocking_modal_consent_ambiguous
- local_optimum_blocking_modal_unprompted_confirm_ambiguous
- local_optimum_checkbox_gate_ambiguous
- local_optimum_panel_toggle_ambiguous
- local_optimum_section_path_ambiguous
- local_optimum_section_path_conflict_ambiguous
- local_optimum_destructive_confirm_ambiguous
- local_optimum_role_conflict_ambiguous
- local_optimum_accessibility_label_ambiguous

## Backlog (untried)

Format: checkbox + id + short spec.

- [ ] local_optimum_disabled_primary: primary label exists but is disabled; secondary is correct.
- [ ] local_optimum_toolbar_vs_menu: same label in toolbar and menu; instruction implies one path only.
- [ ] local_optimum_confirm_then_apply: "OK" only closes modal, "Apply" commits; correct is apply.
- [ ] local_optimum_tab_state_reset: wrong tab resets state; right tab preserves state for later step.
- [ ] local_optimum_form_validation: submit blocked until field is valid; correct action is fix field first.
