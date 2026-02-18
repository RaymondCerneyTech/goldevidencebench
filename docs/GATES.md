# Gate Contracts (Source of Truth)

This page lists each gate or benchmark, where its thresholds live, and the artifact it produces.
Treat the linked config files as the source of truth for PASS/FAIL semantics.

Terminology note: "commit policy" (aka selector/reranker) is the chooser that picks which candidate commits to state. Script and env var names still use "selector".
Gates are constraint checks: they don't prevent optimization, they ensure optimization respects the contract.

## Core gates and benchmarks

| Gate / Benchmark | Command | Threshold / Fixture Config | Primary Artifact |
| --- | --- | --- | --- |
| Drift holdout gate | `.\scripts\run_drift_holdout_gate.ps1` | `configs/usecase_checks.json` (`drift_holdout_gate`: `canary_min`, `drift.step_rate` max) | `runs/release_gates/drift_holdout_gate.json` |
| Drift wall | `.\scripts\run_drift_wall.ps1` | `configs/usecase_checks.json` (`drift_gate`) | `runs/drift_wall_latest/summary.json` (safety wall); optional stress wall at `runs/drift_wall_latest_stress/summary.json` |
| Core benchmark | `.\scripts\run_core_benchmark.ps1` | `configs/core_benchmark.json` + `configs/core_thresholds.json` | `runs/<run_dir>/summary.json` |
| RAG benchmark (lenient/strict) | `.\scripts\run_rag_benchmark.ps1 -Preset lenient|strict` | `configs/rag_benchmark_lenient.json` / `configs/rag_benchmark_strict.json` + `configs/rag_thresholds.json` | `runs/<run_dir>/summary.json` |

## Release checks (gates)

| Gate | Command | Threshold / Fixture Config | Primary Artifact |
| --- | --- | --- | --- |
| Instruction override | `.\scripts\run_instruction_override_gate.ps1` | `configs/usecase_checks.json` (`instruction_override`) | `runs/release_gates/instruction_override_gate/summary.json` |
| Memory verify | `python .\scripts\verify_memories.py ...` | `configs/usecase_checks.json` (`memory_verify_gate`) | `runs/release_gates/memory_verify.json` |
| Persona invariance | `python .\scripts\check_persona_invariance_gate.py` (invoked by `.\scripts\run_release_check.ps1`) | `configs/usecase_checks.json` (`persona_invariance_gate`, `overall.min_row_invariance_rate >= 1.0`) | `runs/release_gates/persona_invariance/summary.json` |
| Cross-app intent-preservation pack | `.\scripts\run_cross_app_intent_preservation_pack.ps1` (collected by `.\scripts\run_release_check.ps1`) | `configs/usecase_checks.json` (`cross_app_intent_preservation_pack`) | `runs/release_gates/cross_app_intent_preservation_pack/summary.json` |
| Update burst release gate | `.\scripts\run_update_burst_full_linear_bucket10.ps1` (via release check) | `configs/usecase_checks.json` (`update_burst_release_gate`) | `runs/release_gates/update_burst_full_linear_k16_bucket5_rate0.12/summary.json` |
| Bad actor holdout gate | `.\scripts\run_bad_actor_holdout_gate.ps1` | `configs/bad_actor_holdout_list.json` + `configs/usecase_checks.json` (`bad_actor_holdout_gate`) | `runs/bad_actor_holdout_latest/summary.json` |
| UI same_label stub | `.\scripts\run_ui_same_label_stub.ps1` | `configs/usecase_checks.json` (`ui_same_label_gate`) | `runs/ui_same_label_gate.json` |
| UI popup_overlay stub | `.\scripts\run_ui_popup_overlay_stub.ps1` | `configs/usecase_checks.json` (`ui_popup_overlay_gate`) | `runs/ui_popup_overlay_gate.json` |
| Release reliability matrix | `.\scripts\run_release_reliability_matrix.ps1` (invoked by `.\scripts\run_release_check.ps1` in `release` profile) | `configs/release_gate_contract.json` (`strict_release.required_reliability_families`, freshness/status/canary policy) | `<release_run_dir>/release_reliability_matrix.json` (`runs/latest_release_reliability_matrix`) |
| Unified reliability signal | `.\scripts\check_reliability_signal.ps1` (invoked by `.\scripts\run_release_check.ps1`) | strict + family reliability summaries; default requires `rpa_mode_switch`, `intent_spec_layer`, `noise_escalation`, `implication_coherence`, `agency_preserving_substitution`, and enforces `derived.reasoning/planning/intelligence >= 0.98` plus implication/agency component floors | `runs/reliability_signal_latest.json` |
| Codex compatibility artifacts | `python .\scripts\build_codex_compat_report.py` (invoked by `.\scripts\run_release_check.ps1` after reliability PASS) | consistency across family scaffolds/docs + orthogonality export from latest reliability files | `runs/codex_compat/family_matrix.json`, `runs/codex_compat/orthogonality_matrix.json`, `runs/codex_compat/rpa_ablation_report.json` |
| Codex next-step report | `python .\scripts\build_codex_next_step_report.py` (invoked by `.\scripts\run_release_check.ps1` after reliability PASS) | control readiness snapshot from reliability + RPA control contract | `runs/codex_next_step_report.json` |
| Real-world utility eval (A/B) | producer resolved by `configs/release_gate_contract.json` (`strict_release.utility_gate`) | baseline vs controlled task-pack delta (`false_commit`, `correction_turns`, `clarification_burden`) when utility gate is required | contract-defined artifact path (default: `runs/real_world_utility_eval_latest.json`) |

