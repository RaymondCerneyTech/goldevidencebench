[CmdletBinding()]
param(
    [string]$BaseDir = $env:RUN_BASE,
    [string]$RunDir = $env:RUN_NEW,
    [string]$Stamp = $null,
    [switch]$AllowDuplicate
)

$scriptPath = Join-Path $PSScriptRoot "append_run_log_summary.py"
if (-not (Test-Path $scriptPath)) {
    throw "Missing script: $scriptPath"
}
if (-not $BaseDir -or -not $RunDir) {
    throw "Set -BaseDir and -RunDir (or RUN_BASE/RUN_NEW env vars)."
}

$argsList = @($scriptPath, "--base-dir", $BaseDir, "--run-dir", $RunDir)
if ($Stamp) {
    $argsList += @("--stamp", $Stamp)
}
if ($AllowDuplicate) {
    $argsList += "--allow-duplicate"
}

python @argsList
