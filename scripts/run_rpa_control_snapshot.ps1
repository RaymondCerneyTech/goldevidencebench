param(
    [string]$ReliabilitySignal = "runs\reliability_signal_latest.json",
    [string]$EpistemicReliability = "runs\epistemic_calibration_suite_reliability_latest.json",
    [string]$AuthorityReliability = "runs\authority_under_interference_hardening_reliability_latest.json",
    [string]$MyopicReliability = "runs\myopic_planning_traps_reliability_latest.json",
    [string]$ReferentialReliability = "runs\referential_indexing_suite_reliability_latest.json",
    [string]$NovelLongHorizonReliability = "runs\novel_continuity_long_horizon_reliability_latest.json",
    [ValidateSet("auto", "reason", "plan", "act")]
    [string]$Mode = "auto",
    [ValidateSet("reversible", "irreversible")]
    [string]$Reversibility = "reversible",
    [double]$ConfidenceFloor = 0.70,
    [double]$PlanningFloor = 0.90,
    [double]$ReasoningFloor = 0.90,
    [double]$NeededInfoFloor = 0.75,
    [double]$RiskFloor = 0.50,
    [double]$IrreversibleConfidenceFloor = 0.85,
    [string]$Out = "runs\rpa_control_latest.json"
)

$ErrorActionPreference = "Stop"

$args = @(
    ".\scripts\build_rpa_control_snapshot.py",
    "--reliability-signal", $ReliabilitySignal,
    "--epistemic-reliability", $EpistemicReliability,
    "--authority-reliability", $AuthorityReliability,
    "--myopic-reliability", $MyopicReliability,
    "--referential-reliability", $ReferentialReliability,
    "--novel-long-horizon-reliability", $NovelLongHorizonReliability,
    "--mode", $Mode,
    "--reversibility", $Reversibility,
    "--confidence-floor", "$ConfidenceFloor",
    "--planning-floor", "$PlanningFloor",
    "--reasoning-floor", "$ReasoningFloor",
    "--needed-info-floor", "$NeededInfoFloor",
    "--risk-floor", "$RiskFloor",
    "--irreversible-confidence-floor", "$IrreversibleConfidenceFloor",
    "--out", $Out
)

python @args | Out-Host
exit $LASTEXITCODE
