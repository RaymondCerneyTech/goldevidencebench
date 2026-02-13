<#
.SYNOPSIS
Runs GoldEvidenceBench release checks and gates.

.DESCRIPTION
Executes a suite of checks (retrieval, UI stubs, local-optimum variants), runs
the bad actor holdout gate, and optionally the drift holdout gate. The UI
local-optimum distillation holdout defaults to local_optimum_blocking_modal_unmentioned_blocked.

.PARAMETER VariantsHoldoutName
Holdout for UI local-optimum distillation (default:
local_optimum_blocking_modal_unmentioned_blocked).

.PARAMETER RunDriftHoldoutGate
Runs the drift holdout canary + fixes gate and fails the release on FAIL.

.PARAMETER SkipRequireControlFamilies
 Diagnostic-only override: do not require rpa_mode_switch, intent_spec_layer,
 noise_escalation, implication_coherence, and agency_preserving_substitution
 in the unified reliability gate.

.PARAMETER SkipDerivedScoreFloors
 Diagnostic-only override: do not enforce derived reasoning/planning/intelligence
 floors in the unified reliability gate.

.PARAMETER SkipRealWorldUtilityEval
 Diagnostic-only override: skip the baseline-vs-controlled utility A/B gate.

.PARAMETER MinReleaseImplicationCoherenceCore
Default floor for the implication-coherence reasoning component in the unified
reliability gate.

.PARAMETER MinReleaseAgencyPreservationCore
Default floor for the agency-preservation reasoning component in the unified
reliability gate.

.PARAMETER MaxReleaseUtilityBurdenDelta
Hard cap for controlled-vs-baseline clarification burden delta from
`runs\real_world_utility_eval_latest.json`.

.PARAMETER WarnReleaseUtilityBurdenDelta
Warning threshold for controlled-vs-baseline clarification burden delta from
`runs\real_world_utility_eval_latest.json`. Values above this threshold are
treated as high-risk even when they are still below the hard cap.

.PARAMETER MinUtilityWarningFalseCommitImprovement
If burden is in warning-zone but false-commit improvement is at/above this
floor, utility warning debt is not triggered.

.PARAMETER MinUtilityWarningCorrectionImprovement
If burden is in warning-zone but correction-turn improvement is at/above this
floor, utility warning debt is not triggered.

.PARAMETER MaxInstructionOverrideTokensPerQP90
Hard cap for instruction-override gate `efficiency.tokens_per_q_p90`.

.PARAMETER WarnInstructionOverrideTokensPerQP90
Warning threshold for instruction-override gate `efficiency.tokens_per_q_p90`.

.PARAMETER WarnInstructionOverrideTokensPerQMean
Warning threshold for instruction-override gate `efficiency.tokens_per_q_mean`.

.PARAMETER MaxInstructionOverrideWallPerQP90
Hard cap for instruction-override gate `efficiency.wall_s_per_q_p90`.

.PARAMETER WarnInstructionOverrideWallPerQP90
Warning threshold for instruction-override gate `efficiency.wall_s_per_q_p90`.

.PARAMETER WarnInstructionOverrideWallPerQMean
Warning threshold for instruction-override gate `efficiency.wall_s_per_q_mean`.

.PARAMETER MaxTrendInstructionOverrideTokensPerQP90Increase
Maximum allowed relative increase (vs baseline median) for instruction-override
`tokens_per_q_p90`.

.PARAMETER MaxTrendInstructionOverrideWallPerQP90Increase
Maximum allowed relative increase (vs baseline median) for instruction-override
`wall_s_per_q_p90`.

.PARAMETER MinMemorySensitivityScenarioCount
Minimum number of scenarios required in `runs\release_gates\memory_verify_sensitivity.json`.

.PARAMETER MinMemorySensitivityMaxInvalidRate
Minimum peak invalid-rate coverage required in `runs\release_gates\memory_verify_sensitivity.json`.

.PARAMETER MinMemorySensitivityMaxActionsBlocked
Minimum peak blocked-action coverage required in `runs\release_gates\memory_verify_sensitivity.json`.

.PARAMETER MinMemorySensitivityMaxTotal
Minimum largest-scenario memory_total required in `runs\release_gates\memory_verify_sensitivity.json`.

.PARAMETER MinMemorySensitivityDistinctTagCount
Minimum distinct memory-tag coverage required in sensitivity scenarios.

.PARAMETER MinMemorySensitivityDistinctReasonCount
Minimum distinct memory-reason coverage required in sensitivity scenarios.

.PARAMETER MinMemoryVerifyTotal
Minimum required `memory_total` for the primary memory verification gate payload.

.PARAMETER MemoryVerifyInputPath
Path to live memory JSONL used by the primary memory verification gate.

.PARAMETER MinMemoryVerifyUseRate
Minimum required `memory_use_rate` for the primary memory verification gate payload.

.PARAMETER MinMemoryVerifyVerifiedRate
Minimum required `memory_verified_rate` for the primary memory verification gate payload.

.PARAMETER MaxMemoryVerifyInvalidRate
Maximum allowed `memory_invalid_rate` for the primary memory verification gate payload.

.PARAMETER MaxMemoryVerifyActionsBlocked
Maximum allowed `actions_blocked_by_memory_gate` for the primary memory verification gate payload.

.PARAMETER MinRegressionFrontierCoverage
Minimum required-tag coverage rate for `runs\codex_compat\regression_frontier.json`.

.PARAMETER MinRegressionFrontierReduction
Minimum candidate-reduction rate for `runs\codex_compat\regression_frontier.json`.

.PARAMETER TrendReleaseWindow
Number of most recent release snapshots considered by trend guard.

.PARAMETER TrendMinHistory
Minimum number of release snapshots (including current release) required before
enforcing trend regression checks.

.PARAMETER TrendMaxSnapshotAgeDays
Maximum age (days) allowed for prior release snapshots to participate in trend
guard baselines.

.PARAMETER MaxTrendReasoningDrop
Maximum allowed drop from baseline-median for `derived.reasoning_score`.

.PARAMETER MaxTrendImplicationCoherenceDrop
Maximum allowed drop from baseline-median for `derived.implication_coherence_core`.

.PARAMETER MaxTrendAgencyPreservationDrop
Maximum allowed drop from baseline-median for `derived.agency_preservation_core`.

.PARAMETER WarningDebtWindow
Number of most recent release snapshots (including current) used to evaluate
warning-zone debt for near-cap cost/burden behavior.

.PARAMETER MaxInstructionOverrideCostWarningHits
Maximum allowed count of instruction-override cost warning-zone hits within
`WarningDebtWindow` before release hard-fails.

.PARAMETER MaxUtilityBurdenWarningHits
Maximum allowed count of utility-burden warning-zone hits within
`WarningDebtWindow` before release hard-fails.

.PARAMETER StrictOptionalThresholdMetrics
If enabled, optional missing threshold metrics are treated as missing failures once
the release history is out of bootstrap mode (`TrendMinHistory` satisfied).

.PARAMETER OptionalMetricExemptionsAllowlistPath
Allowlist for newly introduced optional-metric exemptions
(`required=false` and `strict_optional_missing=false`) in
`configs/usecase_checks.json`. New exemptions are blocked unless approved here
after bootstrap.

.PARAMETER FailOnInstructionOverrideSoftFail
 Escalate instruction override soft-fail normalization (non-zero sweep exit with
 complete artifacts) to a hard release failure.

.PARAMETER FastLocal
 Enables local iteration mode that reuses fresh heavyweight artifacts when
 available to reduce cycle time.

.PARAMETER ReuseInstructionOverrideMaxAgeMinutes
 Maximum artifact age (minutes) for reusing instruction-override gate outputs in
 FastLocal mode.

.PARAMETER ReuseUiBaselinesMaxAgeMinutes
 Maximum artifact age (minutes) for reusing UI baseline search outputs in
 FastLocal mode.

.PARAMETER ReuseUtilityEvalMaxAgeMinutes
 Maximum artifact age (minutes) for reusing real-world utility eval outputs in
 FastLocal mode.

.PARAMETER SkipWarningDebtGuard
 Skips warning-debt hard-fail enforcement for local iteration loops.

#>
param(
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL,
    [string]$GateAdapter = "goldevidencebench.adapters.retrieval_llama_cpp_adapter:create_adapter",
    [switch]$RunSweeps,
    [switch]$SkipThresholds,
    [switch]$SkipReliabilitySignal,
    [switch]$SkipRequireControlFamilies,
    [switch]$SkipDerivedScoreFloors,
    [switch]$SkipRealWorldUtilityEval,
    [double]$MinReleaseReasoningScore = 0.98,
    [double]$MinReleasePlanningScore = 0.98,
    [double]$MinReleaseIntelligenceIndex = 0.98,
    [double]$MinReleaseImplicationCoherenceCore = 0.945,
    [double]$MinReleaseAgencyPreservationCore = 0.92,
    [double]$MaxReleaseUtilityBurdenDelta = 0.50,
    [double]$WarnReleaseUtilityBurdenDelta = 0.50,
    [double]$MinUtilityWarningFalseCommitImprovement = 0.05,
    [double]$MinUtilityWarningCorrectionImprovement = 0.50,
    [double]$MaxInstructionOverrideTokensPerQP90 = 2400.0,
    [double]$WarnInstructionOverrideTokensPerQP90 = 2400.0,
    [double]$WarnInstructionOverrideTokensPerQMean = 2400.0,
    [double]$MaxInstructionOverrideWallPerQP90 = 4.00,
    [double]$WarnInstructionOverrideWallPerQP90 = 3.50,
    [double]$WarnInstructionOverrideWallPerQMean = 3.50,
    [double]$MaxTrendInstructionOverrideTokensPerQP90Increase = 0.15,
    [double]$MaxTrendInstructionOverrideWallPerQP90Increase = 0.20,
    [string]$MemoryVerifyInputPath = "data\\memories\\user_notes_memory.jsonl",
    [int]$MinMemoryVerifyTotal = 10,
    [double]$MinMemoryVerifyUseRate = 1.0,
    [double]$MinMemoryVerifyVerifiedRate = 1.0,
    [double]$MaxMemoryVerifyInvalidRate = 0.0,
    [int]$MaxMemoryVerifyActionsBlocked = 0,
    [int]$MinMemorySensitivityScenarioCount = 15,
    [double]$MinMemorySensitivityMaxInvalidRate = 1.00,
    [int]$MinMemorySensitivityMaxActionsBlocked = 60,
    [int]$MinMemorySensitivityMaxTotal = 100,
    [int]$MinMemorySensitivityDistinctTagCount = 5,
    [int]$MinMemorySensitivityDistinctReasonCount = 9,
    [double]$MinRegressionFrontierCoverage = 1.00,
    [double]$MinRegressionFrontierReduction = 0.93,
    [int]$TrendReleaseWindow = 8,
    [int]$TrendMinHistory = 3,
    [int]$TrendMaxSnapshotAgeDays = 14,
    [int]$WarningDebtWindow = 3,
    [int]$MaxInstructionOverrideCostWarningHits = 1,
    [int]$MaxUtilityBurdenWarningHits = 1,
    [double]$MaxTrendReasoningDrop = 0.01,
    [double]$MaxTrendImplicationCoherenceDrop = 0.01,
    [double]$MaxTrendAgencyPreservationDrop = 0.01,
    [bool]$StrictOptionalThresholdMetrics = $true,
    [string]$OptionalMetricExemptionsAllowlistPath = "configs\\optional_metric_exemptions_allowlist.json",
    [switch]$FailOnInstructionOverrideSoftFail,
    [switch]$FastLocal,
    [int]$ReuseInstructionOverrideMaxAgeMinutes = 240,
    [int]$ReuseUiBaselinesMaxAgeMinutes = 240,
    [int]$ReuseUtilityEvalMaxAgeMinutes = 240,
    [switch]$SkipWarningDebtGuard,
    [switch]$RunDriftHoldoutGate,
    [int]$VariantsSeeds = 10,
    [string]$VariantsHoldoutName = "local_optimum_blocking_modal_unmentioned_blocked",
    [int]$VariantsFuzzVariants = 5,
    [int]$VariantsFuzzSeed = 0,
    [switch]$RotateHoldout,
    [switch]$AutoCurriculum,
    [double]$AutoCurriculumGapMin = 0.1,
    [double]$AutoCurriculumSolvedMin = 0.9,
    [string]$AutoCurriculumStatePath = "runs\\release_gates\\ui_holdout_autocurriculum.json",
    [string]$HoldoutList = "",
    [string]$HoldoutListPath = "configs\\ui_holdout_list.json",
    [ValidateSet("stale_tab_state", "focus_drift")]
    [string]$DriftHoldoutName = "stale_tab_state",
    [string]$BadActorHoldoutId = "",
    [string]$BadActorHoldoutListPath = "configs\\bad_actor_holdout_list.json",
    [switch]$SkipVariants
)

$gateUsesServerAdapter = $GateAdapter -like "*llama_server_adapter*"
if ($ModelPath -eq "<MODEL_PATH>") {
    if ($PSBoundParameters.ContainsKey("ModelPath")) {
        Write-Error "Replace placeholder <MODEL_PATH> with a real path, or omit -ModelPath when using llama_server_adapter."
        exit 1
    }
    if ($gateUsesServerAdapter) {
        # Ignore placeholder inherited from environment for server-adapter runs.
        $ModelPath = ""
    } else {
        Write-Error "Replace placeholder <MODEL_PATH> with a real path, or set GOLDEVIDENCEBENCH_MODEL."
        exit 1
    }
}

$RequiredVariantsHoldout = "local_optimum_blocking_modal_unmentioned_blocked"
$DefaultHoldoutList = "local_optimum_section_path,local_optimum_section_path_conflict,local_optimum_blocking_modal_detour,local_optimum_tab_detour,local_optimum_disabled_primary,local_optimum_toolbar_vs_menu,local_optimum_confirm_then_apply,local_optimum_tab_state_reset,local_optimum_context_switch,local_optimum_stale_tab_state,local_optimum_form_validation,local_optimum_window_focus,local_optimum_panel_toggle,local_optimum_accessibility_label,local_optimum_checkbox_gate,local_optimum_blocking_modal_required,local_optimum_blocking_modal_permission,local_optimum_blocking_modal_consent,local_optimum_blocking_modal_unmentioned,local_optimum_blocking_modal_unmentioned_blocked,local_optimum_blocking_modal,local_optimum_overlay,local_optimum_primary,local_optimum_delayed_solvable,local_optimum_role_mismatch,local_optimum_role_conflict,local_optimum_destructive_confirm,local_optimum_unsaved_changes,local_optimum_blocking_modal_unprompted_confirm"

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$ReleaseRunDir = "runs\\release_check_$stamp"
New-Item -ItemType Directory -Path $ReleaseRunDir -Force | Out-Null

