<#
.SYNOPSIS
Runs a minimal regression demo (PASS) and optional FAIL demo.

.DESCRIPTION
PASS demo runs the drift holdout gate with default thresholds and writes
artifacts under runs\demo_regression_pass_<timestamp>.
FAIL demo (optional) sets CanaryMin high to intentionally fail and writes
artifacts under runs\demo_regression_fail_<timestamp>.

.PARAMETER ModelPath
Path to GGUF model for LLM-dependent checks.

.PARAMETER HoldoutName
Drift holdout name (default: stale_tab_state).

.PARAMETER IncludeFailDemo
Run an intentional FAIL demo (CanaryMin set high).

.PARAMETER FailCanaryMin
CanaryMin threshold for the FAIL demo (default: 1.1).

.PARAMETER GenerateReports
Generate report.md for the PASS (and FAIL, if run) snapshots.

.PARAMETER ComparePassFail
Generate a delta_report.md comparing PASS vs FAIL (if fail demo runs).
#>
param(
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL,
    [ValidateSet("stale_tab_state", "focus_drift")]
    [string]$HoldoutName = "stale_tab_state",
    [switch]$IncludeFailDemo,
    [double]$FailCanaryMin = 1.1,
    [switch]$GenerateReports,
    [switch]$ComparePassFail
)

if (-not $ModelPath) {
    Write-Error "Set -ModelPath or GOLDEVIDENCEBENCH_MODEL before running."
    exit 1
}

$gateScript = Join-Path $PSScriptRoot "run_drift_holdout_gate.ps1"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"

$passRunsDir = "runs\\demo_regression_pass_$stamp"
$passGateArtifact = Join-Path $passRunsDir "drift_holdout_gate.json"
$passLatestDir = Join-Path $passRunsDir "drift_holdout_latest"

Write-Host "Regression demo (PASS expected)"
& $gateScript -ModelPath $ModelPath -HoldoutName $HoldoutName -RunsDir $passRunsDir `
    -GateArtifactPath $passGateArtifact -LatestDir $passLatestDir | Out-Host
$passCode = $LASTEXITCODE

if ($passCode -ne 0) {
    Write-Error "PASS demo failed."
    exit $passCode
}

Write-Host "PASS artifacts:"
Write-Host "  $passGateArtifact"
Write-Host "  $passLatestDir"

if ($GenerateReports) {
    & python .\scripts\generate_report.py --run-dir $passLatestDir | Out-Host
}

if ($IncludeFailDemo) {
    $failRunsDir = "runs\\demo_regression_fail_$stamp"
    $failGateArtifact = Join-Path $failRunsDir "drift_holdout_gate.json"
    $failLatestDir = Join-Path $failRunsDir "drift_holdout_latest"

    Write-Host "Regression demo (FAIL expected; CanaryMin=$FailCanaryMin)"
    & $gateScript -ModelPath $ModelPath -HoldoutName $HoldoutName -RunsDir $failRunsDir `
        -GateArtifactPath $failGateArtifact -LatestDir $failLatestDir -CanaryMin $FailCanaryMin | Out-Host
    $failCode = $LASTEXITCODE

    Write-Host "FAIL artifacts:"
    Write-Host "  $failGateArtifact"
    Write-Host "  $failLatestDir"

    if ($GenerateReports) {
        & python .\scripts\generate_report.py --run-dir $failLatestDir | Out-Host
    }

    if ($ComparePassFail) {
        & python .\scripts\compare_runs.py --base $passLatestDir --other $failLatestDir --allow-missing-diagnosis | Out-Host
    }

    if ($failCode -eq 0) {
        Write-Error "FAIL demo unexpectedly passed (CanaryMin=$FailCanaryMin)."
        exit 1
    }
}
