param(
    [ValidateSet(
        "compression_roundtrip_generalization",
        "myopic_planning_traps",
        "referential_indexing_suite",
        "novel_continuity",
        "novel_continuity_long_horizon",
        "epistemic_calibration_suite",
        "authority_under_interference",
        "authority_under_interference_hardening",
        "rpa_mode_switch",
        "intent_spec_layer",
        "noise_escalation",
        "implication_coherence",
        "agency_preserving_substitution",
        "persona_amalgamation",
        "social_pressure_self_doubt",
        "rag_prompt_injection"
    )]
    [string]$Family,
    [ValidateSet("observe", "ramp", "target", "custom")]
    [string]$Stage = "ramp",
    [string]$Adapter = "goldevidencebench.adapters.llama_server_adapter:create_adapter",
    [int]$RunCount = 3,
    [int]$SleepSeconds = 2,
    [switch]$OverwriteFirstRun = $true,
    [switch]$UseRealPublicFixtures,
    [double]$MaxJitter = -1.0,
    [bool]$RunPersonaTrap = $true,
    [string]$PersonaProfiles = "persona_confident_expert,persona_creative_writer,persona_ultra_brief,persona_overly_helpful",
    [string[]]$CheckerExtraArgs = @(),
    [switch]$ContinueOnRunFailure,
    [string]$Out = "",
    [switch]$PromoteLatestOnPass
)

$ErrorActionPreference = "Stop"

$runScriptMap = @{
    "compression_roundtrip_generalization" = ".\scripts\run_compression_roundtrip_generalization_family.ps1"
    "myopic_planning_traps" = ".\scripts\run_myopic_planning_traps_family.ps1"
    "referential_indexing_suite" = ".\scripts\run_referential_indexing_suite_family.ps1"
    "novel_continuity" = ".\scripts\run_novel_continuity_family.ps1"
    "novel_continuity_long_horizon" = ".\scripts\run_novel_continuity_long_horizon_family.ps1"
    "epistemic_calibration_suite" = ".\scripts\run_epistemic_calibration_suite_family.ps1"
    "authority_under_interference" = ".\scripts\run_authority_under_interference_family.ps1"
    "authority_under_interference_hardening" = ".\scripts\run_authority_under_interference_hardening_family.ps1"
    "rpa_mode_switch" = ".\scripts\run_rpa_mode_switch_family.ps1"
    "intent_spec_layer" = ".\scripts\run_intent_spec_family.ps1"
    "noise_escalation" = ".\scripts\run_noise_escalation_family.ps1"
    "implication_coherence" = ".\scripts\run_implication_coherence_family.ps1"
    "agency_preserving_substitution" = ".\scripts\run_agency_preserving_substitution_family.ps1"
    "persona_amalgamation" = ".\scripts\run_persona_amalgamation_family.ps1"
    "social_pressure_self_doubt" = ".\scripts\run_social_pressure_self_doubt_family.ps1"
    "rag_prompt_injection" = ".\scripts\run_rag_prompt_injection_family.ps1"
}

$checkerMap = @{
    "compression_roundtrip_generalization" = ".\scripts\check_compression_roundtrip_generalization_reliability.py"
    "myopic_planning_traps" = ".\scripts\check_myopic_planning_traps_reliability.py"
    "referential_indexing_suite" = ".\scripts\check_referential_indexing_suite_reliability.py"
    "novel_continuity" = ".\scripts\check_novel_continuity_reliability.py"
    "novel_continuity_long_horizon" = ".\scripts\check_novel_continuity_long_horizon_reliability.py"
    "epistemic_calibration_suite" = ".\scripts\check_epistemic_calibration_suite_reliability.py"
    "authority_under_interference" = ".\scripts\check_authority_under_interference_reliability.py"
    "authority_under_interference_hardening" = ".\scripts\check_authority_under_interference_hardening_reliability.py"
    "rpa_mode_switch" = ".\scripts\check_rpa_mode_switch_reliability.py"
    "intent_spec_layer" = ".\scripts\check_intent_spec_reliability.py"
    "noise_escalation" = ".\scripts\check_noise_escalation_reliability.py"
    "implication_coherence" = ".\scripts\check_implication_coherence_reliability.py"
    "agency_preserving_substitution" = ".\scripts\check_agency_preserving_substitution_reliability.py"
    "persona_amalgamation" = ".\scripts\check_persona_amalgamation_reliability.py"
    "social_pressure_self_doubt" = ".\scripts\check_social_pressure_self_doubt_reliability.py"
    "rag_prompt_injection" = ".\scripts\check_rag_prompt_injection_reliability.py"
}