if ($RunSweeps -and -not $ModelPath) {
    Write-Error "Set -ModelPath or GOLDEVIDENCEBENCH_MODEL before running sweeps."
    exit 1
}
if ($MaxReleaseUtilityBurdenDelta -lt 0.0 -or $MaxReleaseUtilityBurdenDelta -gt 1.0) {
    Write-Error "MaxReleaseUtilityBurdenDelta must be between 0.0 and 1.0."
    exit 1
}
if ($WarnReleaseUtilityBurdenDelta -lt 0.0 -or $WarnReleaseUtilityBurdenDelta -gt 1.0) {
    Write-Error "WarnReleaseUtilityBurdenDelta must be between 0.0 and 1.0."
    exit 1
}
if ($WarnReleaseUtilityBurdenDelta -gt $MaxReleaseUtilityBurdenDelta) {
    Write-Error "WarnReleaseUtilityBurdenDelta must be <= MaxReleaseUtilityBurdenDelta."
    exit 1
}
if ($MinUtilityWarningFalseCommitImprovement -lt 0.0) {
    Write-Error "MinUtilityWarningFalseCommitImprovement must be >= 0.0."
    exit 1
}
if ($MinUtilityWarningCorrectionImprovement -lt 0.0) {
    Write-Error "MinUtilityWarningCorrectionImprovement must be >= 0.0."
    exit 1
}
if ($MaxInstructionOverrideTokensPerQP90 -le 0.0) {
    Write-Error "MaxInstructionOverrideTokensPerQP90 must be > 0.0."
    exit 1
}
if ($WarnInstructionOverrideTokensPerQP90 -le 0.0) {
    Write-Error "WarnInstructionOverrideTokensPerQP90 must be > 0.0."
    exit 1
}
if ($WarnInstructionOverrideTokensPerQP90 -gt $MaxInstructionOverrideTokensPerQP90) {
    Write-Error "WarnInstructionOverrideTokensPerQP90 must be <= MaxInstructionOverrideTokensPerQP90."
    exit 1
}
if ($WarnInstructionOverrideTokensPerQMean -le 0.0) {
    Write-Error "WarnInstructionOverrideTokensPerQMean must be > 0.0."
    exit 1
}
if ($MaxInstructionOverrideWallPerQP90 -le 0.0) {
    Write-Error "MaxInstructionOverrideWallPerQP90 must be > 0.0."
    exit 1
}
if ($WarnInstructionOverrideWallPerQP90 -le 0.0) {
    Write-Error "WarnInstructionOverrideWallPerQP90 must be > 0.0."
    exit 1
}
if ($WarnInstructionOverrideWallPerQP90 -gt $MaxInstructionOverrideWallPerQP90) {
    Write-Error "WarnInstructionOverrideWallPerQP90 must be <= MaxInstructionOverrideWallPerQP90."
    exit 1
}
if ($WarnInstructionOverrideWallPerQMean -le 0.0) {
    Write-Error "WarnInstructionOverrideWallPerQMean must be > 0.0."
    exit 1
}
if ($MaxTrendInstructionOverrideTokensPerQP90Increase -lt 0.0) {
    Write-Error "MaxTrendInstructionOverrideTokensPerQP90Increase must be >= 0.0."
    exit 1
}
if ($MaxTrendInstructionOverrideWallPerQP90Increase -lt 0.0) {
    Write-Error "MaxTrendInstructionOverrideWallPerQP90Increase must be >= 0.0."
    exit 1
}
if (-not (Test-Path $MemoryVerifyInputPath)) {
    Write-Error ("MemoryVerifyInputPath does not exist: {0}" -f $MemoryVerifyInputPath)
    exit 1
}
if ($MinMemoryVerifyTotal -lt 1) {
    Write-Error "MinMemoryVerifyTotal must be >= 1."
    exit 1
}
if ($MinMemoryVerifyUseRate -lt 0.0 -or $MinMemoryVerifyUseRate -gt 1.0) {
    Write-Error "MinMemoryVerifyUseRate must be between 0.0 and 1.0."
    exit 1
}
if ($MinMemoryVerifyVerifiedRate -lt 0.0 -or $MinMemoryVerifyVerifiedRate -gt 1.0) {
    Write-Error "MinMemoryVerifyVerifiedRate must be between 0.0 and 1.0."
    exit 1
}
if ($MaxMemoryVerifyInvalidRate -lt 0.0 -or $MaxMemoryVerifyInvalidRate -gt 1.0) {
    Write-Error "MaxMemoryVerifyInvalidRate must be between 0.0 and 1.0."
    exit 1
}
if ($MaxMemoryVerifyActionsBlocked -lt 0) {
    Write-Error "MaxMemoryVerifyActionsBlocked must be >= 0."
    exit 1
}
if ($MinMemorySensitivityScenarioCount -lt 1) {
    Write-Error "MinMemorySensitivityScenarioCount must be >= 1."
    exit 1
}
if ($MinMemorySensitivityMaxInvalidRate -lt 0.0 -or $MinMemorySensitivityMaxInvalidRate -gt 1.0) {
    Write-Error "MinMemorySensitivityMaxInvalidRate must be between 0.0 and 1.0."
    exit 1
}
if ($MinMemorySensitivityMaxActionsBlocked -lt 1) {
    Write-Error "MinMemorySensitivityMaxActionsBlocked must be >= 1."
    exit 1
}
if ($MinMemorySensitivityMaxTotal -lt 1) {
    Write-Error "MinMemorySensitivityMaxTotal must be >= 1."
    exit 1
}
if ($MinMemorySensitivityDistinctTagCount -lt 1) {
    Write-Error "MinMemorySensitivityDistinctTagCount must be >= 1."
    exit 1
}
if ($MinMemorySensitivityDistinctReasonCount -lt 1) {
    Write-Error "MinMemorySensitivityDistinctReasonCount must be >= 1."
    exit 1
}
if ($MinRegressionFrontierCoverage -lt 0.0 -or $MinRegressionFrontierCoverage -gt 1.0) {
    Write-Error "MinRegressionFrontierCoverage must be between 0.0 and 1.0."
    exit 1
}
if ($MinRegressionFrontierReduction -lt 0.0 -or $MinRegressionFrontierReduction -gt 1.0) {
    Write-Error "MinRegressionFrontierReduction must be between 0.0 and 1.0."
    exit 1
}
if ($TrendReleaseWindow -lt 2) {
    Write-Error "TrendReleaseWindow must be >= 2."
    exit 1
}
if ($TrendMinHistory -lt 2) {
    Write-Error "TrendMinHistory must be >= 2."
    exit 1
}
if ($TrendMaxSnapshotAgeDays -lt 1) {
    Write-Error "TrendMaxSnapshotAgeDays must be >= 1."
    exit 1
}
if ($WarningDebtWindow -lt 2) {
    Write-Error "WarningDebtWindow must be >= 2."
    exit 1
}
if ($MaxInstructionOverrideCostWarningHits -lt 0) {
    Write-Error "MaxInstructionOverrideCostWarningHits must be >= 0."
    exit 1
}
if ($MaxInstructionOverrideCostWarningHits -ge $WarningDebtWindow) {
    Write-Error "MaxInstructionOverrideCostWarningHits must be < WarningDebtWindow."
    exit 1
}
if ($MaxUtilityBurdenWarningHits -lt 0) {
    Write-Error "MaxUtilityBurdenWarningHits must be >= 0."
    exit 1
}
if ($MaxUtilityBurdenWarningHits -ge $WarningDebtWindow) {
    Write-Error "MaxUtilityBurdenWarningHits must be < WarningDebtWindow."
    exit 1
}
if (-not (Test-Path $OptionalMetricExemptionsAllowlistPath)) {
    Write-Error ("OptionalMetricExemptionsAllowlistPath does not exist: {0}" -f $OptionalMetricExemptionsAllowlistPath)
    exit 1
}
if ($ReuseInstructionOverrideMaxAgeMinutes -lt 0) {
    Write-Error "ReuseInstructionOverrideMaxAgeMinutes must be >= 0."
    exit 1
}
if ($ReuseUiBaselinesMaxAgeMinutes -lt 0) {
    Write-Error "ReuseUiBaselinesMaxAgeMinutes must be >= 0."
    exit 1
}
if ($ReuseUtilityEvalMaxAgeMinutes -lt 0) {
    Write-Error "ReuseUtilityEvalMaxAgeMinutes must be >= 0."
    exit 1
}
if ($FastLocal -and -not $PSBoundParameters.ContainsKey("SkipWarningDebtGuard")) {
    $SkipWarningDebtGuard = $true
    Write-Host "[FAST] SkipWarningDebtGuard enabled by default in FastLocal mode."
}

$manifestPath = Join-Path $ReleaseRunDir "release_manifest.json"
$releaseLogsDir = Join-Path $ReleaseRunDir "logs"
New-Item -ItemType Directory -Path $releaseLogsDir -Force | Out-Null
$manifest = [ordered]@{
    created_at = (Get-Date -Format "s")
    model_path = $ModelPath
    gate_adapter = $GateAdapter
    selected_holdouts = [ordered]@{
        drift = $DriftHoldoutName
        bad_actor = $BadActorHoldoutId
    }
    unified_reliability_gate = [ordered]@{
        fast_local = [bool]$FastLocal
        reuse_instruction_override_max_age_minutes = $ReuseInstructionOverrideMaxAgeMinutes
        reuse_ui_baselines_max_age_minutes = $ReuseUiBaselinesMaxAgeMinutes
        reuse_utility_eval_max_age_minutes = $ReuseUtilityEvalMaxAgeMinutes
        skip_warning_debt_guard = [bool]$SkipWarningDebtGuard
        skip_require_control_families = [bool]$SkipRequireControlFamilies
        skip_derived_score_floors = [bool]$SkipDerivedScoreFloors
        skip_real_world_utility_eval = [bool]$SkipRealWorldUtilityEval
        min_reasoning_score = $MinReleaseReasoningScore
        min_planning_score = $MinReleasePlanningScore
        min_intelligence_index = $MinReleaseIntelligenceIndex
        min_implication_coherence_core = $MinReleaseImplicationCoherenceCore
        min_agency_preservation_core = $MinReleaseAgencyPreservationCore
        max_release_utility_burden_delta = $MaxReleaseUtilityBurdenDelta
        warn_release_utility_burden_delta = $WarnReleaseUtilityBurdenDelta
        min_utility_warning_false_commit_improvement = $MinUtilityWarningFalseCommitImprovement
        min_utility_warning_correction_improvement = $MinUtilityWarningCorrectionImprovement
        max_instruction_override_tokens_per_q_p90 = $MaxInstructionOverrideTokensPerQP90
        warn_instruction_override_tokens_per_q_p90 = $WarnInstructionOverrideTokensPerQP90
        warn_instruction_override_tokens_per_q_mean = $WarnInstructionOverrideTokensPerQMean
        max_instruction_override_wall_s_per_q_p90 = $MaxInstructionOverrideWallPerQP90
        warn_instruction_override_wall_s_per_q_p90 = $WarnInstructionOverrideWallPerQP90
        warn_instruction_override_wall_s_per_q_mean = $WarnInstructionOverrideWallPerQMean
        max_trend_instruction_override_tokens_per_q_p90_increase = $MaxTrendInstructionOverrideTokensPerQP90Increase
        max_trend_instruction_override_wall_s_per_q_p90_increase = $MaxTrendInstructionOverrideWallPerQP90Increase
        memory_verify_input_path = $MemoryVerifyInputPath
        min_memory_verify_total = $MinMemoryVerifyTotal
        min_memory_verify_use_rate = $MinMemoryVerifyUseRate
        min_memory_verify_verified_rate = $MinMemoryVerifyVerifiedRate
        max_memory_verify_invalid_rate = $MaxMemoryVerifyInvalidRate
        max_memory_verify_actions_blocked = $MaxMemoryVerifyActionsBlocked
        min_memory_sensitivity_scenario_count = $MinMemorySensitivityScenarioCount
        min_memory_sensitivity_max_invalid_rate = $MinMemorySensitivityMaxInvalidRate
        min_memory_sensitivity_max_actions_blocked = $MinMemorySensitivityMaxActionsBlocked
        min_memory_sensitivity_max_total = $MinMemorySensitivityMaxTotal
        min_memory_sensitivity_distinct_tag_count = $MinMemorySensitivityDistinctTagCount
        min_memory_sensitivity_distinct_reason_count = $MinMemorySensitivityDistinctReasonCount
        min_regression_frontier_coverage = $MinRegressionFrontierCoverage
        min_regression_frontier_reduction = $MinRegressionFrontierReduction
        trend_release_window = $TrendReleaseWindow
        trend_min_history = $TrendMinHistory
        trend_max_snapshot_age_days = $TrendMaxSnapshotAgeDays
        warning_debt_window = $WarningDebtWindow
        max_instruction_override_cost_warning_hits = $MaxInstructionOverrideCostWarningHits
        max_utility_burden_warning_hits = $MaxUtilityBurdenWarningHits
        max_trend_reasoning_drop = $MaxTrendReasoningDrop
        max_trend_implication_coherence_drop = $MaxTrendImplicationCoherenceDrop
        max_trend_agency_preservation_drop = $MaxTrendAgencyPreservationDrop
        strict_optional_threshold_metrics = $StrictOptionalThresholdMetrics
        optional_metric_exemptions_allowlist_path = $OptionalMetricExemptionsAllowlistPath
        fail_on_instruction_override_soft_fail = [bool]$FailOnInstructionOverrideSoftFail
    }
    artifacts = [ordered]@{
        release_gates_dir = "runs\\release_gates"
        drift_holdout_gate = "runs\\release_gates\\drift_holdout_gate.json"
        drift_holdout_latest = "runs\\drift_holdout_latest"
        bad_actor_holdout_latest = "runs\\bad_actor_holdout_latest\\summary.json"
        ui_same_label_gate = "runs\\ui_same_label_gate.json"
        ui_popup_overlay_gate = "runs\\ui_popup_overlay_gate.json"
        ui_minipilot_notepad_gate = "runs\\ui_minipilot_notepad_gate.json"
        instruction_override_gate = "runs\\release_gates\\instruction_override_gate\\summary.json"
        instruction_override_sweep_status = "runs\\release_gates\\instruction_override_gate\\sweep_status.json"
        memory_verify_gate = "runs\\release_gates\\memory_verify.json"
        memory_verify_sensitivity_gate = "runs\\release_gates\\memory_verify_sensitivity.json"
        persona_invariance_gate = "runs\\release_gates\\persona_invariance\\summary.json"
        update_burst_release_gate = "runs\\release_gates\\update_burst_full_linear_k16_bucket5_rate0.12\\summary.json"
        reliability_signal = "runs\\reliability_signal_latest.json"
        compression_reliability = "runs\\compression_reliability_latest.json"
        novel_continuity_reliability = "runs\\novel_continuity_reliability_latest.json"
        authority_under_interference_reliability = "runs\\authority_under_interference_reliability_latest.json"
        rpa_mode_switch_reliability = "runs\\rpa_mode_switch_reliability_latest.json"
        intent_spec_layer_reliability = "runs\\intent_spec_layer_reliability_latest.json"
        noise_escalation_reliability = "runs\\noise_escalation_reliability_latest.json"
        implication_coherence_reliability = "runs\\implication_coherence_reliability_latest.json"
        agency_preserving_substitution_reliability = "runs\\agency_preserving_substitution_reliability_latest.json"
        real_world_utility_eval = "runs\\real_world_utility_eval_latest.json"
        codex_compat_family_matrix = "runs\\codex_compat\\family_matrix.json"
        codex_compat_orthogonality_matrix = "runs\\codex_compat\\orthogonality_matrix.json"
        codex_compat_rpa_ablation_report = "runs\\codex_compat\\rpa_ablation_report.json"
        codex_compat_regression_frontier = "runs\\codex_compat\\regression_frontier.json"
        codex_compat_scaffold_backlog = "runs\\codex_compat\\scaffold_backlog.json"
        codex_compat_report = "docs\\CODEX_COMPAT_REPORT.md"
        codex_next_step_report = "runs\\codex_next_step_report.json"
        optional_metric_inventory = "runs\\latest_optional_metric_inventory"
        release_quality_snapshot = "runs\\latest_release_quality_snapshot"
        release_trend_guard = "runs\\latest_release_trend_guard"
    }
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -Path $manifestPath -Encoding UTF8

.\scripts\set_latest_pointer.ps1 -RunDir $ReleaseRunDir -PointerPath "runs\\latest_release" | Out-Host
Write-Host "Release manifest: $manifestPath"

$releaseIntegrityWarnings = New-Object System.Collections.Generic.List[string]
$releaseRiskWarnings = New-Object System.Collections.Generic.List[string]
if ($FastLocal) {
    $releaseIntegrityWarnings.Add("fast_local_mode")
    Write-Host "[FAST] Local iteration mode enabled; snapshot quality accrual is disabled for trend history."
}

function ConvertTo-NullableDouble {
    param([object]$Value)
    if ($null -eq $Value) {
        return $null
    }
    try {
        return [double]$Value
    } catch {
        return $null
    }
}

function Read-JsonObject {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        return $null
    }
    try {
        return Get-Content -Raw -Path $Path | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Test-ArtifactFresh {
    param(
        [string]$Path,
        [int]$MaxAgeMinutes
    )
    if ($MaxAgeMinutes -le 0) {
        return $false
    }
    if (-not (Test-Path $Path)) {
        return $false
    }
    try {
        $item = Get-Item -Path $Path
    } catch {
        return $false
    }
    $ageMinutes = ([datetimeoffset]::UtcNow - [datetimeoffset]::new($item.LastWriteTimeUtc)).TotalMinutes
    return ($ageMinutes -le $MaxAgeMinutes)
}

function Resolve-PointerTarget {
    param([string]$PointerPath)
    if (-not (Test-Path $PointerPath)) {
        return $null
    }
    try {
        $raw = Get-Content -Raw -Path $PointerPath
    } catch {
        return $null
    }
    if ($null -eq $raw) {
        return $null
    }
    $candidate = "$raw".Trim()
    if ([string]::IsNullOrWhiteSpace($candidate)) {
        return $null
    }
    return $candidate
}

function Get-MedianValue {
    param([double[]]$Values)
    if (-not $Values -or $Values.Count -eq 0) {
        return $null
    }
    $sorted = $Values | Sort-Object
    $count = $sorted.Count
    if (($count % 2) -eq 1) {
        return [double]$sorted[[int][math]::Floor($count / 2)]
    }
    $upper = [int]($count / 2)
    $lower = $upper - 1
    return ([double]$sorted[$lower] + [double]$sorted[$upper]) / 2.0
}

function Get-ReleaseSnapshotTimestampUtc {
    param(
        [object]$Snapshot,
        [string]$SnapshotPath
    )
    if ($Snapshot -and $Snapshot.generated_at_utc) {
        try {
            return [datetimeoffset]::Parse("$($Snapshot.generated_at_utc)")
        } catch {
            # Fall through to file timestamp.
        }
    }
    try {
        return [datetimeoffset]::new((Get-Item $SnapshotPath).LastWriteTimeUtc)
    } catch {
        return $null
    }
}

function Get-ReleaseSnapshotQualityAssessment {
    param(
        [object]$Snapshot,
        [string]$SnapshotPath,
        [datetimeoffset]$NowUtc,
        [int]$MaxSnapshotAgeDays,
        [int]$MinScenarioCount,
        [double]$MinMaxInvalidRate,
        [int]$MinMaxActionsBlocked,
        [int]$MinMaxTotal,
        [int]$MinDistinctTagCount,
        [int]$MinDistinctReasonCount
    )
    $reasons = @()
    $thresholdStrictOptionalModeActive = $false
    if ($Snapshot -and $Snapshot.gates -and ($Snapshot.gates.PSObject.Properties.Name -contains "threshold_strict_optional_mode_active")) {
        try {
            $thresholdStrictOptionalModeActive = [bool]$Snapshot.gates.threshold_strict_optional_mode_active
        } catch {
            $thresholdStrictOptionalModeActive = $false
        }
    }

    if ("$($Snapshot.status)" -ne "PASS") {
        $reasons += "status_not_pass"
    }

    $timestampUtc = Get-ReleaseSnapshotTimestampUtc -Snapshot $Snapshot -SnapshotPath $SnapshotPath
    $ageDays = $null
    if ($null -eq $timestampUtc) {
        $reasons += "timestamp_unavailable"
    } else {
        $ageDays = ([double]($NowUtc - $timestampUtc).TotalDays)
        if ($ageDays -gt $MaxSnapshotAgeDays) {
            $reasons += "stale_snapshot"
        }
    }

    $integrityWarningCount = ConvertTo-NullableDouble $Snapshot.integrity.warning_count
    $integrityWarnings = @()
    if ($Snapshot -and $Snapshot.integrity -and ($Snapshot.integrity.PSObject.Properties.Name -contains "warnings")) {
        $integrityWarnings = @($Snapshot.integrity.warnings | ForEach-Object { "$_" })
    }
    $effectiveIntegrityWarningCount = $integrityWarningCount
    if ($integrityWarnings.Count -gt 0 -and -not $thresholdStrictOptionalModeActive) {
        $effectiveIntegrityWarningCount = @(
            $integrityWarnings | Where-Object { $_ -notlike "threshold_optional_missing_na_count:*" }
        ).Count
    }
    if ($null -eq $integrityWarningCount) {
        $reasons += "integrity_warning_count_missing"
    } elseif ($effectiveIntegrityWarningCount -gt 0) {
        $reasons += "integrity_warnings_present"
    }

    $scenarioCount = ConvertTo-NullableDouble $Snapshot.gates.memory_sensitivity_scenario_count
    $maxInvalidRate = ConvertTo-NullableDouble $Snapshot.gates.memory_sensitivity_max_invalid_rate
    $maxActionsBlocked = ConvertTo-NullableDouble $Snapshot.gates.memory_sensitivity_max_actions_blocked
    $maxTotal = ConvertTo-NullableDouble $Snapshot.gates.memory_sensitivity_max_total
    $distinctTagCount = ConvertTo-NullableDouble $Snapshot.gates.memory_sensitivity_distinct_tag_count
    $distinctReasonCount = ConvertTo-NullableDouble $Snapshot.gates.memory_sensitivity_distinct_reason_count
    $thresholdErrorCount = ConvertTo-NullableDouble $Snapshot.gates.threshold_error_count
    $thresholdOptionalMissingCount = ConvertTo-NullableDouble $Snapshot.gates.threshold_optional_missing_na_count

    if ($null -eq $scenarioCount) { $reasons += "memory_sensitivity_scenario_count_missing" }
    if ($null -eq $maxInvalidRate) { $reasons += "memory_sensitivity_max_invalid_rate_missing" }
    if ($null -eq $maxActionsBlocked) { $reasons += "memory_sensitivity_max_actions_blocked_missing" }
    if ($null -eq $maxTotal) { $reasons += "memory_sensitivity_max_total_missing" }
    if ($null -eq $distinctTagCount) { $reasons += "memory_sensitivity_distinct_tag_count_missing" }
    if ($null -eq $distinctReasonCount) { $reasons += "memory_sensitivity_distinct_reason_count_missing" }
    if ($null -eq $thresholdErrorCount) { $reasons += "threshold_error_count_missing" }
    if ($null -eq $thresholdOptionalMissingCount) { $reasons += "threshold_optional_missing_na_count_missing" }

    if ($null -ne $scenarioCount -and $scenarioCount -lt $MinScenarioCount) {
        $reasons += "memory_sensitivity_scenario_count_below_floor"
    }
    if ($null -ne $maxInvalidRate -and $maxInvalidRate -lt $MinMaxInvalidRate) {
        $reasons += "memory_sensitivity_max_invalid_rate_below_floor"
    }
    if ($null -ne $maxActionsBlocked -and $maxActionsBlocked -lt $MinMaxActionsBlocked) {
        $reasons += "memory_sensitivity_max_actions_blocked_below_floor"
    }
    if ($null -ne $maxTotal -and $maxTotal -lt $MinMaxTotal) {
        $reasons += "memory_sensitivity_max_total_below_floor"
    }
    if ($null -ne $distinctTagCount -and $distinctTagCount -lt $MinDistinctTagCount) {
        $reasons += "memory_sensitivity_distinct_tag_count_below_floor"
    }
    if ($null -ne $distinctReasonCount -and $distinctReasonCount -lt $MinDistinctReasonCount) {
        $reasons += "memory_sensitivity_distinct_reason_count_below_floor"
    }
    if ($null -ne $thresholdErrorCount -and $thresholdErrorCount -gt 0) {
        $reasons += "threshold_errors_present"
    }
    # Optional-missing metrics are tracked/governed separately; they should not
    # disqualify snapshot quality eligibility for trend-history accrual.

    $eligible = ($reasons.Count -eq 0)
    return [pscustomobject]@{
        eligible = $eligible
        reasons = @($reasons)
        timestamp_utc = if ($timestampUtc) { $timestampUtc.ToString("o") } else { $null }
        age_days = $ageDays
        integrity_warning_count = $integrityWarningCount
    }
}

if ($RunSweeps) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $stressRoot = "runs\\wall_update_burst_full_linear_bucket10_$stamp"
    $pinRoot = "runs\\wall_update_burst_full_linear_bucket10_pin_$stamp"

    Write-Host "Running stress sweep..."
    .\scripts\run_update_burst_full_linear_bucket10.ps1 `
        -ModelPath $ModelPath `
        -OutRoot $stressRoot `
        -Rates 0.205,0.209,0.22,0.24

    Write-Host "Running pin sweep..."
    .\scripts\run_update_burst_full_linear_bucket10.ps1 `
        -ModelPath $ModelPath `
        -OutRoot $pinRoot `
        -Rates 0.18,0.19,0.195,0.20 `
        -FindWall:$true

    Write-Host "Sweeps complete: $stressRoot, $pinRoot"
}

function Get-NextHoldoutFromReport {
    param(
        [object]$Report,
        [double]$GapMin,
        [double]$SolvedMin,
        [string]$FallbackHoldout
    )
    $result = [ordered]@{
        holdout = $FallbackHoldout
        reason = "fallback"
        exhausted = $false
    }
    if (-not $Report) {
        return $result
    }
    $holdout = $Report.holdout
    $holdoutName = $holdout.name
    $holdoutSolved = $false
    $holdoutGap = 0.0
    if ($holdout) {
        $holdoutGap = [double]($holdout.sa_beats_greedy_rate)
        $holdoutSolved = (
            [double]($holdout.policy_task_pass_rate_min) -ge $SolvedMin -and
            [double]($holdout.greedy_task_pass_rate_min) -ge $SolvedMin
        )
    }
    if (-not $holdoutSolved -or $holdoutGap -ge $GapMin) {
        $result.holdout = $holdoutName
        $result.reason = "holdout_unsolved"
        return $result
    }
    $candidates = @()
    $variantBreakdown = $Report.variant_breakdown
    if ($variantBreakdown) {
        foreach ($prop in $variantBreakdown.PSObject.Properties) {
            $name = $prop.Name
            $data = $prop.Value
            if ($data.excluded_from_distillation -eq $true) {
                continue
            }
            $gap = [double]($data.sa_beats_greedy_rate)
            if ($gap -lt $GapMin) {
                continue
            }
            $candidates += [pscustomobject]@{
                name = $name
                gap = $gap
                greedy_min = [double]($data.greedy_task_pass_rate_min)
                policy_min = [double]($data.policy_task_pass_rate_min)
            }
        }
    }
    if ($candidates.Count -gt 0) {
        $pick = $candidates | Sort-Object `
            @{ Expression = "gap"; Descending = $true }, `
            @{ Expression = "greedy_min"; Descending = $false }, `
            @{ Expression = "policy_min"; Descending = $false } | Select-Object -First 1
        $result.holdout = $pick.name
        $result.reason = "gap_candidate"
        return $result
    }
    $result.holdout = $holdoutName
    $result.reason = "curriculum_exhausted"
    $result.exhausted = $true
    return $result
}

