<#
.SYNOPSIS
Demonstrates a "bad actor" config that passes a general wall but fails the drift holdout gate.

.DESCRIPTION
Runs a light drift wall sweep (general coverage), then runs the drift holdout gate
with fixes disabled to simulate a model/config that ignores mitigations.

.PARAMETER ModelPath
Path to GGUF model for LLM-dependent checks.

.PARAMETER HoldoutName
Drift holdout name (default: stale_tab_state).

.PARAMETER WallSteps
Steps for the drift wall (default: 80).

.PARAMETER GenerateReports
Generate report.md for the holdout snapshot.

.PARAMETER OutRoot
Optional root folder to store artifacts (defaults to runs/bad_actor_*).

.PARAMETER AllowWallFail
Continue even if the drift wall exceeds its threshold.

.PARAMETER WallMaxOverride
Optional override for the drift wall max threshold.
#>
param(
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL,
    [ValidateSet("stale_tab_state", "focus_drift")]
    [string]$HoldoutName = "stale_tab_state",
    [int[]]$WallSteps = @(80),
    [switch]$GenerateReports,
    [string]$OutRoot = "",
    [switch]$AllowWallFail,
    [double]$WallMaxOverride = [double]::NaN
)

if (-not $ModelPath) {
    Write-Error "Set -ModelPath or GOLDEVIDENCEBENCH_MODEL before running."
    exit 1
}

function Get-DriftMax {
    param([string]$ConfigPath)
    $fallback = 0.25
    if (-not (Test-Path $ConfigPath)) {
        return $fallback
    }
    try {
        $config = Get-Content -Raw -Path $ConfigPath | ConvertFrom-Json
        $check = $config.checks | Where-Object { $_.id -eq "drift_gate" } | Select-Object -First 1
        if (-not $check) {
            return $fallback
        }
        $metric = $check.metrics | Where-Object { $_.path -eq "drift.step_rate" } | Select-Object -First 1
        if ($metric -and $null -ne $metric.max) {
            return [double]$metric.max
        }
    } catch {
        return $fallback
    }
    return $fallback
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
if ($OutRoot) {
    New-Item -ItemType Directory -Path $OutRoot -Force | Out-Null
    $wallDir = Join-Path $OutRoot "wall"
} else {
    $wallDir = "runs\\bad_actor_wall_$stamp"
}

Write-Host "Bad actor demo: drift wall (general coverage)"
.\scripts\run_drift_wall.ps1 -ModelPath $ModelPath -RunsDir $wallDir -Steps $WallSteps | Out-Host
if ($LASTEXITCODE -ne 0) {
    Write-Error "Drift wall run failed."
    exit 1
}

$driftMax = if (-not [double]::IsNaN($WallMaxOverride)) { $WallMaxOverride } else { Get-DriftMax -ConfigPath ".\\configs\\usecase_checks.json" }
$wallSummary = "runs\\drift_wall_latest\\summary.json"
if (-not (Test-Path $wallSummary)) {
    Write-Error "Missing drift wall summary: $wallSummary"
    exit 1
}
$wallData = Get-Content -Raw -Path $wallSummary | ConvertFrom-Json
$wallRate = if ($wallData.drift) { [double]$wallData.drift.step_rate } else { $null }
if ($null -eq $wallRate) {
    Write-Error "Drift wall summary missing drift.step_rate."
    exit 1
}
Write-Host ("Drift wall rate: {0} (max {1})" -f $wallRate, $driftMax)
if ($wallRate -gt $driftMax) {
    if ($AllowWallFail) {
        Write-Host "Drift wall exceeded threshold; continuing because -AllowWallFail is set."
    } else {
        Write-Error "Drift wall exceeded threshold; demo requires a passing wall."
        exit 1
    }
}

$gateScript = Join-Path $PSScriptRoot "run_drift_holdout_gate.ps1"
if ($OutRoot) {
    $badRunsDir = Join-Path $OutRoot "holdout"
} else {
    $badRunsDir = "runs\\bad_actor_holdout_$stamp"
}
$badGateArtifact = Join-Path $badRunsDir "drift_holdout_gate.json"
$badLatestDir = Join-Path $badRunsDir "drift_holdout_latest"

Write-Host "Bad actor demo: drift holdout (FAIL expected; fixes disabled)"
& $gateScript -ModelPath $ModelPath -HoldoutName $HoldoutName -RunsDir $badRunsDir `
    -GateArtifactPath $badGateArtifact -LatestDir $badLatestDir `
    -FixAuthorityFilter:$false -FixPreferRerank "latest_step" | Out-Host
$badCode = $LASTEXITCODE

if ($GenerateReports) {
    & python .\scripts\generate_report.py --run-dir $badLatestDir | Out-Host
}

if ($badCode -eq 0) {
    Write-Error "Bad actor demo unexpectedly passed."
    exit 1
}

Write-Host "Bad actor artifacts:"
Write-Host "  $badGateArtifact"
Write-Host "  $badLatestDir"
