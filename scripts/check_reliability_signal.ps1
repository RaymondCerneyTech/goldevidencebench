param(
    [string]$Strict = "runs\latest_rag_strict",
    [string]$CompressionReliability = "runs\compression_reliability_latest.json",
    [string]$NovelReliability = "runs\novel_continuity_reliability_latest.json",
    [string]$AuthorityInterferenceReliability = "runs\authority_under_interference_reliability_latest.json",
    [string]$CompressionRoundtripReliability = "runs\compression_roundtrip_generalization_reliability_latest.json",
    [switch]$RequireCompressionRoundtrip,
    [string]$NovelLongHorizonReliability = "runs\novel_continuity_long_horizon_reliability_latest.json",
    [switch]$RequireNovelLongHorizon,
    [string]$MyopicPlanningReliability = "runs\myopic_planning_traps_reliability_latest.json",
    [switch]$RequireMyopicPlanning,
    [string]$ReferentialIndexingReliability = "runs\referential_indexing_suite_reliability_latest.json",
    [switch]$RequireReferentialIndexing,
    [string]$EpistemicReliability = "runs\epistemic_calibration_suite_reliability_latest.json",
    [switch]$RequireEpistemic,
    [string]$AuthorityHardeningReliability = "runs\authority_under_interference_hardening_reliability_latest.json",
    [switch]$RequireAuthorityHardening,
    [string]$RPAModeSwitchReliability = "runs\rpa_mode_switch_reliability_latest.json",
    [switch]$RequireRPAModeSwitch,
    [string]$IntentSpecReliability = "runs\intent_spec_layer_reliability_latest.json",
    [switch]$RequireIntentSpec,
    [string]$NoiseEscalationReliability = "runs\noise_escalation_reliability_latest.json",
    [switch]$RequireNoiseEscalation,
    [double]$MinValueAcc = 0.95,
    [double]$MinExactAcc = 0.95,
    [double]$MinCiteF1 = 0.95,
    [double]$MinInstructionAcc = 0.95,
    [double]$MinStateIntegrityRate = 0.95,
    [Nullable[double]]$MinReasoningScore = $null,
    [Nullable[double]]$MinPlanningScore = $null,
    [Nullable[double]]$MinIntelligenceIndex = $null,
    [switch]$SkipDomainHardChecks,
    [string]$Out = "runs\reliability_signal_latest.json"
)

$ErrorActionPreference = "Stop"

$args = @(
    ".\scripts\check_reliability_signal.py",
    "--strict", $Strict,
    "--compression-reliability", $CompressionReliability,
    "--novel-reliability", $NovelReliability,
    "--authority-interference-reliability", $AuthorityInterferenceReliability,
    "--compression-roundtrip-reliability", $CompressionRoundtripReliability,
    "--novel-long-horizon-reliability", $NovelLongHorizonReliability,
    "--myopic-planning-reliability", $MyopicPlanningReliability,
    "--referential-indexing-reliability", $ReferentialIndexingReliability,
    "--epistemic-reliability", $EpistemicReliability,
    "--authority-hardening-reliability", $AuthorityHardeningReliability,
    "--rpa-mode-switch-reliability", $RPAModeSwitchReliability,
    "--intent-spec-reliability", $IntentSpecReliability,
    "--noise-escalation-reliability", $NoiseEscalationReliability,
    "--min-value-acc", "$MinValueAcc",
    "--min-exact-acc", "$MinExactAcc",
    "--min-cite-f1", "$MinCiteF1",
    "--min-instruction-acc", "$MinInstructionAcc",
    "--min-state-integrity-rate", "$MinStateIntegrityRate",
    "--out", $Out
)
if ($SkipDomainHardChecks) {
    $args += "--skip-domain-hard-checks"
}
if ($null -ne $MinReasoningScore) {
    $args += @("--min-reasoning-score", "$MinReasoningScore")
}
if ($null -ne $MinPlanningScore) {
    $args += @("--min-planning-score", "$MinPlanningScore")
}
if ($null -ne $MinIntelligenceIndex) {
    $args += @("--min-intelligence-index", "$MinIntelligenceIndex")
}
if ($RequireNovelLongHorizon) {
    $args += "--require-novel-long-horizon"
}
if ($RequireCompressionRoundtrip) {
    $args += "--require-compression-roundtrip"
}
if ($RequireMyopicPlanning) {
    $args += "--require-myopic-planning"
}
if ($RequireReferentialIndexing) {
    $args += "--require-referential-indexing"
}
if ($RequireEpistemic) {
    $args += "--require-epistemic"
}
if ($RequireAuthorityHardening) {
    $args += "--require-authority-hardening"
}
if ($RequireRPAModeSwitch) {
    $args += "--require-rpa-mode-switch"
}
if ($RequireIntentSpec) {
    $args += "--require-intent-spec"
}
if ($RequireNoiseEscalation) {
    $args += "--require-noise-escalation"
}

python @args | Out-Host
exit $LASTEXITCODE