if (-not $SkipThresholds) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $resolvedHoldout = $VariantsHoldoutName
    if ($AutoCurriculum) {
        $prevReportPath = "runs\\release_gates\\ui_local_optimum_distillation.json"
        if (Test-Path $prevReportPath) {
            try {
                $report = Get-Content $prevReportPath -Raw | ConvertFrom-Json
                $choice = Get-NextHoldoutFromReport -Report $report -GapMin $AutoCurriculumGapMin -SolvedMin $AutoCurriculumSolvedMin -FallbackHoldout $resolvedHoldout
                if ($choice.holdout) {
                    $resolvedHoldout = $choice.holdout
                    New-Item -ItemType Directory -Path (Split-Path $AutoCurriculumStatePath) -Force | Out-Null
                    [pscustomobject]@{
                        used_holdout = $resolvedHoldout
                        reason = $choice.reason
                        exhausted = $choice.exhausted
                        gap_min = $AutoCurriculumGapMin
                        solved_min = $AutoCurriculumSolvedMin
                        source_report = $prevReportPath
                        updated_at = (Get-Date -Format "s")
                    } | ConvertTo-Json -Depth 4 | Set-Content -Path $AutoCurriculumStatePath -Encoding UTF8
                    if ($choice.exhausted) {
                        Write-Host "AutoCurriculum: no oracle gap found in previous report (curriculum exhausted)."
                    } else {
                        Write-Host ("AutoCurriculum holdout: {0} ({1})" -f $resolvedHoldout, $choice.reason)
                    }
                }
            } catch {
                Write-Host "AutoCurriculum: failed to parse prior distillation report."
            }
        } else {
            Write-Host "AutoCurriculum: no prior distillation report found; using configured holdout."
        }
    } elseif ($RotateHoldout) {
    $resolvedList = $HoldoutList
    if (-not $resolvedList) {
        if (Test-Path $HoldoutListPath) {
            try {
                $holdoutConfig = Get-Content $HoldoutListPath -Raw | ConvertFrom-Json
                if ($holdoutConfig -and $holdoutConfig.holdouts) {
                    $holdoutNames = @(
                        $holdoutConfig.holdouts | ForEach-Object { $_.ToString().Trim() } | Where-Object { $_ }
                    )
                }
            } catch {
                $holdoutNames = @()
            }
        }
    }
    if (-not $holdoutNames -or $holdoutNames.Count -eq 0) {
        if (-not $resolvedList) {
            $resolvedList = $DefaultHoldoutList
        }
        $holdoutNames = @(
            $resolvedList -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ }
        )
    }
        if (-not $holdoutNames -or $holdoutNames.Count -eq 0) {
            Write-Host "RotateHoldout ignored: HoldoutList is empty."
        } else {
            $statePath = "runs\\release_gates\\ui_holdout_rotation.json"
            $state = $null
            if (Test-Path $statePath) {
                try {
                    $state = Get-Content $statePath -Raw | ConvertFrom-Json
                } catch {
                    $state = $null
                }
            }
            $index = 0
            if ($state -and $state.index -is [int]) {
                $index = [int]$state.index
            }
            $resolvedHoldout = $holdoutNames[$index % $holdoutNames.Count]
            $nextIndex = ($index + 1) % $holdoutNames.Count
            New-Item -ItemType Directory -Path (Split-Path $statePath) -Force | Out-Null
            [pscustomobject]@{
                index = $nextIndex
                holdout = $resolvedHoldout
                updated_at = (Get-Date -Format "s")
                list = $holdoutNames
            } | ConvertTo-Json -Depth 4 | Set-Content -Path $statePath -Encoding UTF8
            Write-Host ("RotateHoldout: {0}" -f $resolvedHoldout)
        }
    }

    $instructionOverrideTokensPerQP90 = $null
    $instructionOverrideWallPerQP90 = $null
    $instructionOverrideCostWarnTriggered = $false

    Write-Host "Running instruction override gate..."
    $instructionOverrideSummary = "runs\\release_gates\\instruction_override_gate\\summary.json"
    $instructionOverrideSweepStatus = "runs\\release_gates\\instruction_override_gate\\sweep_status.json"
    $reuseInstructionOverride = $false
    if ($FastLocal -and (Test-ArtifactFresh -Path $instructionOverrideSummary -MaxAgeMinutes $ReuseInstructionOverrideMaxAgeMinutes)) {
        $cachedReusable = $true
        $cachedOutcome = ""
        if (Test-Path $instructionOverrideSweepStatus) {
            $cachedSweepStatus = Read-JsonObject -Path $instructionOverrideSweepStatus
            if (-not $cachedSweepStatus) {
                $cachedReusable = $false
            } else {
                $cachedOutcome = "$($cachedSweepStatus.sweep_outcome)"
                if ($cachedOutcome -ne "pass" -and $cachedOutcome -ne "soft_fail_artifacts_complete") {
                    $cachedReusable = $false
                }
                if ($FailOnInstructionOverrideSoftFail -and $cachedOutcome -eq "soft_fail_artifacts_complete") {
                    $cachedReusable = $false
                }
            }
        } elseif ($FailOnInstructionOverrideSoftFail) {
            $cachedReusable = $false
        }
        if ($cachedReusable) {
            $reuseInstructionOverride = $true
            Write-Host ("[FAST] Reusing instruction override artifacts ({0}, max_age={1}m)." -f $instructionOverrideSummary, $ReuseInstructionOverrideMaxAgeMinutes)
        }
    }
    if (-not $reuseInstructionOverride) {
        $instructionOverrideParams = @{
            ModelPath = $ModelPath
            Adapter = $GateAdapter
        }
        if ($FastLocal) {
            $instructionOverrideParams.Seeds = 2
            $instructionOverrideParams.StateModesCsv = "kv"
            $instructionOverrideParams.DistractorProfilesCsv = "standard,instruction_suite"
            $instructionOverrideParams.Episodes = 1
            $instructionOverrideParams.Steps = 60
            $instructionOverrideParams.Queries = 8
            $instructionOverrideParams.MaxBookTokens = 320
            Write-Host "[FAST] Using reduced instruction override sweep settings for local iteration."
        }
        if ($FailOnInstructionOverrideSoftFail) {
            $instructionOverrideParams.FailOnSweepSoftFail = $true
        }
        .\scripts\run_instruction_override_gate.ps1 @instructionOverrideParams
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Instruction override gate failed."
            exit 1
        }
    } else {
        Write-Host "Instruction override gate: runs\\release_gates\\instruction_override_gate\\summary.json"
        if (Test-Path $instructionOverrideSweepStatus) {
            Write-Host "Instruction override sweep status: runs\\release_gates\\instruction_override_gate\\sweep_status.json"
        }
    }
    if (-not (Test-Path $instructionOverrideSummary)) {
        Write-Error "Instruction override gate did not produce summary.json."
        exit 1
    }
    $instructionOverridePayload = Read-JsonObject -Path $instructionOverrideSummary
    if (-not $instructionOverridePayload) {
        Write-Error ("Unable to parse instruction override summary: {0}" -f $instructionOverrideSummary)
        exit 1
    }
    $instructionOverrideEfficiency = $instructionOverridePayload.efficiency
    if (-not $instructionOverrideEfficiency) {
        Write-Error "Instruction override summary missing efficiency block; rerun gate with updated summarizer."
        exit 1
    }
    $instructionOverrideTokensPerQP90 = ConvertTo-NullableDouble $instructionOverrideEfficiency.tokens_per_q_p90
    $instructionOverrideTokensPerQMean = ConvertTo-NullableDouble $instructionOverrideEfficiency.tokens_per_q_mean
    $instructionOverrideWallPerQP90 = ConvertTo-NullableDouble $instructionOverrideEfficiency.wall_s_per_q_p90
    $instructionOverrideWallPerQMean = ConvertTo-NullableDouble $instructionOverrideEfficiency.wall_s_per_q_mean
    if ($null -eq $instructionOverrideTokensPerQP90 -or $null -eq $instructionOverrideWallPerQP90 -or $null -eq $instructionOverrideTokensPerQMean -or $null -eq $instructionOverrideWallPerQMean) {
        Write-Error "Instruction override summary missing required efficiency mean/p90 metrics."
        exit 1
    }
    if ($instructionOverrideTokensPerQP90 -gt $MaxInstructionOverrideTokensPerQP90) {
        Write-Error ("Instruction override cost gate failed: tokens_per_q_p90={0:N6} > cap={1:N6}" -f $instructionOverrideTokensPerQP90, $MaxInstructionOverrideTokensPerQP90)
        exit 1
    }
    if ($instructionOverrideWallPerQP90 -gt $MaxInstructionOverrideWallPerQP90) {
        Write-Error ("Instruction override cost gate failed: wall_s_per_q_p90={0:N6} > cap={1:N6}" -f $instructionOverrideWallPerQP90, $MaxInstructionOverrideWallPerQP90)
        exit 1
    }
    Write-Host ("[PASS] instruction_override.tokens_per_q_p90={0:N6} <= {1:N6}" -f $instructionOverrideTokensPerQP90, $MaxInstructionOverrideTokensPerQP90)
    Write-Host ("[PASS] instruction_override.wall_s_per_q_p90={0:N6} <= {1:N6}" -f $instructionOverrideWallPerQP90, $MaxInstructionOverrideWallPerQP90)
    $instructionTokenWarning = ($instructionOverrideTokensPerQP90 -gt $WarnInstructionOverrideTokensPerQP90) -and ($instructionOverrideTokensPerQMean -gt $WarnInstructionOverrideTokensPerQMean)
    $instructionWallWarning = ($instructionOverrideWallPerQP90 -gt $WarnInstructionOverrideWallPerQP90) -and ($instructionOverrideWallPerQMean -gt $WarnInstructionOverrideWallPerQMean)
    if ($instructionTokenWarning -or $instructionWallWarning) {
        $instructionOverrideCostWarnTriggered = $true
        Write-Warning ("Instruction override cost warning zone: tokens_per_q_mean/p90={0:N6}/{1:N6} (warn={2:N6}/{3:N6}), wall_s_per_q_mean/p90={4:N6}/{5:N6} (warn={6:N6}/{7:N6})" -f `
            $instructionOverrideTokensPerQMean, $instructionOverrideTokensPerQP90, $WarnInstructionOverrideTokensPerQMean, $WarnInstructionOverrideTokensPerQP90, `
            $instructionOverrideWallPerQMean, $instructionOverrideWallPerQP90, $WarnInstructionOverrideWallPerQMean, $WarnInstructionOverrideWallPerQP90)
        $releaseRiskWarnings.Add("instruction_override_cost_warning_zone")
    }
    if (Test-Path $instructionOverrideSweepStatus) {
        try {
            $sweepStatus = Get-Content -Raw $instructionOverrideSweepStatus | ConvertFrom-Json
            if ($sweepStatus -and $sweepStatus.sweep_outcome -eq "soft_fail_artifacts_complete") {
                Write-Warning ("Instruction override gate completed with normalized soft-fail (exit={0}, completed_runs={1}/{2})." -f `
                    $sweepStatus.sweep_exit_code, $sweepStatus.completed_runs, $sweepStatus.expected_runs)
                $releaseIntegrityWarnings.Add("instruction_override_soft_fail_normalized")
            }
        } catch {
            Write-Warning "Instruction override sweep_status.json is unreadable."
            $releaseIntegrityWarnings.Add("instruction_override_sweep_status_unreadable")
        }
    } else {
        Write-Warning "Instruction override gate missing sweep_status.json."
        $releaseIntegrityWarnings.Add("instruction_override_sweep_status_missing")
    }
    if (Test-Path $instructionOverrideSummary) {
        .\scripts\set_latest_pointer.ps1 -RunDir $instructionOverrideSummary -PointerPath "runs\\latest_instruction_override_gate" | Out-Host
    }
    Write-Host ("Running memory verification gate (input={0})..." -f $MemoryVerifyInputPath)
    python .\scripts\verify_memories.py --in $MemoryVerifyInputPath `
        --out .\runs\release_gates\memory_verify.json `
        --out-details .\runs\release_gates\memory_verify_details.json
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Memory verification gate failed."
        exit $LASTEXITCODE
    }
    $memoryVerify = "runs\\release_gates\\memory_verify.json"
    if (Test-Path $memoryVerify) {
        .\scripts\set_latest_pointer.ps1 -RunDir $memoryVerify -PointerPath "runs\\latest_memory_verify_gate" | Out-Host
    }
    $memoryVerifyPayload = Read-JsonObject -Path $memoryVerify
    if (-not $memoryVerifyPayload) {
        Write-Error "Unable to parse memory verification payload: $memoryVerify"
        exit 1
    }
    $memoryTotal = ConvertTo-NullableDouble $memoryVerifyPayload.memory_total
    $memoryUseRate = ConvertTo-NullableDouble $memoryVerifyPayload.memory_use_rate
    $memoryVerifiedRate = ConvertTo-NullableDouble $memoryVerifyPayload.memory_verified_rate
    $memoryInvalidRate = ConvertTo-NullableDouble $memoryVerifyPayload.memory_invalid_rate
    $memoryActionsBlocked = ConvertTo-NullableDouble $memoryVerifyPayload.actions_blocked_by_memory_gate
    if ($null -eq $memoryTotal -or $null -eq $memoryUseRate -or $null -eq $memoryVerifiedRate -or `
        $null -eq $memoryInvalidRate -or $null -eq $memoryActionsBlocked) {
        Write-Error "Memory verification payload missing required numeric metrics."
        exit 1
    }
    if ($memoryTotal -lt $MinMemoryVerifyTotal) {
        Write-Error ("Memory verification gate failed: memory_total={0:N0} < floor={1:N0}" -f $memoryTotal, $MinMemoryVerifyTotal)
        exit 1
    }
    if ($memoryUseRate -lt $MinMemoryVerifyUseRate) {
        Write-Error ("Memory verification gate failed: memory_use_rate={0:N6} < floor={1:N6}" -f $memoryUseRate, $MinMemoryVerifyUseRate)
        exit 1
    }
    if ($memoryVerifiedRate -lt $MinMemoryVerifyVerifiedRate) {
        Write-Error ("Memory verification gate failed: memory_verified_rate={0:N6} < floor={1:N6}" -f $memoryVerifiedRate, $MinMemoryVerifyVerifiedRate)
        exit 1
    }
    if ($memoryInvalidRate -gt $MaxMemoryVerifyInvalidRate) {
        Write-Error ("Memory verification gate failed: memory_invalid_rate={0:N6} > cap={1:N6}" -f $memoryInvalidRate, $MaxMemoryVerifyInvalidRate)
        exit 1
    }
    if ($memoryActionsBlocked -gt $MaxMemoryVerifyActionsBlocked) {
        Write-Error ("Memory verification gate failed: actions_blocked_by_memory_gate={0:N0} > cap={1:N0}" -f $memoryActionsBlocked, $MaxMemoryVerifyActionsBlocked)
        exit 1
    }
    Write-Host ("[PASS] memory_verify.memory_total={0:N0} >= {1:N0}" -f $memoryTotal, $MinMemoryVerifyTotal)
    Write-Host ("[PASS] memory_verify.memory_use_rate={0:N6} >= {1:N6}" -f $memoryUseRate, $MinMemoryVerifyUseRate)
    Write-Host ("[PASS] memory_verify.memory_verified_rate={0:N6} >= {1:N6}" -f $memoryVerifiedRate, $MinMemoryVerifyVerifiedRate)
    Write-Host ("[PASS] memory_verify.memory_invalid_rate={0:N6} <= {1:N6}" -f $memoryInvalidRate, $MaxMemoryVerifyInvalidRate)
    Write-Host ("[PASS] memory_verify.actions_blocked_by_memory_gate={0:N0} <= {1:N0}" -f $memoryActionsBlocked, $MaxMemoryVerifyActionsBlocked)
    Write-Host "Memory verification robustness is enforced by sensitivity coverage gate; primary gate validates live memory payload integrity."

    Write-Host "Running memory verification sensitivity gate..."
    Write-Host "Note: sensitivity fixtures intentionally include synthetic invalid-citation modes (including missing-file) to validate blocker behavior."
    python .\scripts\run_memory_verify_sensitivity.py `
        --out .\runs\release_gates\memory_verify_sensitivity.json
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Memory verification sensitivity gate failed."
        exit $LASTEXITCODE
    }
    $memoryVerifySensitivity = "runs\\release_gates\\memory_verify_sensitivity.json"
    if (Test-Path $memoryVerifySensitivity) {
        .\scripts\set_latest_pointer.ps1 -RunDir $memoryVerifySensitivity -PointerPath "runs\\latest_memory_verify_sensitivity_gate" | Out-Host
    }
    $memorySensitivityPayload = Read-JsonObject -Path $memoryVerifySensitivity
    if (-not $memorySensitivityPayload) {
        Write-Error "Unable to parse memory verification sensitivity payload: $memoryVerifySensitivity"
        exit 1
    }
    if ("$($memorySensitivityPayload.status)" -ne "PASS") {
        Write-Error "Memory verification sensitivity payload status is not PASS."
        exit 1
    }
    $memorySensitivityCoverage = $memorySensitivityPayload.coverage
    $memorySensitivityChecks = $memorySensitivityPayload.checks
    if (-not $memorySensitivityCoverage -or -not $memorySensitivityChecks) {
        Write-Error "Memory verification sensitivity payload missing coverage/checks sections."
        exit 1
    }

    $sensitivityScenarioCount = ConvertTo-NullableDouble $memorySensitivityCoverage.scenario_count
    $sensitivityMaxInvalidRate = ConvertTo-NullableDouble $memorySensitivityCoverage.max_invalid_rate
    $sensitivityMaxActionsBlocked = ConvertTo-NullableDouble $memorySensitivityCoverage.max_actions_blocked
    $sensitivityMaxTotal = ConvertTo-NullableDouble $memorySensitivityCoverage.max_total
    $sensitivityDistinctTagCount = ConvertTo-NullableDouble $memorySensitivityCoverage.distinct_tag_count
    $sensitivityDistinctReasonCount = ConvertTo-NullableDouble $memorySensitivityCoverage.distinct_reason_count
    if ($null -eq $sensitivityScenarioCount -or $null -eq $sensitivityMaxInvalidRate -or `
        $null -eq $sensitivityMaxActionsBlocked -or $null -eq $sensitivityMaxTotal -or `
        $null -eq $sensitivityDistinctTagCount -or $null -eq $sensitivityDistinctReasonCount) {
        Write-Error "Memory verification sensitivity coverage missing numeric metrics."
        exit 1
    }

    $requiredSensitivityChecks = @(
        "monotonic_invalid_rate",
        "monotonic_verified_rate",
        "blocked_equals_invalid",
        "blocked_matches_expected",
        "all_used_count_expected",
        "invalid_rate_matches_expected",
        "verified_rate_matches_expected",
        "unused_entries_excluded",
        "range_exercised",
        "high_scale_exercised",
        "tag_reason_diversity"
    )
    $availableSensitivityChecks = @($memorySensitivityChecks.PSObject.Properties.Name)
    foreach ($checkName in $requiredSensitivityChecks) {
        if ($availableSensitivityChecks -notcontains $checkName) {
            Write-Error "Memory verification sensitivity check missing: $checkName"
            exit 1
        }
        if (-not [bool]$memorySensitivityChecks.$checkName) {
            Write-Error "Memory verification sensitivity check failed: $checkName"
            exit 1
        }
    }

    if ($sensitivityScenarioCount -lt $MinMemorySensitivityScenarioCount) {
        Write-Error ("Memory verification sensitivity coverage failed: scenario_count={0:N0} < floor={1:N0}" -f $sensitivityScenarioCount, $MinMemorySensitivityScenarioCount)
        exit 1
    }
    if ($sensitivityMaxInvalidRate -lt $MinMemorySensitivityMaxInvalidRate) {
        Write-Error ("Memory verification sensitivity coverage failed: max_invalid_rate={0:N6} < floor={1:N6}" -f $sensitivityMaxInvalidRate, $MinMemorySensitivityMaxInvalidRate)
        exit 1
    }
    if ($sensitivityMaxActionsBlocked -lt $MinMemorySensitivityMaxActionsBlocked) {
        Write-Error ("Memory verification sensitivity coverage failed: max_actions_blocked={0:N0} < floor={1:N0}" -f $sensitivityMaxActionsBlocked, $MinMemorySensitivityMaxActionsBlocked)
        exit 1
    }
    if ($sensitivityMaxTotal -lt $MinMemorySensitivityMaxTotal) {
        Write-Error ("Memory verification sensitivity coverage failed: max_total={0:N0} < floor={1:N0}" -f $sensitivityMaxTotal, $MinMemorySensitivityMaxTotal)
        exit 1
    }
    if ($sensitivityDistinctTagCount -lt $MinMemorySensitivityDistinctTagCount) {
        Write-Error ("Memory verification sensitivity coverage failed: distinct_tag_count={0:N0} < floor={1:N0}" -f $sensitivityDistinctTagCount, $MinMemorySensitivityDistinctTagCount)
        exit 1
    }
    if ($sensitivityDistinctReasonCount -lt $MinMemorySensitivityDistinctReasonCount) {
        Write-Error ("Memory verification sensitivity coverage failed: distinct_reason_count={0:N0} < floor={1:N0}" -f $sensitivityDistinctReasonCount, $MinMemorySensitivityDistinctReasonCount)
        exit 1
    }
    Write-Host ("[PASS] memory_sensitivity.scenario_count={0:N0} >= {1:N0}" -f $sensitivityScenarioCount, $MinMemorySensitivityScenarioCount)
    Write-Host ("[PASS] memory_sensitivity.max_invalid_rate={0:N6} >= {1:N6}" -f $sensitivityMaxInvalidRate, $MinMemorySensitivityMaxInvalidRate)
    Write-Host ("[PASS] memory_sensitivity.max_actions_blocked={0:N0} >= {1:N0}" -f $sensitivityMaxActionsBlocked, $MinMemorySensitivityMaxActionsBlocked)
    Write-Host ("[PASS] memory_sensitivity.max_total={0:N0} >= {1:N0}" -f $sensitivityMaxTotal, $MinMemorySensitivityMaxTotal)
    Write-Host ("[PASS] memory_sensitivity.distinct_tag_count={0:N0} >= {1:N0}" -f $sensitivityDistinctTagCount, $MinMemorySensitivityDistinctTagCount)
    Write-Host ("[PASS] memory_sensitivity.distinct_reason_count={0:N0} >= {1:N0}" -f $sensitivityDistinctReasonCount, $MinMemorySensitivityDistinctReasonCount)

    Write-Host "Running UI same_label stub..."
    $uiSameLog = Join-Path $releaseLogsDir "ui_same_label_stub.log"
    .\scripts\run_ui_same_label_stub.ps1 *> $uiSameLog
    if ($LASTEXITCODE -ne 0) {
        Write-Error "UI same_label stub failed. See $uiSameLog"
        if (Test-Path $uiSameLog) { Get-Content $uiSameLog -Tail 40 | Out-Host }
        exit $LASTEXITCODE
    }
    Write-Host "UI same_label stub complete (log: $uiSameLog)"
    if (Test-Path "runs\\ui_same_label_gate.json") {
        .\scripts\set_latest_pointer.ps1 -RunDir "runs\\ui_same_label_gate.json" -PointerPath "runs\\latest_ui_same_label_gate" | Out-Host
    }
    Write-Host "Running UI popup_overlay stub..."
    $uiPopupLog = Join-Path $releaseLogsDir "ui_popup_overlay_stub.log"
    .\scripts\run_ui_popup_overlay_stub.ps1 *> $uiPopupLog
    if ($LASTEXITCODE -ne 0) {
        Write-Error "UI popup_overlay stub failed. See $uiPopupLog"
        if (Test-Path $uiPopupLog) { Get-Content $uiPopupLog -Tail 40 | Out-Host }
        exit $LASTEXITCODE
    }
    Write-Host "UI popup_overlay stub complete (log: $uiPopupLog)"
    if (Test-Path "runs\\ui_popup_overlay_gate.json") {
        .\scripts\set_latest_pointer.ps1 -RunDir "runs\\ui_popup_overlay_gate.json" -PointerPath "runs\\latest_ui_popup_overlay_gate" | Out-Host
    }
    Write-Host "Running UI minipilot notepad stub..."
    $uiNotepadLog = Join-Path $releaseLogsDir "ui_minipilot_notepad_stub.log"
    .\scripts\run_ui_minipilot_notepad_stub.ps1 *> $uiNotepadLog
    if ($LASTEXITCODE -ne 0) {
        Write-Error "UI minipilot notepad stub failed. See $uiNotepadLog"
        if (Test-Path $uiNotepadLog) { Get-Content $uiNotepadLog -Tail 40 | Out-Host }
        exit $LASTEXITCODE
    }
    Write-Host "UI minipilot notepad stub complete (log: $uiNotepadLog)"
    if (Test-Path "runs\\ui_minipilot_notepad_gate.json") {
        .\scripts\set_latest_pointer.ps1 -RunDir "runs\\ui_minipilot_notepad_gate.json" -PointerPath "runs\\latest_ui_minipilot_notepad_gate" | Out-Host
    }
    Write-Host "Validating demo presets..."
    $demoConfigPath = "configs\\demo_presets.json"
    if (Test-Path $demoConfigPath) {
        $demoConfig = Get-Content $demoConfigPath -Raw | ConvertFrom-Json
        $presetMap = @{}
        foreach ($preset in $demoConfig.presets) {
            if ($preset.name) {
                $presetMap[$preset.name.ToLowerInvariant()] = $preset
            }
        }
        function Test-PresetArgs {
            param(
                [string]$Name,
                [string[]]$Required
            )
            if (-not $presetMap.ContainsKey($Name.ToLowerInvariant())) {
                Write-Error "Missing preset: $Name"
                return $false
            }
            $argsLower = @()
            foreach ($arg in $presetMap[$Name.ToLowerInvariant()].args) {
                $argsLower += $arg.ToString().ToLowerInvariant()
            }
            foreach ($req in $Required) {
                if (-not ($argsLower -contains $req.ToLowerInvariant())) {
                    Write-Error "Preset '$Name' missing required arg: $req"
                    return $false
                }
            }
            return $true
        }
        $demoOk = $true
        $demoOk = (Test-PresetArgs -Name "notepad" -Required @("-Text","-FilePath","-OnExistingFile","-InputMode","-VerifySaved","-CloseAfterSave")) -and $demoOk
        $demoOk = (Test-PresetArgs -Name "form" -Required @("-Username","-Password","-OutputPath","-VerifySaved","-CloseAfterSave")) -and $demoOk
        $demoOk = (Test-PresetArgs -Name "calculator" -Required @("-Expression","-Expected","-VerifyResult","-CloseAfter")) -and $demoOk
        $demoOk = (Test-PresetArgs -Name "notepad_calc" -Required @("-Text","-FilePath","-Expression","-Expected")) -and $demoOk
        if (-not $demoOk) {
            Write-Error "Demo preset validation failed."
            exit 1
        }
    } else {
        Write-Warning "Demo presets config not found; skipping demo preset validation."
    }
    if ($ModelPath) {
        Write-Host "Running demo dry-runs (live presets)..."
        .\scripts\run_demo.ps1 -ModelPath $ModelPath -Preset notepad -DryRun
        if ($LASTEXITCODE -ne 0) { Write-Error "Demo dry-run failed: notepad"; exit 1 }
        .\scripts\run_demo.ps1 -ModelPath $ModelPath -Preset form -DryRun
        if ($LASTEXITCODE -ne 0) { Write-Error "Demo dry-run failed: form"; exit 1 }
        .\scripts\run_demo.ps1 -ModelPath $ModelPath -Preset calculator -DryRun
        if ($LASTEXITCODE -ne 0) { Write-Error "Demo dry-run failed: calculator"; exit 1 }
    } else {
        Write-Host "Skipping demo dry-runs: ModelPath not set."
    }
    $uiBaselineOutputs = @(
        "runs\\ui_minipilot_notepad_search.json",
        "runs\\ui_minipilot_form_search.json",
        "runs\\ui_minipilot_table_search.json",
        "runs\\ui_minipilot_notepad_ambiguous_search.json",
        "runs\\ui_minipilot_notepad_wrong_directory_detour_search.json",
        "runs\\ui_minipilot_local_optimum_search.json",
        "runs\\ui_minipilot_local_optimum_delayed_ambiguous_search.json",
        "runs\\ui_minipilot_local_optimum_blocking_modal_unmentioned_ambiguous_search.json",
        "runs\\ui_minipilot_local_optimum_blocking_modal_unmentioned_blocked_ambiguous_search.json",
        "runs\\ui_minipilot_local_optimum_blocking_modal_required_ambiguous_search.json",
        "runs\\ui_minipilot_local_optimum_blocking_modal_permission_ambiguous_search.json",
        "runs\\ui_minipilot_local_optimum_blocking_modal_consent_ambiguous_search.json",
        "runs\\ui_minipilot_local_optimum_disabled_primary_ambiguous_search.json",
        "runs\\ui_minipilot_local_optimum_toolbar_vs_menu_ambiguous_search.json",
        "runs\\ui_minipilot_local_optimum_confirm_then_apply_ambiguous_search.json",
        "runs\\ui_minipilot_local_optimum_tab_state_reset_ambiguous_search.json",
        "runs\\ui_minipilot_local_optimum_context_switch_ambiguous_search.json",
        "runs\\ui_minipilot_local_optimum_stale_tab_state_ambiguous_search.json",
        "runs\\ui_minipilot_local_optimum_form_validation_ambiguous_search.json",
        "runs\\ui_minipilot_local_optimum_window_focus_ambiguous_search.json",
        "runs\\ui_minipilot_local_optimum_checkbox_gate_ambiguous_search.json",
        "runs\\ui_minipilot_local_optimum_panel_toggle_ambiguous_search.json",
        "runs\\ui_minipilot_local_optimum_accessibility_label_ambiguous_search.json",
        "runs\\ui_minipilot_local_optimum_section_path_ambiguous_search.json",
        "runs\\ui_minipilot_local_optimum_section_path_conflict_ambiguous_search.json",
        "runs\\ui_minipilot_local_optimum_blocking_modal_unprompted_confirm_ambiguous_search.json",
        "runs\\ui_minipilot_local_optimum_destructive_confirm_ambiguous_search.json",
        "runs\\ui_minipilot_local_optimum_role_conflict_ambiguous_search.json"
    )
    $reuseUiBaselines = $false
    if ($FastLocal) {
        $staleUiBaselineOutputs = @(
            $uiBaselineOutputs | Where-Object { -not (Test-ArtifactFresh -Path $_ -MaxAgeMinutes $ReuseUiBaselinesMaxAgeMinutes) }
        )
        if ($staleUiBaselineOutputs.Count -eq 0) {
            $reuseUiBaselines = $true
            Write-Host ("[FAST] Reusing {0} UI baseline outputs (max_age={1}m)." -f $uiBaselineOutputs.Count, $ReuseUiBaselinesMaxAgeMinutes)
        } else {
            Write-Host ("[FAST] UI baseline cache miss ({0} stale/missing artifacts); recomputing baselines." -f $staleUiBaselineOutputs.Count)
        }
    }
    if (-not $reuseUiBaselines) {
        Write-Host "Running UI minipilot notepad baseline (step overhead)..."
        python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_notepad_fixture.jsonl `
            --observed .\data\ui_minipilot_notepad_observed_ok.jsonl `
            --out .\runs\ui_minipilot_notepad_search.json
        Write-Host "Running UI minipilot form baseline (step overhead)..."
        python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_form_fixture.jsonl `
            --observed .\data\ui_minipilot_form_observed_ok.jsonl `
            --out .\runs\ui_minipilot_form_search.json
        Write-Host "Running UI minipilot table baseline (step overhead)..."
        python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_table_fixture.jsonl `
            --observed .\data\ui_minipilot_table_observed_ok.jsonl `
            --out .\runs\ui_minipilot_table_search.json
        Write-Host "Running UI minipilot notepad ambiguous baseline..."
        python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_notepad_ambiguous_fixture.jsonl `
            --observed .\data\ui_minipilot_notepad_ambiguous_observed_ok.jsonl `
            --out .\runs\ui_minipilot_notepad_ambiguous_search.json
        Write-Host "Running UI minipilot notepad wrong-directory detour baseline..."
        python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_notepad_wrong_directory_detour_fixture.jsonl `
            --observed .\data\ui_minipilot_notepad_wrong_directory_detour_observed_ok.jsonl `
            --out .\runs\ui_minipilot_notepad_wrong_directory_detour_search.json
        Write-Host "Running UI local-optimum baseline (SA discriminator)..."
        python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_fixture.jsonl `
            --observed .\data\ui_minipilot_local_optimum_observed_ok.jsonl --out .\runs\ui_minipilot_local_optimum_search.json --seeds 10

        Write-Host "Running UI local-optimum delayed ambiguous baseline..."
        python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_delayed_ambiguous_fixture.jsonl `
            --observed .\data\ui_minipilot_local_optimum_delayed_ambiguous_observed_ok.jsonl `
            --out .\runs\ui_minipilot_local_optimum_delayed_ambiguous_search.json
        Write-Host "Running UI local-optimum blocking modal unmentioned ambiguous baseline..."
        python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_blocking_modal_unmentioned_ambiguous_fixture.jsonl `
            --observed .\data\ui_minipilot_local_optimum_blocking_modal_unmentioned_ambiguous_observed_ok.jsonl `
            --out .\runs\ui_minipilot_local_optimum_blocking_modal_unmentioned_ambiguous_search.json
        Write-Host "Running UI local-optimum blocking modal unmentioned blocked ambiguous baseline..."
        python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_blocking_modal_unmentioned_blocked_ambiguous_fixture.jsonl `
            --observed .\data\ui_minipilot_local_optimum_blocking_modal_unmentioned_blocked_ambiguous_observed_ok.jsonl `
            --out .\runs\ui_minipilot_local_optimum_blocking_modal_unmentioned_blocked_ambiguous_search.json
        Write-Host "Running UI local-optimum blocking modal required ambiguous baseline..."
        python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_blocking_modal_required_ambiguous_fixture.jsonl `
            --observed .\data\ui_minipilot_local_optimum_blocking_modal_required_ambiguous_observed_ok.jsonl `
            --out .\runs\ui_minipilot_local_optimum_blocking_modal_required_ambiguous_search.json
        Write-Host "Running UI local-optimum blocking modal permission ambiguous baseline..."
        python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_blocking_modal_permission_ambiguous_fixture.jsonl `
            --observed .\data\ui_minipilot_local_optimum_blocking_modal_permission_ambiguous_observed_ok.jsonl `
            --out .\runs\ui_minipilot_local_optimum_blocking_modal_permission_ambiguous_search.json
        Write-Host "Running UI local-optimum blocking modal consent ambiguous baseline..."
        python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_blocking_modal_consent_ambiguous_fixture.jsonl `
            --observed .\data\ui_minipilot_local_optimum_blocking_modal_consent_ambiguous_observed_ok.jsonl `
            --out .\runs\ui_minipilot_local_optimum_blocking_modal_consent_ambiguous_search.json
        Write-Host "Running UI local-optimum disabled primary ambiguous baseline..."
        python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_disabled_primary_ambiguous_fixture.jsonl `
            --observed .\data\ui_minipilot_local_optimum_disabled_primary_ambiguous_observed_ok.jsonl `
            --out .\runs\ui_minipilot_local_optimum_disabled_primary_ambiguous_search.json
        Write-Host "Running UI local-optimum toolbar vs menu ambiguous baseline..."
        python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_toolbar_vs_menu_ambiguous_fixture.jsonl `
            --observed .\data\ui_minipilot_local_optimum_toolbar_vs_menu_ambiguous_observed_ok.jsonl `
            --out .\runs\ui_minipilot_local_optimum_toolbar_vs_menu_ambiguous_search.json
        Write-Host "Running UI local-optimum confirm then apply ambiguous baseline..."
        python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_confirm_then_apply_ambiguous_fixture.jsonl `
            --observed .\data\ui_minipilot_local_optimum_confirm_then_apply_ambiguous_observed_ok.jsonl `
            --out .\runs\ui_minipilot_local_optimum_confirm_then_apply_ambiguous_search.json
        Write-Host "Running UI local-optimum tab state reset ambiguous baseline..."
        python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_tab_state_reset_ambiguous_fixture.jsonl `
            --observed .\data\ui_minipilot_local_optimum_tab_state_reset_ambiguous_observed_ok.jsonl `
            --out .\runs\ui_minipilot_local_optimum_tab_state_reset_ambiguous_search.json
        Write-Host "Running UI local-optimum context switch ambiguous baseline..."
        python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_context_switch_ambiguous_fixture.jsonl `
            --observed .\data\ui_minipilot_local_optimum_context_switch_ambiguous_observed_ok.jsonl `
            --out .\runs\ui_minipilot_local_optimum_context_switch_ambiguous_search.json
        Write-Host "Running UI local-optimum stale tab state ambiguous baseline..."
        python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_stale_tab_state_ambiguous_fixture.jsonl `
            --observed .\data\ui_minipilot_local_optimum_stale_tab_state_ambiguous_observed_ok.jsonl `
            --out .\runs\ui_minipilot_local_optimum_stale_tab_state_ambiguous_search.json
        Write-Host "Running UI local-optimum form validation ambiguous baseline..."
        python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_form_validation_ambiguous_fixture.jsonl `
            --observed .\data\ui_minipilot_local_optimum_form_validation_ambiguous_observed_ok.jsonl `
            --out .\runs\ui_minipilot_local_optimum_form_validation_ambiguous_search.json
        Write-Host "Running UI local-optimum window focus ambiguous baseline..."
        python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_window_focus_ambiguous_fixture.jsonl `
            --observed .\data\ui_minipilot_local_optimum_window_focus_ambiguous_observed_ok.jsonl `
            --out .\runs\ui_minipilot_local_optimum_window_focus_ambiguous_search.json
        Write-Host "Running UI local-optimum checkbox gate ambiguous baseline..."
        python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_checkbox_gate_ambiguous_fixture.jsonl `
            --observed .\data\ui_minipilot_local_optimum_checkbox_gate_ambiguous_observed_ok.jsonl `
            --out .\runs\ui_minipilot_local_optimum_checkbox_gate_ambiguous_search.json
        Write-Host "Running UI local-optimum panel toggle ambiguous baseline..."
        python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_panel_toggle_ambiguous_fixture.jsonl `
            --observed .\data\ui_minipilot_local_optimum_panel_toggle_ambiguous_observed_ok.jsonl `
            --out .\runs\ui_minipilot_local_optimum_panel_toggle_ambiguous_search.json
        Write-Host "Running UI local-optimum accessibility label ambiguous baseline..."
        python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_accessibility_label_ambiguous_fixture.jsonl `
            --observed .\data\ui_minipilot_local_optimum_accessibility_label_ambiguous_observed_ok.jsonl `
            --out .\runs\ui_minipilot_local_optimum_accessibility_label_ambiguous_search.json
        Write-Host "Running UI local-optimum section path ambiguous baseline..."
        python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_section_path_ambiguous_fixture.jsonl `
            --observed .\data\ui_minipilot_local_optimum_section_path_ambiguous_observed_ok.jsonl `
            --out .\runs\ui_minipilot_local_optimum_section_path_ambiguous_search.json
        Write-Host "Running UI local-optimum section path conflict ambiguous baseline..."
        python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_section_path_conflict_ambiguous_fixture.jsonl `
            --observed .\data\ui_minipilot_local_optimum_section_path_conflict_ambiguous_observed_ok.jsonl `
            --out .\runs\ui_minipilot_local_optimum_section_path_conflict_ambiguous_search.json
        python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_blocking_modal_unprompted_confirm_ambiguous_fixture.jsonl `
            --observed .\data\ui_minipilot_local_optimum_blocking_modal_unprompted_confirm_ambiguous_observed_ok.jsonl `
            --out .\runs\ui_minipilot_local_optimum_blocking_modal_unprompted_confirm_ambiguous_search.json
        python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_destructive_confirm_ambiguous_fixture.jsonl `
            --observed .\data\ui_minipilot_local_optimum_destructive_confirm_ambiguous_observed_ok.jsonl `
            --out .\runs\ui_minipilot_local_optimum_destructive_confirm_ambiguous_search.json
        python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_role_conflict_ambiguous_fixture.jsonl `
            --observed .\data\ui_minipilot_local_optimum_role_conflict_ambiguous_observed_ok.jsonl `
            --out .\runs\ui_minipilot_local_optimum_role_conflict_ambiguous_search.json
    }
    if (-not $SkipVariants) {
        $releaseDir = "runs\\release_gates"
        $releaseDistillation = Join-Path $releaseDir "ui_local_optimum_distillation.json"
        $report = $null
        $distillationPath = $releaseDistillation
        $reuseVariants = $false
        if ($FastLocal -and (Test-ArtifactFresh -Path $releaseDistillation -MaxAgeMinutes $ReuseUiBaselinesMaxAgeMinutes)) {
            $report = Read-JsonObject -Path $releaseDistillation
            if ($report -and $report.holdout_name -and $report.holdout_name -eq $RequiredVariantsHoldout) {
                $reuseVariants = $true
                Write-Host ("[FAST] Reusing UI local-optimum distillation report ({0}, max_age={1}m)." -f $releaseDistillation, $ReuseUiBaselinesMaxAgeMinutes)
            } else {
                $report = $null
            }
        }
        if (-not $reuseVariants) {
            $variantsOutRoot = "runs\\ui_local_optimum_variants_$stamp"
            Write-Host "Running UI local-optimum variants + distillation report..."
            $variantsLog = Join-Path $releaseLogsDir "ui_local_optimum_variants.log"
            .\scripts\run_ui_local_optimum_variants.ps1 `
                -OutRoot $variantsOutRoot `
                -Seeds $VariantsSeeds `
                -HoldoutName $resolvedHoldout `
                -FuzzVariants $VariantsFuzzVariants `
                -FuzzSeed $VariantsFuzzSeed *> $variantsLog
            if ($LASTEXITCODE -ne 0) {
                Write-Error "UI local-optimum variants failed. See $variantsLog"
                if (Test-Path $variantsLog) { Get-Content $variantsLog -Tail 60 | Out-Host }
                exit $LASTEXITCODE
            }
            Write-Host "UI local-optimum variants complete (log: $variantsLog)"
            $distillationPath = Join-Path $variantsOutRoot "distillation_report.json"
            if (Test-Path $distillationPath) {
                New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
                Copy-Item -Path $distillationPath -Destination $releaseDistillation -Force
                $report = $null
                try {
                    $report = Get-Content $releaseDistillation -Raw | ConvertFrom-Json
                } catch {
                    Write-Error "Failed to parse ui_local_optimum_distillation.json after copy."
                    exit 1
                }
            }
        }
        if ($report) {
            if (-not $report.holdout_name) {
                Write-Error "ui_local_optimum_distillation.json missing holdout_name."
                exit 1
            }
            if ($report.holdout_name -ne $RequiredVariantsHoldout) {
                Write-Error ("ui_local_optimum_distillation.json holdout_name '{0}' does not match required '{1}'." -f $report.holdout_name, $RequiredVariantsHoldout)
                exit 1
            }
            if ($AutoCurriculum) {
                try {
                    $choice = Get-NextHoldoutFromReport -Report $report -GapMin $AutoCurriculumGapMin -SolvedMin $AutoCurriculumSolvedMin -FallbackHoldout $resolvedHoldout
                    New-Item -ItemType Directory -Path (Split-Path $AutoCurriculumStatePath) -Force | Out-Null
                    [pscustomobject]@{
                        used_holdout = $resolvedHoldout
                        next_holdout = $choice.holdout
                        reason = $choice.reason
                        exhausted = $choice.exhausted
                        gap_min = $AutoCurriculumGapMin
                        solved_min = $AutoCurriculumSolvedMin
                        source_report = $distillationPath
                        updated_at = (Get-Date -Format "s")
                    } | ConvertTo-Json -Depth 5 | Set-Content -Path $AutoCurriculumStatePath -Encoding UTF8
                    if ($choice.exhausted) {
                        Write-Host "AutoCurriculum: no oracle gap found in current report (curriculum exhausted)."
                    } else {
                        Write-Host ("AutoCurriculum next holdout: {0} ({1})" -f $choice.holdout, $choice.reason)
                    }
                } catch {
                    Write-Host "AutoCurriculum: failed to parse distillation report for next holdout."
                }
            }
        }
    }
    if ($RunDriftHoldoutGate) {
        if (-not $ModelPath) {
            Write-Error "Set -ModelPath or GOLDEVIDENCEBENCH_MODEL before running the drift holdout gate."
            exit 1
        }
        Write-Host ("Running drift holdout gate (holdout={0})..." -f $DriftHoldoutName)
        .\scripts\run_drift_holdout_gate.ps1 -ModelPath $ModelPath -HoldoutName $DriftHoldoutName
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Drift holdout gate failed."
            exit 1
        }
    }
    $gateRequiresModelPath = -not ($GateAdapter -like "*llama_server_adapter*")
    if ($gateRequiresModelPath -and -not $ModelPath) {
        Write-Error ("Set -ModelPath or GOLDEVIDENCEBENCH_MODEL before running the bad actor holdout gate with adapter '{0}'." -f $GateAdapter)
        exit 1
    }
    if ($BadActorHoldoutId) {
        Write-Host ("Running bad actor holdout gate (holdout={0})..." -f $BadActorHoldoutId)
    } else {
        Write-Host "Running bad actor holdout gate..."
    }
    .\scripts\run_bad_actor_holdout_gate.ps1 `
        -ModelPath $ModelPath `
        -Adapter $GateAdapter `
        -HoldoutListPath $BadActorHoldoutListPath `
        -HoldoutId $BadActorHoldoutId
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Bad actor holdout gate failed."
        exit 1
    }

    Write-Host "Running persona invariance release gate..."
    $personaGateDir = "runs\\release_gates\\persona_invariance"
    New-Item -ItemType Directory -Path $personaGateDir -Force | Out-Null
    $personaGateSummaryPath = Join-Path $personaGateDir "summary.json"
    $personaGateRowsPath = Join-Path $personaGateDir "rows.jsonl"
    $personaInputs = @(
        "compression_families=runs\\compression_reliability_latest.json",
        "compression_roundtrip_generalization=runs\\compression_roundtrip_generalization_reliability_latest.json",
        "myopic_planning_traps=runs\\myopic_planning_traps_reliability_latest.json",
        "referential_indexing_suite=runs\\referential_indexing_suite_reliability_latest.json",
        "novel_continuity=runs\\novel_continuity_reliability_latest.json",
        "novel_continuity_long_horizon=runs\\novel_continuity_long_horizon_reliability_latest.json",
        "epistemic_calibration_suite=runs\\epistemic_calibration_suite_reliability_latest.json",
        "authority_under_interference=runs\\authority_under_interference_reliability_latest.json",
        "authority_under_interference_hardening=runs\\authority_under_interference_hardening_reliability_latest.json",
        "rpa_mode_switch=runs\\rpa_mode_switch_reliability_latest.json",
        "intent_spec_layer=runs\\intent_spec_layer_reliability_latest.json",
        "noise_escalation=runs\\noise_escalation_reliability_latest.json",
        "implication_coherence=runs\\implication_coherence_reliability_latest.json",
        "agency_preserving_substitution=runs\\agency_preserving_substitution_reliability_latest.json"
    )
    python .\scripts\check_persona_invariance_gate.py `
        --inputs $personaInputs `
        --out $personaGateSummaryPath `
        --rows-out $personaGateRowsPath
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Persona invariance gate failed (persona_contract_drift)."
        exit 1
    }
    .\scripts\set_latest_pointer.ps1 -RunDir $personaGateSummaryPath -PointerPath "runs\\latest_persona_invariance_gate" | Out-Host

    $thresholdHistoryPassCount = 0
    $thresholdHistoryRejectedCount = 0
    $thresholdHistoryNowUtc = [datetimeoffset]::UtcNow
    $releaseDirResolvedForThresholds = ""
    try {
        $releaseDirResolvedForThresholds = (Resolve-Path $ReleaseRunDir).Path
    } catch {
        $releaseDirResolvedForThresholds = $ReleaseRunDir
    }
    $thresholdReleaseDirs = @(Get-ChildItem -Path "runs" -Directory -Filter "release_check_*" -ErrorAction SilentlyContinue)
    foreach ($dir in $thresholdReleaseDirs) {
        if ($dir.FullName -eq $releaseDirResolvedForThresholds) {
            continue
        }
        $snapshotPath = Join-Path $dir.FullName "release_quality_snapshot.json"
        if (-not (Test-Path $snapshotPath)) {
            continue
        }
        $snapshot = Read-JsonObject -Path $snapshotPath
        if (-not $snapshot) {
            continue
        }
        $snapshotQuality = Get-ReleaseSnapshotQualityAssessment `
            -Snapshot $snapshot `
            -SnapshotPath $snapshotPath `
            -NowUtc $thresholdHistoryNowUtc `
            -MaxSnapshotAgeDays $TrendMaxSnapshotAgeDays `
            -MinScenarioCount $MinMemorySensitivityScenarioCount `
            -MinMaxInvalidRate $MinMemorySensitivityMaxInvalidRate `
            -MinMaxActionsBlocked $MinMemorySensitivityMaxActionsBlocked `
            -MinMaxTotal $MinMemorySensitivityMaxTotal `
            -MinDistinctTagCount $MinMemorySensitivityDistinctTagCount `
            -MinDistinctReasonCount $MinMemorySensitivityDistinctReasonCount
        if (-not $snapshotQuality.eligible) {
            $thresholdHistoryRejectedCount += 1
            continue
        }
        $thresholdHistoryPassCount += 1
    }
    $strictOptionalThresholdMetricsActive = $false
    if ($StrictOptionalThresholdMetrics) {
        if (($thresholdHistoryPassCount + 1) -ge $TrendMinHistory) {
            $strictOptionalThresholdMetricsActive = $true
            Write-Host "[ENFORCE] threshold optional-metric strict mode enabled (quality-qualified history)."
        } else {
            Write-Host ("[BOOTSTRAP] threshold optional-metric strict mode disabled ({0}/{1} quality snapshots including current; rejected={2}; max_age_days={3})." -f `
                ($thresholdHistoryPassCount + 1), $TrendMinHistory, $thresholdHistoryRejectedCount, $TrendMaxSnapshotAgeDays)
        }
    } else {
        Write-Host "[WARN] threshold optional-metric strict mode disabled by parameter."
    }
    $thresholdEvalPath = Join-Path $ReleaseRunDir "thresholds_eval.json"
    $thresholdArgs = @(
        ".\scripts\check_thresholds.py",
        "--config", ".\configs\usecase_checks.json",
        "--quiet-passes",
        "--out", $thresholdEvalPath
    )
    if ($strictOptionalThresholdMetricsActive) {
        $thresholdArgs += "--strict-optional"
    }
    python @thresholdArgs
    $exitCode = $LASTEXITCODE
    $optionalMissingNaCount = 0
    $thresholdErrorCount = $null
    if (Test-Path $thresholdEvalPath) {
        $thresholdEvalPayload = Read-JsonObject -Path $thresholdEvalPath
        if ($thresholdEvalPayload) {
            $thresholdErrorCount = ConvertTo-NullableDouble $thresholdEvalPayload.error_count
            $thresholdIssues = @($thresholdEvalPayload.issues)
            $optionalMissingNaCount = @(
                $thresholdIssues | Where-Object {
                    "$($_.status)" -eq "not_applicable" -and "$($_.message)" -like "*optional metric missing*"
                }
            ).Count
            if ($optionalMissingNaCount -gt 0 -and -not $strictOptionalThresholdMetricsActive) {
                Write-Warning ("Threshold checks in bootstrap mode still have {0} optional-missing N/A entries." -f $optionalMissingNaCount)
            }
        }
    }
    $optionalMetricInventoryPath = Join-Path $ReleaseRunDir "optional_metric_inventory.json"
    $thresholdConfigPayload = Read-JsonObject -Path "configs\\usecase_checks.json"
    $optionalMetricExemptions = @()
    if ($thresholdConfigPayload -and $thresholdConfigPayload.checks) {
        foreach ($check in @($thresholdConfigPayload.checks)) {
            $checkId = "$($check.id)"
            $summaryPath = "$($check.summary_path)"
            $severity = "$($check.severity)"
            foreach ($metric in @($check.metrics)) {
                if (-not $metric) {
                    continue
                }
                $metricPath = "$($metric.path)"
                if ([string]::IsNullOrWhiteSpace($metricPath)) {
                    continue
                }
                $metricRequired = $true
                if ($metric.PSObject.Properties.Name -contains "required") {
                    try {
                        $metricRequired = [bool]$metric.required
                    } catch {
                        $metricRequired = $true
                    }
                } elseif ($metric.PSObject.Properties.Name -contains "allow_missing") {
                    try {
                        $metricRequired = -not [bool]$metric.allow_missing
                    } catch {
                        $metricRequired = $true
                    }
                }
                if ($metricRequired) {
                    continue
                }
                $strictOptionalMissing = $true
                if ($metric.PSObject.Properties.Name -contains "strict_optional_missing") {
                    try {
                        $strictOptionalMissing = [bool]$metric.strict_optional_missing
                    } catch {
                        $strictOptionalMissing = $true
                    }
                }
                if ($strictOptionalMissing) {
                    continue
                }
                $key = "{0}::{1}" -f $checkId, $metricPath
                $optionalMetricExemptions += [ordered]@{
                    key = $key
                    check_id = $checkId
                    metric_path = $metricPath
                    severity = $severity
                    summary_path = $summaryPath
                }
            }
        }
    }
    $optionalMetricExemptions = @($optionalMetricExemptions | Sort-Object key)
    $currentExemptionKeys = @($optionalMetricExemptions | ForEach-Object { "$($_.key)" })

    $priorInventoryPointerPath = "runs\\latest_optional_metric_inventory"
    $priorInventoryPath = Resolve-PointerTarget -PointerPath $priorInventoryPointerPath
    $priorExemptionKeys = @()
    $hasPriorInventory = $false
    if (-not [string]::IsNullOrWhiteSpace($priorInventoryPath) -and (Test-Path $priorInventoryPath)) {
        $priorInventoryPayload = Read-JsonObject -Path $priorInventoryPath
        if ($priorInventoryPayload) {
            $hasPriorInventory = $true
            if ($priorInventoryPayload.exemption_keys) {
                $priorExemptionKeys = @($priorInventoryPayload.exemption_keys | ForEach-Object { "$_".Trim() } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
            } elseif ($priorInventoryPayload.exemptions) {
                $priorExemptionKeys = @($priorInventoryPayload.exemptions | ForEach-Object { "$($_.key)".Trim() } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
            }
        }
    }
    $newExemptionKeys = @($currentExemptionKeys | Where-Object { $priorExemptionKeys -notcontains $_ })

    $allowlistPayload = Read-JsonObject -Path $OptionalMetricExemptionsAllowlistPath
    $allowlistedNewExemptionKeys = @()
    if ($allowlistPayload -and $allowlistPayload.allowed_new_exemptions) {
        foreach ($entry in @($allowlistPayload.allowed_new_exemptions)) {
            if ($entry -is [string]) {
                $candidate = "$entry".Trim()
                if (-not [string]::IsNullOrWhiteSpace($candidate)) {
                    $allowlistedNewExemptionKeys += $candidate
                }
                continue
            }
            if ($entry.PSObject.Properties.Name -contains "key") {
                $candidate = "$($entry.key)".Trim()
                if (-not [string]::IsNullOrWhiteSpace($candidate)) {
                    $allowlistedNewExemptionKeys += $candidate
                }
            }
        }
    }
    $allowlistedNewExemptionKeys = @($allowlistedNewExemptionKeys | Sort-Object -Unique)
    $unapprovedNewExemptionKeys = @($newExemptionKeys | Where-Object { $allowlistedNewExemptionKeys -notcontains $_ })

    if ($hasPriorInventory -and $unapprovedNewExemptionKeys.Count -gt 0) {
        Write-Error ("Optional-metric exemption governance failed: unapproved new exemptions detected -> {0}" -f ($unapprovedNewExemptionKeys -join ", "))
        exit 1
    }
    if (-not $hasPriorInventory) {
        Write-Host "[BOOTSTRAP] optional-metric exemption inventory baseline missing; new exemptions are not yet enforceable."
    } elseif ($newExemptionKeys.Count -gt 0) {
        Write-Host ("[PASS] optional-metric exemption governance: all {0} new exemptions approved." -f $newExemptionKeys.Count)
    } else {
        Write-Host "[PASS] optional-metric exemption governance: no new exemptions."
    }

    $optionalMetricInventoryPayload = [ordered]@{
        benchmark = "optional_metric_inventory"
        generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        strict_optional_mode_active = [bool]$strictOptionalThresholdMetricsActive
        has_prior_inventory = [bool]$hasPriorInventory
        prior_inventory_path = $priorInventoryPath
        threshold_error_count = $thresholdErrorCount
        optional_missing_na_count = $optionalMissingNaCount
        exemption_count = $currentExemptionKeys.Count
        exemption_keys = $currentExemptionKeys
        new_exemption_keys = $newExemptionKeys
        allowlisted_new_exemption_keys = $allowlistedNewExemptionKeys
        unapproved_new_exemption_keys = $unapprovedNewExemptionKeys
        exemptions = $optionalMetricExemptions
    }
    $optionalMetricInventoryPayload | ConvertTo-Json -Depth 7 | Set-Content -Path $optionalMetricInventoryPath -Encoding UTF8
    .\scripts\set_latest_pointer.ps1 -RunDir $optionalMetricInventoryPath -PointerPath "runs\\latest_optional_metric_inventory" | Out-Host
    if ($exitCode -ne 0) {
        $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $artifactRoot = "runs\\ui_gate_artifacts_$stamp"
        New-Item -ItemType Directory -Path $artifactRoot -Force | Out-Null
        $pairs = @(
            @{
                Name = "local_optimum"
                Fixture = "data\\ui_minipilot_local_optimum_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_search.json"
            },
            @{
                Name = "local_optimum_delayed_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_delayed_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_delayed_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_blocking_modal_unmentioned_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_blocking_modal_unmentioned_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_blocking_modal_unmentioned_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_blocking_modal_unmentioned_blocked_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_blocking_modal_unmentioned_blocked_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_blocking_modal_unmentioned_blocked_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_blocking_modal_required_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_blocking_modal_required_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_blocking_modal_required_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_blocking_modal_permission_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_blocking_modal_permission_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_blocking_modal_permission_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_blocking_modal_consent_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_blocking_modal_consent_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_blocking_modal_consent_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_disabled_primary_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_disabled_primary_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_disabled_primary_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_toolbar_vs_menu_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_toolbar_vs_menu_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_toolbar_vs_menu_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_confirm_then_apply_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_confirm_then_apply_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_confirm_then_apply_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_tab_state_reset_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_tab_state_reset_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_tab_state_reset_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_context_switch_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_context_switch_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_context_switch_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_stale_tab_state_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_stale_tab_state_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_stale_tab_state_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_form_validation_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_form_validation_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_form_validation_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_window_focus_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_window_focus_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_window_focus_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_checkbox_gate_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_checkbox_gate_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_checkbox_gate_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_panel_toggle_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_panel_toggle_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_panel_toggle_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_accessibility_label_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_accessibility_label_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_accessibility_label_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_section_path_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_section_path_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_section_path_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_section_path_conflict_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_section_path_conflict_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_section_path_conflict_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_blocking_modal_unprompted_confirm_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_blocking_modal_unprompted_confirm_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_blocking_modal_unprompted_confirm_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_destructive_confirm_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_destructive_confirm_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_destructive_confirm_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_role_conflict_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_role_conflict_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_role_conflict_ambiguous_search.json"
            }
        )
        foreach ($pair in $pairs) {
            if (-not (Test-Path $pair.Baseline)) {
                Write-Host "Skip artifact dump (missing baseline): $($pair.Baseline)"
                continue
            }
            $outDir = Join-Path $artifactRoot $pair.Name
            python .\scripts\dump_ui_baseline_artifacts.py `
                --fixture $pair.Fixture `
                --baseline $pair.Baseline `
                --out-dir $outDir
        }
    }
    if ($exitCode -ne 0) {
        Write-Error "Release threshold checks failed."
        exit 1
    }
    if (-not $SkipReliabilitySignal) {
        Write-Host "Running unified reliability signal gate..."
        $reliabilityParams = @{}
        if (-not $SkipRequireControlFamilies) {
            $reliabilityParams.RequireRPAModeSwitch = $true
            $reliabilityParams.RequireIntentSpec = $true
            $reliabilityParams.RequireNoiseEscalation = $true
            $reliabilityParams.RequireImplicationCoherence = $true
            $reliabilityParams.RequireAgencyPreservingSubstitution = $true
        } else {
            Write-Warning "SkipRequireControlFamilies enabled: unified reliability gate will not require RPA/intent/noise/implication/agency families."
        }
        if (-not $SkipDerivedScoreFloors) {
            $reliabilityParams.MinReasoningScore = $MinReleaseReasoningScore
            $reliabilityParams.MinPlanningScore = $MinReleasePlanningScore
            $reliabilityParams.MinIntelligenceIndex = $MinReleaseIntelligenceIndex
            $reliabilityParams.MinImplicationCoherenceCore = $MinReleaseImplicationCoherenceCore
            $reliabilityParams.MinAgencyPreservationCore = $MinReleaseAgencyPreservationCore
        } else {
            Write-Warning "SkipDerivedScoreFloors enabled: unified reliability gate will not enforce reasoning/planning/intelligence or implication/agency component floors."
        }
        .\scripts\check_reliability_signal.ps1 @reliabilityParams
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Unified reliability signal gate failed."
            exit 1
        }
        if (Test-Path "runs\\reliability_signal_latest.json") {
            .\scripts\set_latest_pointer.ps1 -RunDir "runs\\reliability_signal_latest.json" -PointerPath "runs\\latest_reliability_signal" | Out-Host
        }
        $reliabilitySignalPath = "runs\\reliability_signal_latest.json"
        $reliabilitySignalPayload = Read-JsonObject -Path $reliabilitySignalPath
        if (-not $reliabilitySignalPayload) {
            Write-Error "Unable to parse reliability signal payload: $reliabilitySignalPath"
            exit 1
        }
        $currentReasoningScore = ConvertTo-NullableDouble $reliabilitySignalPayload.derived.reasoning_score
        $currentImplicationCore = ConvertTo-NullableDouble $reliabilitySignalPayload.derived.reasoning_components.implication_coherence_core
        $currentAgencyCore = ConvertTo-NullableDouble $reliabilitySignalPayload.derived.reasoning_components.agency_preservation_core
        if ($null -eq $currentReasoningScore -or $null -eq $currentImplicationCore -or $null -eq $currentAgencyCore) {
            Write-Error "Reliability signal missing required derived metrics for trend guard."
            exit 1
        }
        if ($null -eq $instructionOverrideTokensPerQP90 -or $null -eq $instructionOverrideWallPerQP90) {
            Write-Error "Instruction override efficiency metrics are unavailable for release cost gating."
            exit 1
        }

        $utilityBurdenDelta = $null
        $utilityFalseCommitImprovement = $null
        $utilityCorrectionImprovement = $null
        $utilityBurdenWarnTriggered = $false
        $frontierCoverageRate = $null
        $frontierReductionRate = $null

        if (-not $SkipRealWorldUtilityEval) {
            Write-Host "Running real-world utility A/B gate..."
            $utilityEvalPath = "runs\\real_world_utility_eval_latest.json"
            $reuseUtilityEval = $false
            if ($FastLocal -and (Test-ArtifactFresh -Path $utilityEvalPath -MaxAgeMinutes $ReuseUtilityEvalMaxAgeMinutes)) {
                $reuseUtilityEval = $true
                Write-Host ("[FAST] Reusing real-world utility eval artifact ({0}, max_age={1}m)." -f $utilityEvalPath, $ReuseUtilityEvalMaxAgeMinutes)
            }
            if (-not $reuseUtilityEval) {
                .\scripts\run_real_world_utility_eval.ps1 -Adapter $GateAdapter -Protocol "closed_book"
                if ($LASTEXITCODE -ne 0) {
                    Write-Error "Real-world utility A/B gate failed."
                    exit 1
                }
            }
            if (-not (Test-Path $utilityEvalPath)) {
                Write-Error "Missing real-world utility artifact: runs\\real_world_utility_eval_latest.json"
                exit 1
            }
            $utilityPayload = Read-JsonObject -Path $utilityEvalPath
            if (-not $utilityPayload) {
                Write-Error "Unable to parse real-world utility payload: runs\\real_world_utility_eval_latest.json"
                exit 1
            }
            $utilityBurdenDelta = ConvertTo-NullableDouble $utilityPayload.comparison.clarification_burden_delta
            if ($null -eq $utilityBurdenDelta) {
                $baselineBurden = ConvertTo-NullableDouble $utilityPayload.baseline.clarification_burden
                $controlledBurden = ConvertTo-NullableDouble $utilityPayload.controlled.clarification_burden
                if ($null -ne $baselineBurden -and $null -ne $controlledBurden) {
                    $utilityBurdenDelta = $controlledBurden - $baselineBurden
                }
            }
            if ($null -eq $utilityBurdenDelta) {
                Write-Error "Utility burden cap gate: missing clarification burden delta in runs\\real_world_utility_eval_latest.json"
                exit 1
            }
            $utilityFalseCommitImprovement = ConvertTo-NullableDouble $utilityPayload.pass_inputs.false_commit_improvement
            if ($null -eq $utilityFalseCommitImprovement) {
                $baselineFalseCommit = ConvertTo-NullableDouble $utilityPayload.baseline.false_commit_rate
                $controlledFalseCommit = ConvertTo-NullableDouble $utilityPayload.controlled.false_commit_rate
                if ($null -ne $baselineFalseCommit -and $null -ne $controlledFalseCommit) {
                    $utilityFalseCommitImprovement = $baselineFalseCommit - $controlledFalseCommit
                }
            }
            $utilityCorrectionImprovement = ConvertTo-NullableDouble $utilityPayload.pass_inputs.correction_improvement
            if ($null -eq $utilityCorrectionImprovement) {
                $baselineCorrection = ConvertTo-NullableDouble $utilityPayload.baseline.correction_turns_per_task
                $controlledCorrection = ConvertTo-NullableDouble $utilityPayload.controlled.correction_turns_per_task
                if ($null -ne $baselineCorrection -and $null -ne $controlledCorrection) {
                    $utilityCorrectionImprovement = $baselineCorrection - $controlledCorrection
                }
            }
            if ($utilityBurdenDelta -gt $MaxReleaseUtilityBurdenDelta) {
                Write-Error ("Utility burden cap gate failed: burden_delta={0:N6} > cap={1:N6}" -f $utilityBurdenDelta, $MaxReleaseUtilityBurdenDelta)
                exit 1
            }
            Write-Host ("[PASS] utility_burden_delta={0:N6} <= {1:N6}" -f $utilityBurdenDelta, $MaxReleaseUtilityBurdenDelta)
            if ($utilityBurdenDelta -gt $WarnReleaseUtilityBurdenDelta) {
                $utilityBurdenCompensated = $false
                if ($null -ne $utilityFalseCommitImprovement -and $null -ne $utilityCorrectionImprovement) {
                    $utilityBurdenCompensated = `
                        ($utilityFalseCommitImprovement -ge $MinUtilityWarningFalseCommitImprovement) -and `
                        ($utilityCorrectionImprovement -ge $MinUtilityWarningCorrectionImprovement)
                }
                if ($utilityBurdenCompensated) {
                    Write-Host ("[INFO] Utility burden in warning zone is compensated by gains: false_commit_improvement={0:N6} (>= {1:N6}), correction_improvement={2:N6} (>= {3:N6})" -f `
                        $utilityFalseCommitImprovement, $MinUtilityWarningFalseCommitImprovement, $utilityCorrectionImprovement, $MinUtilityWarningCorrectionImprovement)
                } else {
                    $utilityBurdenWarnTriggered = $true
                    Write-Warning ("Utility burden warning zone: burden_delta={0:N6} > warn={1:N6}" -f $utilityBurdenDelta, $WarnReleaseUtilityBurdenDelta)
                    $releaseRiskWarnings.Add("utility_burden_warning_zone")
                }
            }
        } else {
            Write-Host "Skipping real-world utility A/B gate (-SkipRealWorldUtilityEval)."
        }

        Write-Host "Building codex compatibility artifacts..."
        python .\scripts\build_codex_compat_report.py --out-dir "runs/codex_compat" --report-path "docs/CODEX_COMPAT_REPORT.md"
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Codex compatibility artifact build failed."
            exit 1
        }

        $compatArtifacts = @(
            "runs\\codex_compat\\family_matrix.json",
            "runs\\codex_compat\\orthogonality_matrix.json",
            "runs\\codex_compat\\rpa_ablation_report.json",
            "runs\\codex_compat\\regression_frontier.json",
            "runs\\codex_compat\\scaffold_backlog.json",
            "docs\\CODEX_COMPAT_REPORT.md"
        )
        foreach ($artifact in $compatArtifacts) {
            if (-not (Test-Path $artifact)) {
                Write-Error "Missing codex compatibility artifact: $artifact"
                exit 1
            }
        }
        $regressionFrontierPath = "runs\\codex_compat\\regression_frontier.json"
        $regressionFrontierPayload = Read-JsonObject -Path $regressionFrontierPath
        if (-not $regressionFrontierPayload) {
            Write-Error "Unable to parse regression frontier payload: $regressionFrontierPath"
            exit 1
        }
        $frontierCoverageRate = ConvertTo-NullableDouble $regressionFrontierPayload.coverage.required_tag_coverage_rate
        $frontierReductionRate = ConvertTo-NullableDouble $regressionFrontierPayload.reduction_rate
        if ($null -eq $frontierCoverageRate -or $null -eq $frontierReductionRate) {
            Write-Error "Regression frontier gate: missing coverage/reduction metrics."
            exit 1
        }
        if ($frontierCoverageRate -lt $MinRegressionFrontierCoverage) {
            Write-Error ("Regression frontier coverage gate failed: coverage={0:N6} < floor={1:N6}" -f $frontierCoverageRate, $MinRegressionFrontierCoverage)
            exit 1
        }
        if ($frontierReductionRate -lt $MinRegressionFrontierReduction) {
            Write-Error ("Regression frontier reduction gate failed: reduction={0:N6} < floor={1:N6}" -f $frontierReductionRate, $MinRegressionFrontierReduction)
            exit 1
        }
        Write-Host ("[PASS] regression_frontier.coverage={0:N6} >= {1:N6}" -f $frontierCoverageRate, $MinRegressionFrontierCoverage)
        Write-Host ("[PASS] regression_frontier.reduction={0:N6} >= {1:N6}" -f $frontierReductionRate, $MinRegressionFrontierReduction)

        .\scripts\set_latest_pointer.ps1 -RunDir "runs\\codex_compat\\family_matrix.json" -PointerPath "runs\\latest_codex_compat_family_matrix" | Out-Host
        .\scripts\set_latest_pointer.ps1 -RunDir "runs\\codex_compat\\orthogonality_matrix.json" -PointerPath "runs\\latest_codex_compat_orthogonality_matrix" | Out-Host
        .\scripts\set_latest_pointer.ps1 -RunDir "runs\\codex_compat\\rpa_ablation_report.json" -PointerPath "runs\\latest_codex_compat_rpa_ablation_report" | Out-Host
        .\scripts\set_latest_pointer.ps1 -RunDir "runs\\codex_compat\\regression_frontier.json" -PointerPath "runs\\latest_codex_compat_regression_frontier" | Out-Host
        .\scripts\set_latest_pointer.ps1 -RunDir "runs\\codex_compat\\scaffold_backlog.json" -PointerPath "runs\\latest_codex_compat_scaffold_backlog" | Out-Host
        .\scripts\set_latest_pointer.ps1 -RunDir "docs\\CODEX_COMPAT_REPORT.md" -PointerPath "runs\\latest_codex_compat_report" | Out-Host

        Write-Host "Building codex next-step report..."
        python .\scripts\build_codex_next_step_report.py
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Codex next-step report build failed."
            exit 1
        }
        if (-not (Test-Path "runs\\codex_next_step_report.json")) {
            Write-Error "Missing codex next-step report artifact: runs\\codex_next_step_report.json"
            exit 1
        }
        .\scripts\set_latest_pointer.ps1 -RunDir "runs\\codex_next_step_report.json" -PointerPath "runs\\latest_codex_next_step_report" | Out-Host

        $releaseDirResolved = ""
        try {
            $releaseDirResolved = (Resolve-Path $ReleaseRunDir).Path
        } catch {
            $releaseDirResolved = $ReleaseRunDir
        }

        $priorSnapshots = @()
        $priorWarningSnapshots = @()
        $priorSnapshotRejections = @()
        $warningDebtSchemaVersion = 3
        $trendNowUtc = [datetimeoffset]::UtcNow
        $releaseDirs = @(Get-ChildItem -Path "runs" -Directory -Filter "release_check_*" -ErrorAction SilentlyContinue)
        foreach ($dir in $releaseDirs) {
            $snapshotPath = Join-Path $dir.FullName "release_quality_snapshot.json"
            if (-not (Test-Path $snapshotPath)) {
                continue
            }
            if ($dir.FullName -eq $releaseDirResolved) {
                continue
            }
            $snapshot = Read-JsonObject -Path $snapshotPath
            if (-not $snapshot) {
                continue
            }
            $snapshotQuality = Get-ReleaseSnapshotQualityAssessment `
                -Snapshot $snapshot `
                -SnapshotPath $snapshotPath `
                -NowUtc $trendNowUtc `
                -MaxSnapshotAgeDays $TrendMaxSnapshotAgeDays `
                -MinScenarioCount $MinMemorySensitivityScenarioCount `
                -MinMaxInvalidRate $MinMemorySensitivityMaxInvalidRate `
                -MinMaxActionsBlocked $MinMemorySensitivityMaxActionsBlocked `
                -MinMaxTotal $MinMemorySensitivityMaxTotal `
                -MinDistinctTagCount $MinMemorySensitivityDistinctTagCount `
                -MinDistinctReasonCount $MinMemorySensitivityDistinctReasonCount
            $warningSortKey = $null
            $snapshotWarningSchemaVersion = $null
            if ($snapshotQuality.timestamp_utc) {
                try {
                    $warningSortKey = [datetimeoffset]::Parse($snapshotQuality.timestamp_utc)
                } catch {
                    $warningSortKey = $null
                }
            }
            if ($null -ne $warningSortKey) {
                $snapshotWarningSchemaVersion = ConvertTo-NullableDouble $snapshot.metrics.warning_debt_schema_version
                if ($null -eq $snapshotWarningSchemaVersion) {
                    $snapshotWarningSchemaVersion = 1
                }
                if ([int]$snapshotWarningSchemaVersion -lt $warningDebtSchemaVersion) {
                    # Ignore legacy warning snapshots produced before current warning semantics.
                    $snapshotWarningSchemaVersion = $null
                }
            }
            if ($null -ne $warningSortKey -and $null -ne $snapshotWarningSchemaVersion) {
                $snapshotInstructionOverrideWarn = $false
                if ($snapshot.gates -and ($snapshot.gates.PSObject.Properties.Name -contains "instruction_override_cost_warning_triggered")) {
                    try {
                        $snapshotInstructionOverrideWarn = [bool]$snapshot.gates.instruction_override_cost_warning_triggered
                    } catch {
                        $snapshotInstructionOverrideWarn = $false
                    }
                }
                $snapshotUtilityBurdenWarn = $false
                if ($snapshot.gates -and ($snapshot.gates.PSObject.Properties.Name -contains "utility_burden_warning_triggered")) {
                    try {
                        $snapshotUtilityBurdenWarn = [bool]$snapshot.gates.utility_burden_warning_triggered
                    } catch {
                        $snapshotUtilityBurdenWarn = $false
                    }
                }
                $priorWarningSnapshots += [pscustomobject]@{
                    path = $snapshotPath
                    sort_key = $warningSortKey
                    warning_debt_schema_version = [int]$snapshotWarningSchemaVersion
                    instruction_override_cost_warning_triggered = $snapshotInstructionOverrideWarn
                    utility_burden_warning_triggered = $snapshotUtilityBurdenWarn
                }
            }
            if (-not $snapshotQuality.eligible) {
                $priorSnapshotRejections += [pscustomobject]@{
                    path = $snapshotPath
                    reasons = @($snapshotQuality.reasons)
                }
                continue
            }
            $snapshotReasoning = ConvertTo-NullableDouble $snapshot.metrics.derived_reasoning_score
            $snapshotImplication = ConvertTo-NullableDouble $snapshot.metrics.derived_implication_coherence_core
            $snapshotAgency = ConvertTo-NullableDouble $snapshot.metrics.derived_agency_preservation_core
            if ($null -eq $snapshotReasoning -or $null -eq $snapshotImplication -or $null -eq $snapshotAgency) {
                $priorSnapshotRejections += [pscustomobject]@{
                    path = $snapshotPath
                    reasons = @("derived_metric_missing")
                }
                continue
            }
            $snapshotTokensP90 = ConvertTo-NullableDouble $snapshot.metrics.instruction_override_tokens_per_q_p90
            $snapshotWallP90 = ConvertTo-NullableDouble $snapshot.metrics.instruction_override_wall_s_per_q_p90
            $sortKey = $null
            if ($snapshotQuality.timestamp_utc) {
                try {
                    $sortKey = [datetimeoffset]::Parse($snapshotQuality.timestamp_utc)
                } catch {
                    $sortKey = $null
                }
            }
            if ($null -eq $sortKey) {
                $priorSnapshotRejections += [pscustomobject]@{
                    path = $snapshotPath
                    reasons = @("timestamp_parse_failed")
                }
                continue
            }
            $priorSnapshots += [pscustomobject]@{
                path = $snapshotPath
                sort_key = $sortKey
                reasoning_score = [double]$snapshotReasoning
                implication_core = [double]$snapshotImplication
                agency_core = [double]$snapshotAgency
                tokens_per_q_p90 = $snapshotTokensP90
                wall_s_per_q_p90 = $snapshotWallP90
                quality_reasons = @($snapshotQuality.reasons)
            }
        }
        $maxPriorSamples = [math]::Max($TrendReleaseWindow - 1, 1)
        $priorSnapshots = @($priorSnapshots | Sort-Object sort_key | Select-Object -Last $maxPriorSamples)
        $currentSnapshotQualityReasons = @()
        if ($releaseIntegrityWarnings.Count -gt 0) {
            $currentSnapshotQualityReasons += "integrity_warnings_present"
        }
        if ($memoryTotal -lt $MinMemoryVerifyTotal) { $currentSnapshotQualityReasons += "memory_total_below_floor" }
        if ($memoryUseRate -lt $MinMemoryVerifyUseRate) { $currentSnapshotQualityReasons += "memory_use_rate_below_floor" }
        if ($memoryVerifiedRate -lt $MinMemoryVerifyVerifiedRate) { $currentSnapshotQualityReasons += "memory_verified_rate_below_floor" }
        if ($memoryInvalidRate -gt $MaxMemoryVerifyInvalidRate) { $currentSnapshotQualityReasons += "memory_invalid_rate_above_cap" }
        if ($memoryActionsBlocked -gt $MaxMemoryVerifyActionsBlocked) { $currentSnapshotQualityReasons += "memory_actions_blocked_above_cap" }
        if ($sensitivityScenarioCount -lt $MinMemorySensitivityScenarioCount) { $currentSnapshotQualityReasons += "memory_sensitivity_scenario_count_below_floor" }
        if ($sensitivityMaxInvalidRate -lt $MinMemorySensitivityMaxInvalidRate) { $currentSnapshotQualityReasons += "memory_sensitivity_max_invalid_rate_below_floor" }
        if ($sensitivityMaxActionsBlocked -lt $MinMemorySensitivityMaxActionsBlocked) { $currentSnapshotQualityReasons += "memory_sensitivity_max_actions_blocked_below_floor" }
        if ($sensitivityMaxTotal -lt $MinMemorySensitivityMaxTotal) { $currentSnapshotQualityReasons += "memory_sensitivity_max_total_below_floor" }
        if ($sensitivityDistinctTagCount -lt $MinMemorySensitivityDistinctTagCount) { $currentSnapshotQualityReasons += "memory_sensitivity_distinct_tag_count_below_floor" }
        if ($sensitivityDistinctReasonCount -lt $MinMemorySensitivityDistinctReasonCount) { $currentSnapshotQualityReasons += "memory_sensitivity_distinct_reason_count_below_floor" }
        if ($null -ne $thresholdErrorCount -and $thresholdErrorCount -gt 0) { $currentSnapshotQualityReasons += "threshold_errors_present" }
        # Optional-missing metrics are governed by exemption policy and should
        # not block trend-history quality eligibility by themselves.
        $currentSnapshotQualityEligible = ($currentSnapshotQualityReasons.Count -eq 0)
        $currentSnapshotQualityCount = 0
        if ($currentSnapshotQualityEligible) { $currentSnapshotQualityCount = 1 }
        $historyWithCurrent = $priorSnapshots.Count + $currentSnapshotQualityCount

        $warningDebtStatus = "PASS"
        $warningDebtNotes = @()
        $warningDebtHistoryCount = 0
        $instructionOverrideWarningHits = 0
        $utilityBurdenWarningHits = 0
        $warningDebtWindowEntries = @()
        $maxPriorWarningSamples = [math]::Max($WarningDebtWindow - 1, 0)
        if ($maxPriorWarningSamples -gt 0) {
            $warningDebtWindowEntries = @($priorWarningSnapshots | Sort-Object sort_key | Select-Object -Last $maxPriorWarningSamples)
        }
        $warningDebtWindowEntries += [pscustomobject]@{
            path = (Join-Path $ReleaseRunDir "release_quality_snapshot.json")
            sort_key = $trendNowUtc
            warning_debt_schema_version = $warningDebtSchemaVersion
            instruction_override_cost_warning_triggered = [bool]$instructionOverrideCostWarnTriggered
            utility_burden_warning_triggered = [bool]$utilityBurdenWarnTriggered
        }
        $warningDebtHistoryCount = @($warningDebtWindowEntries).Count
        if ($SkipWarningDebtGuard) {
            $warningDebtStatus = "SKIP"
            $warningDebtNotes += "disabled_by_parameter"
            Write-Host "[SKIP] warning debt guard disabled by parameter."
        } elseif ($warningDebtHistoryCount -lt $WarningDebtWindow) {
            $warningDebtStatus = "SKIP"
            $warningDebtNotes += "bootstrap_mode"
            $warningDebtNotes += ("insufficient_warning_history: have={0}, need={1}" -f $warningDebtHistoryCount, $WarningDebtWindow)
            Write-Host ("[BOOTSTRAP] warning debt guard: insufficient history ({0}/{1} including current)." -f $warningDebtHistoryCount, $WarningDebtWindow)
        } else {
            $instructionOverrideWarningHits = @(
                $warningDebtWindowEntries | Where-Object { $_.instruction_override_cost_warning_triggered }
            ).Count
            $utilityBurdenWarningHits = @(
                $warningDebtWindowEntries | Where-Object { $_.utility_burden_warning_triggered }
            ).Count
            if ($instructionOverrideWarningHits -le $MaxInstructionOverrideCostWarningHits) {
                Write-Host ("[PASS] warning_debt.instruction_override_cost_warning_hits={0} <= {1} (window={2})" -f `
                    $instructionOverrideWarningHits, $MaxInstructionOverrideCostWarningHits, $WarningDebtWindow)
            } else {
                Write-Host ("[FAIL] warning_debt.instruction_override_cost_warning_hits={0} > {1} (window={2})" -f `
                    $instructionOverrideWarningHits, $MaxInstructionOverrideCostWarningHits, $WarningDebtWindow)
                $warningDebtStatus = "FAIL"
                $warningDebtNotes += "instruction_override_cost_warning_debt_exceeded"
            }
            if ($utilityBurdenWarningHits -le $MaxUtilityBurdenWarningHits) {
                Write-Host ("[PASS] warning_debt.utility_burden_warning_hits={0} <= {1} (window={2})" -f `
                    $utilityBurdenWarningHits, $MaxUtilityBurdenWarningHits, $WarningDebtWindow)
            } else {
                Write-Host ("[FAIL] warning_debt.utility_burden_warning_hits={0} > {1} (window={2})" -f `
                    $utilityBurdenWarningHits, $MaxUtilityBurdenWarningHits, $WarningDebtWindow)
                $warningDebtStatus = "FAIL"
                $warningDebtNotes += "utility_burden_warning_debt_exceeded"
            }
        }

        $trendStatus = "PASS"
        $trendNotes = @()
        $baselineReasoningMedian = $null
        $baselineImplicationMedian = $null
        $baselineAgencyMedian = $null
        $baselineTokensPerQP90Median = $null
        $baselineWallPerQP90Median = $null
        $reasoningDrop = $null
        $implicationDrop = $null
        $agencyDrop = $null
        $tokensPerQP90Increase = $null
        $wallPerQP90Increase = $null
        $reasoningDropPass = $true
        $implicationDropPass = $true
        $agencyDropPass = $true
        $tokensPerQP90IncreasePass = $true
        $wallPerQP90IncreasePass = $true

        if ($historyWithCurrent -lt $TrendMinHistory) {
            $trendStatus = "SKIP"
            $trendNotes += "bootstrap_mode"
            $trendNotes += ("insufficient_quality_history: have={0}, need={1}" -f $historyWithCurrent, $TrendMinHistory)
            if (-not $currentSnapshotQualityEligible) {
                $trendNotes += "current_snapshot_not_quality_eligible"
            }
            Write-Host ("[BOOTSTRAP] trend guard: insufficient quality history ({0}/{1} including current; prior_eligible={2}; prior_rejected={3}; max_age_days={4})." -f `
                $historyWithCurrent, $TrendMinHistory, $priorSnapshots.Count, $priorSnapshotRejections.Count, $TrendMaxSnapshotAgeDays)
        } else {
            $baselineReasoningMedian = Get-MedianValue -Values @($priorSnapshots | ForEach-Object { [double]$_.reasoning_score })
            $baselineImplicationMedian = Get-MedianValue -Values @($priorSnapshots | ForEach-Object { [double]$_.implication_core })
            $baselineAgencyMedian = Get-MedianValue -Values @($priorSnapshots | ForEach-Object { [double]$_.agency_core })
            $baselineTokenSamples = @($priorSnapshots | Where-Object { $null -ne $_.tokens_per_q_p90 } | ForEach-Object { [double]$_.tokens_per_q_p90 })
            $baselineWallSamples = @($priorSnapshots | Where-Object { $null -ne $_.wall_s_per_q_p90 } | ForEach-Object { [double]$_.wall_s_per_q_p90 })
            if ($baselineTokenSamples.Count -gt 0) {
                $baselineTokensPerQP90Median = Get-MedianValue -Values $baselineTokenSamples
            }
            if ($baselineWallSamples.Count -gt 0) {
                $baselineWallPerQP90Median = Get-MedianValue -Values $baselineWallSamples
            }

            if ($null -eq $baselineReasoningMedian -or $null -eq $baselineImplicationMedian -or $null -eq $baselineAgencyMedian) {
                $trendStatus = "SKIP"
                $trendNotes += "bootstrap_mode"
                $trendNotes += "insufficient_valid_baseline_metrics"
                Write-Host "[BOOTSTRAP] trend guard: unable to compute baseline medians from prior snapshots."
            } else {
                $reasoningDrop = [double]$baselineReasoningMedian - [double]$currentReasoningScore
                $implicationDrop = [double]$baselineImplicationMedian - [double]$currentImplicationCore
                $agencyDrop = [double]$baselineAgencyMedian - [double]$currentAgencyCore

                $reasoningDropPass = ($reasoningDrop -le $MaxTrendReasoningDrop)
                $implicationDropPass = ($implicationDrop -le $MaxTrendImplicationCoherenceDrop)
                $agencyDropPass = ($agencyDrop -le $MaxTrendAgencyPreservationDrop)

                if (-not $reasoningDropPass -or -not $implicationDropPass -or -not $agencyDropPass) {
                    $trendStatus = "FAIL"
                    $trendNotes += "regression_detected"
                }

                if ($reasoningDropPass) {
                    Write-Host ("[PASS] trend.reasoning_drop={0:N6} <= {1:N6}" -f $reasoningDrop, $MaxTrendReasoningDrop)
                } else {
                    Write-Host ("[FAIL] trend.reasoning_drop={0:N6} > {1:N6}" -f $reasoningDrop, $MaxTrendReasoningDrop)
                }
                if ($implicationDropPass) {
                    Write-Host ("[PASS] trend.implication_coherence_drop={0:N6} <= {1:N6}" -f $implicationDrop, $MaxTrendImplicationCoherenceDrop)
                } else {
                    Write-Host ("[FAIL] trend.implication_coherence_drop={0:N6} > {1:N6}" -f $implicationDrop, $MaxTrendImplicationCoherenceDrop)
                }
                if ($agencyDropPass) {
                    Write-Host ("[PASS] trend.agency_preservation_drop={0:N6} <= {1:N6}" -f $agencyDrop, $MaxTrendAgencyPreservationDrop)
                } else {
                    Write-Host ("[FAIL] trend.agency_preservation_drop={0:N6} > {1:N6}" -f $agencyDrop, $MaxTrendAgencyPreservationDrop)
                }

                if ($null -eq $baselineTokensPerQP90Median -or $baselineTokensPerQP90Median -le 0.0) {
                    $trendNotes += "cost_tokens_baseline_unavailable"
                    Write-Host "[BOOTSTRAP] trend guard: instruction_override.tokens_per_q_p90 baseline unavailable."
                } else {
                    $tokensPerQP90Increase = ([double]$instructionOverrideTokensPerQP90 - [double]$baselineTokensPerQP90Median) / [double]$baselineTokensPerQP90Median
                    $tokensPerQP90IncreasePass = ($tokensPerQP90Increase -le $MaxTrendInstructionOverrideTokensPerQP90Increase)
                    if ($tokensPerQP90IncreasePass) {
                        Write-Host ("[PASS] trend.instruction_override.tokens_per_q_p90_increase={0:N6} <= {1:N6}" -f $tokensPerQP90Increase, $MaxTrendInstructionOverrideTokensPerQP90Increase)
                    } else {
                        Write-Host ("[FAIL] trend.instruction_override.tokens_per_q_p90_increase={0:N6} > {1:N6}" -f $tokensPerQP90Increase, $MaxTrendInstructionOverrideTokensPerQP90Increase)
                        $trendStatus = "FAIL"
                        $trendNotes += "regression_detected"
                    }
                }

                if ($null -eq $baselineWallPerQP90Median -or $baselineWallPerQP90Median -le 0.0) {
                    $trendNotes += "cost_wall_baseline_unavailable"
                    Write-Host "[BOOTSTRAP] trend guard: instruction_override.wall_s_per_q_p90 baseline unavailable."
                } else {
                    $wallPerQP90Increase = ([double]$instructionOverrideWallPerQP90 - [double]$baselineWallPerQP90Median) / [double]$baselineWallPerQP90Median
                    $wallPerQP90IncreasePass = ($wallPerQP90Increase -le $MaxTrendInstructionOverrideWallPerQP90Increase)
                    if ($wallPerQP90IncreasePass) {
                        Write-Host ("[PASS] trend.instruction_override.wall_s_per_q_p90_increase={0:N6} <= {1:N6}" -f $wallPerQP90Increase, $MaxTrendInstructionOverrideWallPerQP90Increase)
                    } else {
                        Write-Host ("[FAIL] trend.instruction_override.wall_s_per_q_p90_increase={0:N6} > {1:N6}" -f $wallPerQP90Increase, $MaxTrendInstructionOverrideWallPerQP90Increase)
                        $trendStatus = "FAIL"
                        $trendNotes += "regression_detected"
                    }
                }
            }
        }

        $trendGuardPath = Join-Path $ReleaseRunDir "release_trend_guard.json"
        $trendGuardPayload = [ordered]@{
            benchmark = "release_trend_guard"
            generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
            status = $trendStatus
            release_run_dir = $ReleaseRunDir
            window = $TrendReleaseWindow
            min_history = $TrendMinHistory
            max_snapshot_age_days = $TrendMaxSnapshotAgeDays
            history_count_including_current = $historyWithCurrent
            history_sample_count = $priorSnapshots.Count
            history_rejected_count = $priorSnapshotRejections.Count
            current_snapshot_quality_eligible = $currentSnapshotQualityEligible
            current_snapshot_quality_reasons = @($currentSnapshotQualityReasons)
            thresholds = [ordered]@{
                warning_debt_window = $WarningDebtWindow
                skip_warning_debt_guard = [bool]$SkipWarningDebtGuard
                max_instruction_override_cost_warning_hits = $MaxInstructionOverrideCostWarningHits
                max_utility_burden_warning_hits = $MaxUtilityBurdenWarningHits
                max_trend_reasoning_drop = $MaxTrendReasoningDrop
                max_trend_implication_coherence_drop = $MaxTrendImplicationCoherenceDrop
                max_trend_agency_preservation_drop = $MaxTrendAgencyPreservationDrop
                max_trend_instruction_override_tokens_per_q_p90_increase = $MaxTrendInstructionOverrideTokensPerQP90Increase
                max_trend_instruction_override_wall_s_per_q_p90_increase = $MaxTrendInstructionOverrideWallPerQP90Increase
            }
            current = [ordered]@{
                derived_reasoning_score = $currentReasoningScore
                derived_implication_coherence_core = $currentImplicationCore
                derived_agency_preservation_core = $currentAgencyCore
                instruction_override_tokens_per_q_p90 = $instructionOverrideTokensPerQP90
                instruction_override_wall_s_per_q_p90 = $instructionOverrideWallPerQP90
            }
            baseline_median = [ordered]@{
                derived_reasoning_score = $baselineReasoningMedian
                derived_implication_coherence_core = $baselineImplicationMedian
                derived_agency_preservation_core = $baselineAgencyMedian
                instruction_override_tokens_per_q_p90 = $baselineTokensPerQP90Median
                instruction_override_wall_s_per_q_p90 = $baselineWallPerQP90Median
            }
            drops = [ordered]@{
                derived_reasoning_score = $reasoningDrop
                derived_implication_coherence_core = $implicationDrop
                derived_agency_preservation_core = $agencyDrop
                instruction_override_tokens_per_q_p90_increase = $tokensPerQP90Increase
                instruction_override_wall_s_per_q_p90_increase = $wallPerQP90Increase
            }
            checks = [ordered]@{
                warning_debt_status = $warningDebtStatus
                instruction_override_cost_warning_hits = $instructionOverrideWarningHits
                utility_burden_warning_hits = $utilityBurdenWarningHits
                reasoning_drop_ok = $reasoningDropPass
                implication_coherence_drop_ok = $implicationDropPass
                agency_preservation_drop_ok = $agencyDropPass
                instruction_override_tokens_per_q_p90_increase_ok = $tokensPerQP90IncreasePass
                instruction_override_wall_s_per_q_p90_increase_ok = $wallPerQP90IncreasePass
            }
            notes = @($trendNotes + $warningDebtNotes)
            history_sources = @($priorSnapshots | ForEach-Object { $_.path })
            history_rejections = @($priorSnapshotRejections)
            warning_history_sources = @($warningDebtWindowEntries | ForEach-Object { $_.path })
        }
        $trendGuardPayload | ConvertTo-Json -Depth 7 | Set-Content -Path $trendGuardPath -Encoding UTF8
        .\scripts\set_latest_pointer.ps1 -RunDir $trendGuardPath -PointerPath "runs\\latest_release_trend_guard" | Out-Host

        $qualitySnapshotPath = Join-Path $ReleaseRunDir "release_quality_snapshot.json"
        $qualitySnapshotPayload = [ordered]@{
            benchmark = "release_quality_snapshot"
            generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
            status = if ($trendStatus -eq "FAIL" -or $warningDebtStatus -eq "FAIL") { "FAIL" } else { "PASS" }
            release_run_dir = $ReleaseRunDir
            reliability_signal_path = $reliabilitySignalPath
            metrics = [ordered]@{
                derived_reasoning_score = $currentReasoningScore
                derived_implication_coherence_core = $currentImplicationCore
                derived_agency_preservation_core = $currentAgencyCore
                warning_debt_schema_version = $warningDebtSchemaVersion
                instruction_override_tokens_per_q_p90 = $instructionOverrideTokensPerQP90
                instruction_override_wall_s_per_q_p90 = $instructionOverrideWallPerQP90
                memory_verify_total = $memoryTotal
                memory_verify_use_rate = $memoryUseRate
                memory_verify_verified_rate = $memoryVerifiedRate
                memory_verify_invalid_rate = $memoryInvalidRate
                memory_verify_actions_blocked = $memoryActionsBlocked
            }
            gates = [ordered]@{
                utility_burden_delta = $utilityBurdenDelta
                utility_burden_delta_cap = $MaxReleaseUtilityBurdenDelta
                utility_burden_delta_warn = $WarnReleaseUtilityBurdenDelta
                utility_burden_warning_triggered = $utilityBurdenWarnTriggered
                instruction_override_tokens_per_q_p90_cap = $MaxInstructionOverrideTokensPerQP90
                instruction_override_tokens_per_q_p90_warn = $WarnInstructionOverrideTokensPerQP90
                instruction_override_wall_s_per_q_p90_cap = $MaxInstructionOverrideWallPerQP90
                instruction_override_wall_s_per_q_p90_warn = $WarnInstructionOverrideWallPerQP90
                instruction_override_cost_warning_triggered = $instructionOverrideCostWarnTriggered
                warning_debt_status = $warningDebtStatus
                warning_debt_window = $WarningDebtWindow
                warning_debt_history_count = $warningDebtHistoryCount
                warning_debt_instruction_override_cost_warning_hits = $instructionOverrideWarningHits
                warning_debt_instruction_override_cost_warning_hits_cap = $MaxInstructionOverrideCostWarningHits
                warning_debt_utility_burden_warning_hits = $utilityBurdenWarningHits
                warning_debt_utility_burden_warning_hits_cap = $MaxUtilityBurdenWarningHits
                threshold_error_count = $thresholdErrorCount
                threshold_optional_missing_na_count = $optionalMissingNaCount
                threshold_strict_optional_mode_active = $strictOptionalThresholdMetricsActive
                threshold_history_quality_count = $thresholdHistoryPassCount
                threshold_history_rejected_count = $thresholdHistoryRejectedCount
                memory_sensitivity_scenario_count = $sensitivityScenarioCount
                memory_sensitivity_max_invalid_rate = $sensitivityMaxInvalidRate
                memory_sensitivity_max_actions_blocked = $sensitivityMaxActionsBlocked
                memory_sensitivity_max_total = $sensitivityMaxTotal
                memory_sensitivity_distinct_tag_count = $sensitivityDistinctTagCount
                memory_sensitivity_distinct_reason_count = $sensitivityDistinctReasonCount
                regression_frontier_coverage = $frontierCoverageRate
                regression_frontier_coverage_floor = $MinRegressionFrontierCoverage
                regression_frontier_reduction = $frontierReductionRate
                regression_frontier_reduction_floor = $MinRegressionFrontierReduction
                trend_guard_status = $trendStatus
            }
            integrity = [ordered]@{
                warning_count = @($releaseIntegrityWarnings | Select-Object -Unique).Count
                warnings = @($releaseIntegrityWarnings | Select-Object -Unique)
                risk_warning_count = @($releaseRiskWarnings | Select-Object -Unique).Count
                risk_warnings = @($releaseRiskWarnings | Select-Object -Unique)
            }
        }
        $qualitySnapshotPayload | ConvertTo-Json -Depth 6 | Set-Content -Path $qualitySnapshotPath -Encoding UTF8
        .\scripts\set_latest_pointer.ps1 -RunDir $qualitySnapshotPath -PointerPath "runs\\latest_release_quality_snapshot" | Out-Host

        if ($trendStatus -eq "FAIL") {
            Write-Error "Trend regression guard failed."
            exit 1
        }
        if ($warningDebtStatus -eq "FAIL") {
            Write-Error "Warning debt guard failed."
            exit 1
        }
    } else {
        Write-Host "Skipping unified reliability signal gate (-SkipReliabilitySignal)."
        if ($SkipRealWorldUtilityEval) {
            Write-Host "Skipping real-world utility A/B gate (-SkipRealWorldUtilityEval)."
        } else {
            Write-Host "Skipping real-world utility A/B gate (requires unified reliability gate)."
        }
    }
}