Default release/nightly contract:

- `run_release_check.ps1` now requires `rpa_mode_switch`, `intent_spec_layer`,
  `noise_escalation`, `implication_coherence`, and
  `agency_preserving_substitution` by default in the unified reliability gate.
- `run_release_check.ps1` now also enforces default derived-score floors:
  `reasoning_score >= 0.98`, `planning_score >= 0.98`,
  `intelligence_index >= 0.98`, `implication_coherence_core >= 0.945`,
  `agency_preservation_core >= 0.92`.
- `run_release_check.ps1` now loads strict release requirements from
  `configs/release_gate_contract.json` and, in `release` profile, produces
  `<release_run_dir>/release_reliability_matrix.json` before unified reliability.
- Release canary policy is contract-driven: `strict_release.canary_policy` sets
  the default and individual `required_reliability_families[]` rows can
  override with `canary_policy` (`strict` or `triage`).
- If contract freshness is `allow_latest`, matrix production uses existing
  reliability artifacts (`-UseExistingArtifacts`) instead of regenerating.
- Utility gate ownership is now contract-defined in
  `strict_release.utility_gate` (required/deferred + producer + artifact path).
- `run_release_reliability_matrix.ps1` now supports `-FailOnMatrixFail` for
  independent CI jobs that require non-zero exit when matrix status is `FAIL`.
- `run_release_check.ps1` now hard-fails on persona contract drift using the
  consolidated persona invariance gate (`row_invariance_rate == 1.0`).
- `cross_app_intent_preservation_pack` is currently warn-only in release
  coupling (visible in threshold output and release integrity/risk warnings).
- On unified reliability PASS, `run_release_check.ps1` also rebuilds Codex
  compatibility outputs and updates `runs/latest_codex_compat_*` pointers.
- `run_release_overnight.ps1` inherits the same default behavior.
- Diagnostic-only overrides: `-SkipRequireControlFamilies`,
  `-SkipDerivedScoreFloors`, `-SkipRealWorldUtilityEval`.

Instruction override normalization contract:

- `run_instruction_override_gate.ps1` now emits `runs/release_gates/instruction_override_gate/sweep_status.json`.
- If sweep exits non-zero but all expected artifacts exist, outcome is normalized to `soft_fail_artifacts_complete` and the gate continues.
- Use `-FailOnSweepSoftFail` to escalate normalized soft-fail to hard fail.
- Use `-FailOnInstructionOverrideSoftFail` on release/nightly wrappers to enforce strict behavior without calling the gate directly.

Optional metric semantics:

- In `configs/usecase_checks.json`, optional checks should prefer explicit `allow_missing` + `skip_if`.
- Threshold evaluation now reports these as `N/A` (`status=not_applicable`) instead of implicit missing/skip ambiguity.

Bad actor holdout defaults: `prefer_update_latest` rerank + authority filter (set in `scripts/run_bad_actor_holdout_gate.ps1`).

Every gate run writes a compact, human-friendly summary (`summary_compact.json` / `summary_compact.csv`) alongside `summary.json`. Latest pointers live under `runs/latest_*` (e.g., `runs/latest_release`, `runs/latest_regression`, `runs/latest_rag_lenient`).

## Holdout suite inputs

- UI holdout rotation list: `configs/ui_holdout_list.json`
- Bad actor holdout subset list: `configs/bad_actor_holdout_list.json`
- Gate threshold checks: `configs/usecase_checks.json`

If you add a new fixture or holdout, update the config file first, then wire it into the scripts or benchmarks that consume it.
