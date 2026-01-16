param(
    [string]$BacklogPath = "docs\\TRAP_FAMILIES.md"
)

if (-not (Test-Path $BacklogPath)) {
    Write-Error "Backlog file not found: $BacklogPath"
    exit 1
}

$lines = Get-Content $BacklogPath
$next = $lines | Where-Object { $_ -match "^\s*-\s*\[ \]\s+" } | Select-Object -First 1
if (-not $next) {
    Write-Host "All trap families are marked done."
    exit 0
}

Write-Host "Next trap family:"
Write-Host $next
