param(
    [string]$Adapter = "goldevidencebench.adapters.llama_server_adapter:create_adapter",
    [ValidateSet("observe", "ramp", "target", "custom")]
    [string]$Stage = "target",
    [int]$RunCount = 5,
    [int]$SleepSeconds = 2,
    [double]$MaxJitter = 0.02,
    [bool]$OverwriteFirstRun = $true,
    [bool]$PromoteLatestOnPass = $true,
    [bool]$ContinueOnFailure = $true,
    [bool]$SkipReliabilitySignal = $false,
    [double]$MinReasoningScore = 0.90,
    [double]$MinPlanningScore = 0.90,
    [double]$MinIntelligenceIndex = 0.90,
    [string]$Out = "",
    [string[]]$Families = @(
        "compression_roundtrip_generalization",
        "myopic_planning_traps",
        "referential_indexing_suite",
        "novel_continuity_long_horizon",
        "epistemic_calibration_suite",
        "authority_under_interference_hardening"
    )
)

$ErrorActionPreference = "Stop"

if (-not $Out) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $Out = "runs\robustness_threshold_$stamp.json"
}

Write-Host "Robustness threshold campaign"
Write-Host "Stage: $Stage"
Write-Host "RunCount: $RunCount"
Write-Host "MaxJitter: $MaxJitter"
Write-Host "Families: $($Families -join ', ')"

$familyRows = @()
$overallPass = $true

foreach ($family in $Families) {
    $usesStage = @(
        "compression_roundtrip_generalization",
        "myopic_planning_traps",
        "referential_indexing_suite",
        "epistemic_calibration_suite"
    ) -contains $family
    $usesCiteStage = @("novel_continuity", "novel_continuity_long_horizon") -contains $family

    if ($usesStage -or $usesCiteStage) {
        $candidateOut = "runs\${family}_reliability_${Stage}_candidate.json"
    } else {
        $candidateOut = "runs\${family}_reliability_candidate.json"
    }

    Write-Host ""
    Write-Host ("Running {0} (runs={1}, stage={2}, max_jitter={3:0.000})..." -f $family, $RunCount, $Stage, $MaxJitter)

    $runArgs = @{
        Family = $family
        Stage = $Stage
        Adapter = $Adapter
        RunCount = $RunCount
        SleepSeconds = $SleepSeconds
        MaxJitter = $MaxJitter
        Out = $candidateOut
    }
    if ($OverwriteFirstRun) {
        $runArgs.OverwriteFirstRun = $true
    }
    if ($PromoteLatestOnPass) {
        $runArgs.PromoteLatestOnPass = $true
    }
    if ($ContinueOnFailure) {
        $runArgs.ContinueOnRunFailure = $true
    }

    $familyExit = 0
    $familyException = ""
    try {
        .\scripts\run_family_stage_triplet.ps1 @runArgs
        $familyExit = $LASTEXITCODE
    } catch {
        $familyExit = 1
        $familyException = "$_"
        if (-not $ContinueOnFailure) {
            throw
        }
        Write-Warning "Family $family encountered an exception and will be marked failed."
    }

    $candidateStatus = "MISSING"
    if (Test-Path $candidateOut) {
        try {
            $candidateStatus = (Get-Content -Raw -Path $candidateOut | ConvertFrom-Json).status
        } catch {
            $candidateStatus = "INVALID"
        }
    }

    if ($candidateStatus -ne "PASS") {
        $overallPass = $false
    }
    if (($familyExit -ne 0) -and (-not $ContinueOnFailure)) {
        $overallPass = $false
    }

    $familyRows += [ordered]@{
        family = $family
        candidate_path = $candidateOut
        candidate_status = $candidateStatus
        script_exit = $familyExit
        exception = $familyException
    }
}

$reliabilitySignalStatus = "SKIPPED"
$reliabilitySignalExit = 0
$reliabilitySignalPath = "runs\reliability_signal_latest.json"
if (-not $SkipReliabilitySignal) {
    Write-Host ""
    Write-Host "Running unified reliability signal with derived R/P floors..."
    $signalArgs = @(
        ".\scripts\check_reliability_signal.py",
        "--strict", "runs\latest_rag_strict",
        "--compression-reliability", "runs\compression_reliability_latest.json",
        "--novel-reliability", "runs\novel_continuity_reliability_latest.json",
        "--authority-interference-reliability", "runs\authority_under_interference_reliability_latest.json",
        "--compression-roundtrip-reliability", "runs\compression_roundtrip_generalization_reliability_latest.json",
        "--novel-long-horizon-reliability", "runs\novel_continuity_long_horizon_reliability_latest.json",
        "--myopic-planning-reliability", "runs\myopic_planning_traps_reliability_latest.json",
        "--referential-indexing-reliability", "runs\referential_indexing_suite_reliability_latest.json",
        "--epistemic-reliability", "runs\epistemic_calibration_suite_reliability_latest.json",
        "--authority-hardening-reliability", "runs\authority_under_interference_hardening_reliability_latest.json",
        "--require-compression-roundtrip",
        "--require-novel-long-horizon",
        "--require-myopic-planning",
        "--require-referential-indexing",
        "--require-epistemic",
        "--require-authority-hardening",
        "--min-reasoning-score", "$MinReasoningScore",
        "--min-planning-score", "$MinPlanningScore",
        "--min-intelligence-index", "$MinIntelligenceIndex",
        "--out", $reliabilitySignalPath
    )
    python @signalArgs | Out-Host
    $reliabilitySignalExit = $LASTEXITCODE
    if (Test-Path $reliabilitySignalPath) {
        try {
            $reliabilitySignalStatus = (Get-Content -Raw -Path $reliabilitySignalPath | ConvertFrom-Json).status
        } catch {
            $reliabilitySignalStatus = "INVALID"
        }
    } else {
        $reliabilitySignalStatus = "MISSING"
    }
    if ($reliabilitySignalStatus -ne "PASS") {
        $overallPass = $false
    }
}

$payload = [ordered]@{
    generated_at = (Get-Date).ToString("o")
    stage = $Stage
    run_count = $RunCount
    max_jitter = $MaxJitter
    min_reasoning_score = $MinReasoningScore
    min_planning_score = $MinPlanningScore
    min_intelligence_index = $MinIntelligenceIndex
    families = $familyRows
    reliability_signal = [ordered]@{
        status = $reliabilitySignalStatus
        exit_code = $reliabilitySignalExit
        path = $reliabilitySignalPath
    }
    status = if ($overallPass) { "PASS" } else { "FAIL" }
}

$outDir = [System.IO.Path]::GetDirectoryName($Out)
if ($outDir) {
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
}
$payload | ConvertTo-Json -Depth 8 | Set-Content -Path $Out -Encoding UTF8
Write-Host "Wrote $Out"

if (-not $overallPass) {
    exit 1
}
