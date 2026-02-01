<#
.SYNOPSIS
Compare the two most recent case pack runs and emit a delta report.

.DESCRIPTION
Uses runs\case_pack_latest.txt for the "other" run when available,
then finds the previous case_pack_* folder for the base.

.PARAMETER RunsRoot
Root runs folder (default: runs).

.PARAMETER Full
Include unchanged metrics in the delta report.

.PARAMETER Print
Print the delta report to stdout.

.PARAMETER Out
Optional output markdown path.
#>
param(
    [string]$RunsRoot = "runs",
    [switch]$Canonical,
    [switch]$Full,
    [switch]$Print,
    [string]$Out = ""
)

$canonicalBase = Join-Path $RunsRoot "case_pack_20260129_205412"
$canonicalOther = Join-Path $RunsRoot "case_pack_20260129_210655"

if ($Canonical) {
    if (-not (Test-Path -LiteralPath $canonicalBase)) {
        Write-Error "Canonical base run not found: $canonicalBase"
        exit 1
    }
    if (-not (Test-Path -LiteralPath $canonicalOther)) {
        Write-Error "Canonical other run not found: $canonicalOther"
        exit 1
    }
    $otherPath = (Resolve-Path -LiteralPath $canonicalOther).Path
    $base = (Resolve-Path -LiteralPath $canonicalBase).Path
} else {
    $latestFile = Join-Path $RunsRoot "case_pack_latest.txt"
    $other = ""
    if (Test-Path $latestFile) {
        $other = (Get-Content -Path $latestFile -Raw).Trim()
    }
    if (-not $other) {
        $other = (Get-ChildItem $RunsRoot -Directory | Where-Object Name -like "case_pack_*" |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
    }
    if (-not $other) {
        Write-Error "Could not resolve latest case pack run."
        exit 1
    }
    $otherPath = $null
    try {
        $otherPath = (Resolve-Path -LiteralPath $other).Path
    } catch {
        $otherPath = $null
    }
    if (-not $otherPath) {
        Write-Error "Could not resolve latest case pack run path: $other"
        exit 1
    }

    $base = (Get-ChildItem $RunsRoot -Directory | Where-Object Name -like "case_pack_*" |
        Sort-Object LastWriteTime -Descending | Where-Object { $_.FullName -ne $otherPath } |
        Select-Object -First 1).FullName
    if (-not $base) {
        Write-Error "Could not resolve base case pack run."
        exit 1
    }
}

Write-Host "Base: $base"
Write-Host "Other: $otherPath"

$pyArgs = @(".\\scripts\\compare_runs.py", "--base", $base, "--other", $otherPath)
if ($Full) {
    $pyArgs += "--full"
}
if ($Print) {
    $pyArgs += "--print"
}
if ($Out) {
    $pyArgs += @("--out", $Out)
}

python @pyArgs
$exitCode = $LASTEXITCODE
if ($Canonical -and ($exitCode -eq 0)) {
    Write-Host "Regression detected: wall_rate increased"
}
exit $exitCode
