# Trap Families Backlog

This list tracks implemented trap families and a backlog of untried ones.
See `docs/TRAP_PLAN.md` for the rationale, scope, and lifecycle.
Use `.\scripts\next_trap_family.ps1` to pick the next backlog item to implement.

## Implemented

- local_optimum_base
- local_optimum_role_mismatch
- local_optimum_blocking_modal
- local_optimum_blocking_modal_detour
- local_optimum_blocking_modal_unmentioned
- local_optimum_blocking_modal_unmentioned_blocked
- local_optimum_blocking_modal_required
- local_optimum_blocking_modal_permission
- local_optimum_blocking_modal_consent
- local_optimum_blocking_modal_unprompted_confirm
- local_optimum_destructive_confirm
- local_optimum_unsaved_changes
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
- local_optimum_disabled_primary
- local_optimum_toolbar_vs_menu
- local_optimum_confirm_then_apply
- local_optimum_tab_state_reset
- local_optimum_stale_tab_state
- local_optimum_context_switch
- local_optimum_form_validation
- local_optimum_window_focus

Ambiguity-only companions (abstain_expected):

- local_optimum_delayed_ambiguous
- local_optimum_blocking_modal_unmentioned_ambiguous
- local_optimum_blocking_modal_unmentioned_blocked_ambiguous
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
- local_optimum_disabled_primary_ambiguous
- local_optimum_toolbar_vs_menu_ambiguous
- local_optimum_confirm_then_apply_ambiguous
- local_optimum_tab_state_reset_ambiguous
- local_optimum_stale_tab_state_ambiguous
- local_optimum_context_switch_ambiguous
- local_optimum_form_validation_ambiguous
- local_optimum_window_focus_ambiguous

## Backlog (untried)

Format: checkbox + id + short spec.

- [x] compression_loss_bounded: loss-bounded summaries of long ledgers (score precision/recall + bloat). Scaffolded via `scripts/generate_compression_loss_bounded_family.py` + `scripts/score_compression_loss_bounded.py`, fixtures under `data/compression_loss_bounded/`. Canary now uses a multi-row stress profile (`expected_fail=true`) and should be tracked as a sensitivity signal.
- [x] compression_recoverability: extraction questions from compressed snapshots (score value/exact/entailment/cite_f1). Scaffolded via `scripts/generate_compression_recoverability_family.py` + `scripts/score_compression_recoverability.py`, fixtures under `data/compression_recoverability/`. Canary is multi-row stress (tail-key lookup + large snapshots + mixed null/non-null targets, `expected_fail=true`).
- [x] novel_continuity: narrative state continuity (identity, timeline, constraints) across chapters. Scaffolded via `scripts/generate_novel_continuity_family.py` + `scripts/score_novel_continuity.py`, wrapper `scripts/run_novel_continuity_family.ps1`, and multi-run checker `scripts/check_novel_continuity_reliability.py`. Canary uses retcon-chain stress (`expected_fail=true`).
- [x] authority_under_interference: latest-authoritative selection under stale/NOTE/noisy evidence. Scaffolded via `scripts/generate_authority_under_interference_family.py` + `scripts/score_authority_under_interference.py`, wrapper `scripts/run_authority_under_interference_family.ps1`, and multi-run checker `scripts/check_authority_under_interference_reliability.py`.

## Next category sets (planned expansions)

These are the next high-leverage sets in execution order.

- [x] novel_continuity_long_horizon: extend continuity with longer callback gaps, delayed dependencies, contradiction pressure, and explicit repair transitions. Scaffolded via `scripts/generate_novel_continuity_long_horizon_family.py` + `scripts/score_novel_continuity_long_horizon.py`, wrapper `scripts/run_novel_continuity_long_horizon_family.ps1`, and multi-run checker `scripts/check_novel_continuity_long_horizon_reliability.py`.
- [x] compression_roundtrip_generalization: expand compaction + recoverability with query-type coverage, tail-key recall, null/non-null calibration, and larger snapshots. Scaffolded via `scripts/generate_compression_roundtrip_generalization_family.py` + `scripts/score_compression_roundtrip_generalization.py`, wrapper `scripts/run_compression_roundtrip_generalization_family.ps1`, and multi-run checker `scripts/check_compression_roundtrip_generalization_reliability.py`.
- [x] authority_under_interference_hardening: extend authority interference with harder decoys, deeper stale chains, and abstain-on-ambiguity variants. Scaffolded via `scripts/generate_authority_under_interference_hardening_family.py` + `scripts/score_authority_under_interference_hardening.py`, wrapper `scripts/run_authority_under_interference_hardening_family.ps1`, and multi-run checker `scripts/check_authority_under_interference_hardening_reliability.py`.
- [x] myopic_planning_traps: deterministic long-horizon decision traps measuring trap-entry rate, first-error step, recovery rate, and horizon success. Scaffolded via `scripts/generate_myopic_planning_traps_family.py` + `scripts/score_myopic_planning_traps.py`, wrapper `scripts/run_myopic_planning_traps_family.ps1`, and multi-run checker `scripts/check_myopic_planning_traps_reliability.py`.
- [x] referential_indexing_suite: orthogonal indexing/reassembly subfamilies (`index_loss_bounded`, `reassembly_recoverability`, `minimal_pointer_set`, `reconstruction_fidelity`, `no_invention_expansion`, `stale_pointer_conflict`, `wrong_hub_attraction`, `assembly_order_traps`, `wrong_address_traps`). Scaffolded via `scripts/generate_referential_indexing_suite_family.py` + `scripts/score_referential_indexing_suite.py`, wrapper `scripts/run_referential_indexing_suite_family.ps1`, and multi-run checker `scripts/check_referential_indexing_suite_reliability.py`.
- [x] epistemic_calibration_suite: know-what-you-know subfamilies (`known_answerable`, `unknown_unanswerable`, `near_miss_familiar`, `contradictory_evidence`, `missing_key_dependency`, `confidence_inversion`). Scaffolded via `scripts/generate_epistemic_calibration_suite_family.py` + `scripts/score_epistemic_calibration_suite.py`, wrapper `scripts/run_epistemic_calibration_suite_family.ps1`, and multi-run checker `scripts/check_epistemic_calibration_suite_reliability.py`.

## Next control families (scaffolded)

- [x] rpa_mode_switch: wrong-mode detection (`reason` vs `plan` vs `act`) under horizon/uncertainty/reversibility pressure. Scaffolded via `scripts/generate_rpa_mode_switch_family.py` + `scripts/score_rpa_mode_switch.py`, wrapper `scripts/run_rpa_mode_switch_family.ps1`, and checker `scripts/check_rpa_mode_switch_reliability.py`.
- [x] intent_spec_layer: underspecified-request disambiguation with bounded clarification burden and downstream-error reduction. Scaffolded via `scripts/generate_intent_spec_family.py` + `scripts/score_intent_spec.py`, wrapper `scripts/run_intent_spec_family.ps1`, and checker `scripts/check_intent_spec_reliability.py`.
- [x] noise_escalation: long-chain noise accumulation with correction checkpoints and recovery-latency scoring. Scaffolded via `scripts/generate_noise_escalation_family.py` + `scripts/score_noise_escalation.py`, wrapper `scripts/run_noise_escalation_family.ps1`, and checker `scripts/check_noise_escalation_reliability.py`.
