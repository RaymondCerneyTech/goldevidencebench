param(
    [string]$ConfigPath = "configs\\trap_contract_audit_jobs.json",
    [string]$Root = ".",
    [string]$OutPath = "runs\\trap_contract_audit_latest.json",
    [string]$MarkdownOutPath = "runs\\trap_contract_audit_latest.md",
    [switch]$FailOnNoData,
    [switch]$AllowFail
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $ConfigPath)) {
    Write-Error "Trap audit config not found: $ConfigPath"
    exit 1
}

$args = @(
    ".\scripts\build_trap_contract_audit.py",
    "--config", $ConfigPath,
    "--root", $Root,
    "--out", $OutPath,
    "--markdown-out", $MarkdownOutPath
)
if ($FailOnNoData) {
    $args += "--fail-on-no-data"
}

Write-Host "Building trap contract audit..."
python @args | Out-Host
$auditExit = $LASTEXITCODE
if ($auditExit -ne 0 -and -not $AllowFail) {
    Write-Error "Trap contract audit failed."
    exit $auditExit
}

if (-not (Test-Path $OutPath)) {
    Write-Error "Missing trap contract audit artifact: $OutPath"
    exit 1
}

$report = Get-Content -Raw -Path $OutPath | ConvertFrom-Json
$status = "$($report.status)"
$trapCount = 0
if ($report.summary -and ($report.summary.PSObject.Properties.Name -contains "trap_count")) {
    $trapCount = [int]$report.summary.trap_count
}

.\scripts\set_latest_pointer.ps1 -RunDir $OutPath -PointerPath "runs\\latest_trap_contract_audit" | Out-Host
if (Test-Path $MarkdownOutPath) {
    .\scripts\set_latest_pointer.ps1 -RunDir $MarkdownOutPath -PointerPath "runs\\latest_trap_contract_audit_md" | Out-Host
}

Write-Host ("trap_contract_audit status={0} traps={1} report={2}" -f $status, $trapCount, $OutPath)
if ($auditExit -ne 0 -and $AllowFail) {
    exit 0
}
exit $auditExit
