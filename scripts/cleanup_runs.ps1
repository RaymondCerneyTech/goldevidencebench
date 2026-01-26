<#
.SYNOPSIS
Cleans run artifacts under runs/.

.DESCRIPTION
Lists run folders and optionally removes them. Keeps runs\release_gates by
default. Use -Execute to delete, or -DryRun to preview without changes.

.PARAMETER RunsRoot
Root directory for run outputs (default: runs).

.PARAMETER KeepLatest
Keep the N most recent run folders (by LastWriteTime).

.PARAMETER OlderThanDays
Only delete runs older than N days.

.PARAMETER IncludeReleaseGates
Include runs\release_gates in deletion.

.PARAMETER IncludeWalls
Include runs_wall* folders at repo root.

.PARAMETER Execute
Actually remove the selected run folders.

.PARAMETER DryRun
Print what would be removed (overrides -Execute).
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$RunsRoot = "runs",
    [int]$KeepLatest = 0,
    [int]$OlderThanDays = 0,
    [switch]$IncludeReleaseGates,
    [switch]$IncludeWalls,
    [switch]$Execute,
    [switch]$DryRun
)

$root = Resolve-Path -Path $RunsRoot -ErrorAction Stop

$runDirs = Get-ChildItem -Path $root -Directory
if (-not $IncludeReleaseGates) {
    $runDirs = $runDirs | Where-Object { $_.Name -ne "release_gates" }
}

if ($OlderThanDays -gt 0) {
    $cutoff = (Get-Date).AddDays(-$OlderThanDays)
    $runDirs = $runDirs | Where-Object { $_.LastWriteTime -lt $cutoff }
}

if ($KeepLatest -gt 0) {
    $keep = $runDirs | Sort-Object LastWriteTime -Descending | Select-Object -First $KeepLatest
    $runDirs = $runDirs | Where-Object { $keep -notcontains $_ }
}

$wallDirs = @()
if ($IncludeWalls) {
    $wallDirs = Get-ChildItem -Path . -Directory -Filter "runs_wall*" -ErrorAction SilentlyContinue
}

$targets = @($runDirs + $wallDirs)
if ($targets.Count -eq 0) {
    Write-Host "No run folders to remove."
    exit 0
}

Write-Host "Run folders selected:"
$targets | ForEach-Object { Write-Host " - $($_.FullName)" }

if ($DryRun -or -not $Execute) {
    Write-Host "Dry run only. Re-run with -Execute to delete."
    exit 0
}

if (-not $PSCmdlet.ShouldProcess($root.Path, "Remove $($targets.Count) run folder(s)")) {
    exit 1
}

foreach ($target in $targets) {
    Remove-Item -LiteralPath $target.FullName -Recurse -Force -ErrorAction Stop
}

Write-Host "Removed $($targets.Count) run folder(s)."