$latestMap = @{
    "compression_roundtrip_generalization" = "runs\compression_roundtrip_generalization_reliability_latest.json"
    "myopic_planning_traps" = "runs\myopic_planning_traps_reliability_latest.json"
    "referential_indexing_suite" = "runs\referential_indexing_suite_reliability_latest.json"
    "novel_continuity" = "runs\novel_continuity_reliability_latest.json"
    "novel_continuity_long_horizon" = "runs\novel_continuity_long_horizon_reliability_latest.json"
    "epistemic_calibration_suite" = "runs\epistemic_calibration_suite_reliability_latest.json"
    "authority_under_interference" = "runs\authority_under_interference_reliability_latest.json"
    "authority_under_interference_hardening" = "runs\authority_under_interference_hardening_reliability_latest.json"
    "rpa_mode_switch" = "runs\rpa_mode_switch_reliability_latest.json"
    "intent_spec_layer" = "runs\intent_spec_layer_reliability_latest.json"
    "noise_escalation" = "runs\noise_escalation_reliability_latest.json"
    "implication_coherence" = "runs\implication_coherence_reliability_latest.json"
    "agency_preserving_substitution" = "runs\agency_preserving_substitution_reliability_latest.json"
    "persona_amalgamation" = "runs\persona_amalgamation_reliability_latest.json"
    "social_pressure_self_doubt" = "runs\social_pressure_self_doubt_reliability_latest.json"
    "rag_prompt_injection" = "runs\rag_prompt_injection_reliability_latest.json"
}

$stageModeMap = @{
    "compression_roundtrip_generalization" = "stage"
    "myopic_planning_traps" = "stage"
    "referential_indexing_suite" = "stage"
    "novel_continuity" = "cite_stage"
    "novel_continuity_long_horizon" = "cite_stage"
    "epistemic_calibration_suite" = "stage"
    "authority_under_interference" = "none"
    "authority_under_interference_hardening" = "none"
    "rpa_mode_switch" = "stage"
    "intent_spec_layer" = "stage"
    "noise_escalation" = "stage"
    "implication_coherence" = "stage"
    "agency_preserving_substitution" = "stage"
    "persona_amalgamation" = "stage"
    "social_pressure_self_doubt" = "stage"
    "rag_prompt_injection" = "stage"
}

$runner = $runScriptMap[$Family]
$checker = $checkerMap[$Family]
$latestPath = $latestMap[$Family]
$stageMode = $stageModeMap[$Family]

if (-not $Out) {
    if ($stageMode -eq "none") {
        $Out = "runs\${Family}_reliability_candidate.json"
    } else {
        $Out = "runs\${Family}_reliability_${Stage}_candidate.json"
    }
}

$runs = @()
for ($i = 1; $i -le $RunCount; $i++) {
    if ($stageMode -eq "none") {
        $run = "runs\${Family}_$(Get-Date -Format yyyyMMdd_HHmmss)_r$i"
    } else {
        $run = "runs\${Family}_$(Get-Date -Format yyyyMMdd_HHmmss)_${Stage}_r$i"
    }
    $runs += $run

    $runArgs = @{
        Adapter = $Adapter
        OutRoot = $run
    }
    if ($stageMode -eq "stage") {
        $runArgs.Stage = $Stage
    } elseif ($stageMode -eq "cite_stage") {
        $runArgs.CiteStage = $Stage
    }
    if (($i -eq 1) -and $OverwriteFirstRun) {
        $runArgs.OverwriteFixtures = $true
    }
    if ($UseRealPublicFixtures) {
        $runArgs.UseRealPublicFixtures = $true
    }
    $runArgs.RunPersonaTrap = $RunPersonaTrap
    if (-not [string]::IsNullOrWhiteSpace($PersonaProfiles)) {
        $runArgs.PersonaProfiles = $PersonaProfiles
    }

    & $runner @runArgs
    $runExit = $LASTEXITCODE
    if ($runExit -ne 0) {
        if ($ContinueOnRunFailure) {
            Write-Warning "$Family run $i failed (exit $runExit). Continuing due to -ContinueOnRunFailure."
        } else {
            throw "$Family run $i failed (exit $runExit)."
        }
    }
    Start-Sleep -Seconds $SleepSeconds
}

