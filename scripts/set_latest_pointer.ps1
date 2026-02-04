param(
    [Parameter(Mandatory = $true)][string]$RunDir,
    [Parameter(Mandatory = $true)][string]$PointerPath
)

$ErrorActionPreference = "Stop"

$resolved = $RunDir
if (Test-Path $RunDir) {
    $resolved = (Resolve-Path $RunDir).Path
}

$parent = Split-Path $PointerPath
if ($parent) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
}

Set-Content -Path $PointerPath -Value $resolved -Encoding UTF8
Write-Host "Latest pointer: $PointerPath -> $resolved"
