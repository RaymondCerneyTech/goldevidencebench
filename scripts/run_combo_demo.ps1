param(
    [string]$ModelPath = "",
    [string]$Text = "Hello from GoldEvidenceBench.",
    [string]$FilePath = "",
    [ValidateSet("prompt","rename","overwrite")]
    [string]$OnExistingFile = "rename",
    [ValidateSet("paste","type")]
    [string]$InputMode = "type",
    [switch]$VerifySaved,
    [switch]$CloseAfterSave,
    [string]$Expression = "12+34",
    [string]$Expected = "46",
    [switch]$VerifyResult,
    [switch]$CloseAfter,
    [switch]$DisableKeystrokeGate,
    [switch]$DryRun
)

$repoRoot = Split-Path $PSScriptRoot -Parent
$notepadScript = Join-Path $repoRoot "scripts\\run_notepad_demo.ps1"
$calculatorScript = Join-Path $repoRoot "scripts\\run_calculator_demo.ps1"

if (-not (Test-Path $notepadScript)) {
    Write-Error "Missing notepad demo script: $notepadScript"
    exit 1
}
if (-not (Test-Path $calculatorScript)) {
    Write-Error "Missing calculator demo script: $calculatorScript"
    exit 1
}

Write-Host "Running Notepad demo..."
$notepadArgs = @{
    ModelPath = $ModelPath
    Text = $Text
    FilePath = $FilePath
    OnExistingFile = $OnExistingFile
    InputMode = $InputMode
    VerifySaved = $VerifySaved
    CloseAfterSave = $CloseAfterSave
}
if ($DisableKeystrokeGate) {
    $notepadArgs["DisableKeystrokeGate"] = $true
}
if ($DryRun) {
    $notepadArgs["DryRun"] = $true
}
& $notepadScript @notepadArgs
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Running Calculator demo..."
$calcArgs = @{
    Expression = $Expression
    Expected = $Expected
    VerifyResult = $VerifyResult
    CloseAfter = $CloseAfter
}
if ($DisableKeystrokeGate) {
    $calcArgs["DisableKeystrokeGate"] = $true
}
if ($DryRun) {
    $calcArgs["DryRun"] = $true
}
& $calculatorScript @calcArgs
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Combo demo complete."