$checkerArgs = @(
    $checker,
    "--run-dirs"
)
$checkerArgs += $runs
$checkerArgs += @("--min-runs", "$RunCount")
if ($stageMode -eq "stage") {
    $checkerArgs += @("--stage", $Stage)
} elseif ($stageMode -eq "cite_stage") {
    $checkerArgs += @("--cite-stage", $Stage)
}
if ($MaxJitter -ge 0.0) {
    $baseJitterFamilies = @(
        "compression_roundtrip_generalization",
        "myopic_planning_traps",
        "referential_indexing_suite",
        "novel_continuity",
        "novel_continuity_long_horizon",
        "authority_under_interference",
        "authority_under_interference_hardening",
        "rpa_mode_switch",
        "intent_spec_layer",
        "noise_escalation",
        "implication_coherence",
        "agency_preserving_substitution",
        "persona_amalgamation",
        "social_pressure_self_doubt",
        "rag_prompt_injection"
    )
    if ($baseJitterFamilies -contains $Family) {
        $checkerArgs += @("--max-value-acc-jitter", "$MaxJitter")
        $checkerArgs += @("--max-exact-acc-jitter", "$MaxJitter")
        $checkerArgs += @("--max-cite-f1-jitter", "$MaxJitter")
    }
    if ($Family -eq "myopic_planning_traps") {
        $checkerArgs += @("--max-horizon-success-jitter", "$MaxJitter")
        $checkerArgs += @("--max-recovery-rate-jitter", "$MaxJitter")
        $checkerArgs += @("--max-trap-entry-jitter", "$MaxJitter")
    } elseif ($Family -eq "epistemic_calibration_suite") {
        $checkerArgs += @("--max-kkyi-jitter", "$MaxJitter")
        $checkerArgs += @("--max-overclaim-jitter", "$MaxJitter")
        $checkerArgs += @("--max-abstain-f1-jitter", "$MaxJitter")
        $checkerArgs += @("--max-ece-jitter", "$MaxJitter")
    } elseif ($Family -eq "authority_under_interference" -or $Family -eq "authority_under_interference_hardening") {
        $checkerArgs += @("--max-authority-violation-jitter", "$MaxJitter")
    } elseif ($Family -eq "rpa_mode_switch") {
        $checkerArgs += @("--max-mode-switch-jitter", "$MaxJitter")
        $checkerArgs += @("--max-premature-act-jitter", "$MaxJitter")
        $checkerArgs += @("--max-unnecessary-plan-jitter", "$MaxJitter")
    } elseif ($Family -eq "intent_spec_layer") {
        $checkerArgs += @("--max-clarification-precision-jitter", "$MaxJitter")
        $checkerArgs += @("--max-clarification-recall-jitter", "$MaxJitter")
        $checkerArgs += @("--max-user-burden-jitter", "$MaxJitter")
    } elseif ($Family -eq "noise_escalation") {
        $checkerArgs += @("--max-noise-slope-jitter", "$MaxJitter")
        $checkerArgs += @("--max-recovery-latency-jitter", "$MaxJitter")
        $checkerArgs += @("--max-irrecoverable-drift-jitter", "$MaxJitter")
    } elseif ($Family -eq "implication_coherence") {
        $checkerArgs += @("--max-implication-consistency-jitter", "$MaxJitter")
        $checkerArgs += @("--max-dependency-coverage-jitter", "$MaxJitter")
        $checkerArgs += @("--max-contradiction-repair-jitter", "$MaxJitter")
        $checkerArgs += @("--max-causal-precision-jitter", "$MaxJitter")
        $checkerArgs += @("--max-propagation-latency-jitter", "$MaxJitter")
        $checkerArgs += @("--max-implication-break-jitter", "$MaxJitter")
        $checkerArgs += @("--max-ic-score-jitter", "$MaxJitter")
        $checkerArgs += @("--max-hard-case-value-acc-jitter", "$MaxJitter")
        $checkerArgs += @("--max-hard-case-cite-f1-jitter", "$MaxJitter")
        $checkerArgs += @("--max-hard-implication-break-jitter", "$MaxJitter")
        $checkerArgs += @("--max-hard-ic-score-jitter", "$MaxJitter")
    } elseif ($Family -eq "agency_preserving_substitution") {
        $checkerArgs += @("--max-substitution-transparency-jitter", "$MaxJitter")
        $checkerArgs += @("--max-unauthorized-substitution-jitter", "$MaxJitter")
        $checkerArgs += @("--max-intent-preservation-jitter", "$MaxJitter")
        $checkerArgs += @("--max-agency-loss-error-jitter", "$MaxJitter")
        $checkerArgs += @("--max-recovery-success-jitter", "$MaxJitter")
    } elseif ($Family -eq "persona_amalgamation") {
        $checkerArgs += @("--max-persona-stability-jitter", "$MaxJitter")
        $checkerArgs += @("--max-subject-mimic-jitter", "$MaxJitter")
        $checkerArgs += @("--max-amalgam-blend-jitter", "$MaxJitter")
        $checkerArgs += @("--max-boundary-action-jitter", "$MaxJitter")
        $checkerArgs += @("--max-high-pressure-stability-jitter", "$MaxJitter")
    } elseif ($Family -eq "social_pressure_self_doubt") {
        $checkerArgs += @("--max-baseline-correct-rate-jitter", "$MaxJitter")
        $checkerArgs += @("--max-flip-rate-jitter", "$MaxJitter")
        $checkerArgs += @("--max-unnecessary-revision-rate-jitter", "$MaxJitter")
        $checkerArgs += @("--max-citation-drift-rate-jitter", "$MaxJitter")
        $checkerArgs += @("--max-per-attack-flip-rate-jitter", "$MaxJitter")
        $checkerArgs += @("--max-capitulation-rate-jitter", "$MaxJitter")
        $checkerArgs += @("--max-responsiveness-rate-jitter", "$MaxJitter")
        $checkerArgs += @("--max-suggestion-hijacking-goal-drift-rate-jitter", "$MaxJitter")
        $checkerArgs += @("--max-suggestion-hijacking-instruction-violation-rate-jitter", "$MaxJitter")
        $checkerArgs += @("--max-emotional-capitulation-rate-jitter", "$MaxJitter")
        $checkerArgs += @("--max-fatigue-degradation-jitter", "$MaxJitter")
    } elseif ($Family -eq "rag_prompt_injection") {
        $checkerArgs += @("--max-baseline-correct-rate-jitter", "$MaxJitter")
        $checkerArgs += @("--max-flip-rate-jitter", "$MaxJitter")
        $checkerArgs += @("--max-unnecessary-revision-rate-jitter", "$MaxJitter")
        $checkerArgs += @("--max-citation-drift-rate-jitter", "$MaxJitter")
        $checkerArgs += @("--max-per-variant-flip-rate-jitter", "$MaxJitter")
        $checkerArgs += @("--max-suggestion-hijacking-goal-drift-rate-jitter", "$MaxJitter")
        $checkerArgs += @("--max-suggestion-hijacking-instruction-violation-rate-jitter", "$MaxJitter")
    }
}
if ($CheckerExtraArgs.Count -gt 0) {
    $checkerArgs += $CheckerExtraArgs
}
$checkerArgs += @("--out", $Out)

