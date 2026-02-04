<#
.SYNOPSIS
Runs the focused regression gate suite.

.DESCRIPTION
Wrapper around run_release_check.ps1 with defaults tuned for regression gating.
Skips heavy UI variants unless -RunVariants is set.

.PARAMETER ModelPath
Path to GGUF model for LLM-dependent checks.

.PARAMETER SkipDriftGate
Skip the drift holdout gate (enabled by default).

.PARAMETER RunVariants
Include UI local-optimum variants (slow).

#>
param(
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL,
    [switch]$SkipDriftGate,
    [switch]$RunVariants
)

if (-not $ModelPath) {
    Write-Error "Set -ModelPath or GOLDEVIDENCEBENCH_MODEL."
    exit 1
}

$releaseArgs = @{
    ModelPath = $ModelPath
}

if (-not $SkipDriftGate) {
    $releaseArgs.RunDriftHoldoutGate = $true
}
if (-not $RunVariants) {
    $releaseArgs.SkipVariants = $true
}

Write-Host "Running regression check..."
.\scripts\run_release_check.ps1 @releaseArgs
$exitCode = $LASTEXITCODE

$latestReleaseFile = "runs\\latest_release"
if (Test-Path $latestReleaseFile) {
    $latestRelease = (Get-Content -Path $latestReleaseFile -Raw).Trim()
    if ($latestRelease) {
        .\scripts\set_latest_pointer.ps1 -RunDir $latestRelease -PointerPath "runs\\latest_regression" | Out-Host
    }
}

exit $exitCode
