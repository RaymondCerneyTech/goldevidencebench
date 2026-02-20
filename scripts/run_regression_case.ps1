<#
.SYNOPSIS
Runs a reproducible regression case by toggling fix configs.

.DESCRIPTION
Runs a PASS baseline drift holdout gate, then re-runs with a config
regression (authority fix disabled + prefer_set_latest disabled).
This produces a FAIL that is caught by the gate.

.PARAMETER ModelPath
Path to GGUF model for LLM-dependent checks.

.PARAMETER HoldoutName
Drift holdout name (default: stale_tab_state).

.PARAMETER GenerateReports
Generate report.md for PASS/FAIL snapshots.

.PARAMETER ComparePassFail
Generate a delta_report.md comparing PASS vs FAIL snapshots.
#>
param(
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL,
    [string]$Adapter = "goldevidencebench.adapters.retrieval_llama_cpp_adapter:create_adapter",
    [ValidateSet("stale_tab_state", "focus_drift")]
    [string]$HoldoutName = "stale_tab_state",
    [string]$OutRoot = "",
    [switch]$GenerateReports,
    [switch]$ComparePassFail
)

$supportsDriftDiagnostics = $Adapter -like "*retrieval_llama_cpp_adapter*"
if (-not $supportsDriftDiagnostics) {
    Write-Error ("Regression case requires retrieval_llama_cpp_adapter (drift diagnostics are adapter-specific). Adapter='{0}'." -f $Adapter)
    exit 1
}

$requiresModelPath = $Adapter -like "*llama_cpp*"
if ($requiresModelPath -and -not $ModelPath) {
    Write-Error "Set -ModelPath or GOLDEVIDENCEBENCH_MODEL before running with llama_cpp adapters."
    exit 1
}
if ($ModelPath) {
    $env:GOLDEVIDENCEBENCH_MODEL = $ModelPath
}

$gateScript = Join-Path $PSScriptRoot "run_drift_holdout_gate.ps1"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
if ($OutRoot) {
    $passRunsDir = Join-Path $OutRoot "pass"
    $failRunsDir = Join-Path $OutRoot "fail"
    New-Item -ItemType Directory -Path $passRunsDir -Force | Out-Null
    New-Item -ItemType Directory -Path $failRunsDir -Force | Out-Null
} else {
    $passRunsDir = "runs\\regression_case_pass_$stamp"
    $failRunsDir = "runs\\regression_case_fail_$stamp"
}
$passGateArtifact = Join-Path $passRunsDir "drift_holdout_gate.json"
$passLatestDir = Join-Path $passRunsDir "drift_holdout_latest"

Write-Host "Regression case (PASS baseline expected)"
$passArgs = @{
    Adapter = $Adapter
    HoldoutName = $HoldoutName
    RunsDir = $passRunsDir
    GateArtifactPath = $passGateArtifact
    LatestDir = $passLatestDir
}
if ($ModelPath) {
    $passArgs.ModelPath = $ModelPath
}
& $gateScript @passArgs | Out-Host
$passCode = $LASTEXITCODE
if ($passCode -ne 0) {
    Write-Error "Baseline run failed; cannot demonstrate regression."
    exit $passCode
}

if ($GenerateReports) {
    & python .\scripts\generate_report.py --run-dir $passLatestDir | Out-Host
}

$failGateArtifact = Join-Path $failRunsDir "drift_holdout_gate.json"
$failLatestDir = Join-Path $failRunsDir "drift_holdout_latest"

Write-Host "Regression case (FAIL expected; fixes disabled)"
$failArgs = @{
    Adapter = $Adapter
    HoldoutName = $HoldoutName
    RunsDir = $failRunsDir
    GateArtifactPath = $failGateArtifact
    LatestDir = $failLatestDir
    FixAuthorityFilter = $false
    FixPreferRerank = "latest_step"
}
if ($ModelPath) {
    $failArgs.ModelPath = $ModelPath
}
& $gateScript @failArgs | Out-Host
$failCode = $LASTEXITCODE

if ($GenerateReports) {
    & python .\scripts\generate_report.py --run-dir $failLatestDir | Out-Host
}

if ($ComparePassFail) {
    & python .\scripts\compare_runs.py --base $passLatestDir --other $failLatestDir --allow-missing-diagnosis | Out-Host
}

if ($failCode -eq 0) {
    Write-Error "Regression case unexpectedly passed; fixes may not be exercising drift."
    exit 1
}

Write-Host "PASS artifacts:"
Write-Host "  $passGateArtifact"
Write-Host "  $passLatestDir"
Write-Host "FAIL artifacts:"
Write-Host "  $failGateArtifact"
Write-Host "  $failLatestDir"