if (Test-Path $Out) {
    Remove-Item -Path $Out -Force
}

python @checkerArgs | Out-Host
$checkerExit = $LASTEXITCODE
if ($checkerExit -ne 0) {
    if ($ContinueOnRunFailure) {
        Write-Warning "$Family reliability check failed (exit $checkerExit)."
    } else {
        throw "$Family reliability check failed (exit $checkerExit)."
    }
}

$status = "MISSING"
if (($checkerExit -eq 0) -or (Test-Path $Out)) {
    if (Test-Path $Out) {
        try {
            $status = (Get-Content -Raw -Path $Out | ConvertFrom-Json).status
        } catch {
            $status = "INVALID"
        }
    } else {
        $status = "MISSING"
    }
}
if (($checkerExit -ne 0) -and ($status -eq "MISSING")) {
    $status = "CHECKER_ERROR"
}
Write-Host "$Family stage=$Stage candidate status: $status"
Write-Host "Candidate: $Out"

if ($PromoteLatestOnPass) {
    $promotionAllowed = ($stageMode -eq "none") -or ($Stage -eq "target")
    if (-not $promotionAllowed) {
        Write-Warning "Promotion skipped: only target stage can be promoted to *_latest for staged families."
    } elseif (($status -eq "PASS") -and ($checkerExit -eq 0)) {
        Copy-Item -Path $Out -Destination $latestPath -Force
        Write-Host "PROMOTED -> $latestPath"
    } elseif ($status -eq "PASS") {
        Write-Warning "Promotion skipped: checker exited non-zero."
    } else {
        Write-Warning "Target candidate failed; latest not updated."
    }
}

Write-Host "Run dirs:"
$runs | ForEach-Object { Write-Host "- $_" }

if ($status -ne "PASS") {
    if ($ContinueOnRunFailure) {
        Write-Warning "$Family stage=$Stage candidate is not PASS."
    } else {
        throw "$Family stage=$Stage candidate is not PASS."
    }
}
