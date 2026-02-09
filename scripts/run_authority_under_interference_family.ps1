param(
    [string]$OutRoot = "",
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL,
    [string]$Adapter = "goldevidencebench.adapters.llama_server_adapter:create_adapter",
    [string]$Protocol = "closed_book",
    [int]$MaxSupportK = 16,
    [switch]$OverwriteFixtures,
    [double]$AnchorsMinValueAcc = 0.85,
    [double]$AnchorsMinExactAcc = 0.85,
    [double]$AnchorsMinCiteF1 = 0.80,
    [double]$AnchorsMinLatestSupportHitRate = 0.80,
    [double]$AnchorsMaxNoteCitationRate = 0.10,
    [double]$AnchorsMaxStaleCitationRate = 0.10,
    [double]$AnchorsMaxAuthorityViolationRate = 0.10,
    [double]$HoldoutMinValueAcc = 0.90,
    [double]$HoldoutMinExactAcc = 0.90,
    [double]$HoldoutMinCiteF1 = 0.85,
    [double]$HoldoutMinLatestSupportHitRate = 0.90,
    [double]$HoldoutMaxNoteCitationRate = 0.05,
    [double]$HoldoutMaxStaleCitationRate = 0.05,
    [double]$HoldoutMaxAuthorityViolationRate = 0.05,
    [double]$CanaryAlertExactRate = 0.85
)

$ErrorActionPreference = "Stop"

function Invoke-PythonChecked {
    param([string[]]$CommandArgs, [string]$StepName)
    python @CommandArgs | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Step failed ($StepName) with exit code $LASTEXITCODE."
    }
}

function Invoke-PythonSoftFail {
    param([string[]]$CommandArgs, [string]$StepName)
    python @CommandArgs | Out-Host
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        Write-Warning "Step failed ($StepName) with exit code $exitCode. Continuing to collect remaining artifacts."
    }
    return $exitCode
}

function Read-JsonFile {
    param([string]$Path)
    return (Get-Content -Raw -Path $Path | ConvertFrom-Json)
}

if (-not $OutRoot) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutRoot = "runs\authority_under_interference_$stamp"
}

if ($ModelPath) {
    $env:GOLDEVIDENCEBENCH_MODEL = $ModelPath
}

New-Item -ItemType Directory -Path $OutRoot -Force | Out-Null

$anchorsData = "data\authority_under_interference\authority_under_interference_anchors.jsonl"
$holdoutData = "data\authority_under_interference\authority_under_interference_holdout.jsonl"
$canaryData = "data\authority_under_interference\authority_under_interference_canary.jsonl"
$needGenerate = $OverwriteFixtures -or -not ((Test-Path $anchorsData) -and (Test-Path $holdoutData) -and (Test-Path $canaryData))

Write-Host "Authority under interference run"
Write-Host "OutRoot: $OutRoot"
Write-Host "Adapter: $Adapter"
Write-Host "Protocol: $Protocol"
Write-Host "MaxSupportK: $MaxSupportK"

if ($needGenerate) {
    $genArgs = @(".\scripts\generate_authority_under_interference_family.py")
    if ($OverwriteFixtures) { $genArgs += "--overwrite" }
    Invoke-PythonChecked -StepName "generate_authority_under_interference_family" -CommandArgs $genArgs
} else {
    Write-Host "Using existing authority_under_interference fixtures."
}

$anchorsPreds = Join-Path $OutRoot "anchors_preds.jsonl"
$holdoutPreds = Join-Path $OutRoot "holdout_preds.jsonl"
$canaryPreds = Join-Path $OutRoot "canary_preds.jsonl"
$anchorsSummary = Join-Path $OutRoot "anchors_summary.json"
$holdoutSummary = Join-Path $OutRoot "holdout_summary.json"
$canarySummary = Join-Path $OutRoot "canary_summary.json"

Invoke-PythonChecked -StepName "model_anchors" -CommandArgs @(
    "-m", "goldevidencebench.cli", "model",
    "--data", $anchorsData,
    "--adapter", $Adapter,
    "--protocol", $Protocol,
    "--citations", "auto",
    "--max-support-k", "$MaxSupportK",
    "--out", $anchorsPreds
)
$scoreAnchorsExit = Invoke-PythonSoftFail -StepName "score_anchors" -CommandArgs @(
    ".\scripts\score_authority_under_interference.py",
    "--data", $anchorsData,
    "--preds", $anchorsPreds,
    "--out", $anchorsSummary,
    "--rows-out", (Join-Path $OutRoot "anchors_rows.jsonl"),
    "--min-value-acc", "$AnchorsMinValueAcc",
    "--min-exact-acc", "$AnchorsMinExactAcc",
    "--min-cite-f1", "$AnchorsMinCiteF1",
    "--min-latest-support-hit-rate", "$AnchorsMinLatestSupportHitRate",
    "--max-note-citation-rate", "$AnchorsMaxNoteCitationRate",
    "--max-stale-citation-rate", "$AnchorsMaxStaleCitationRate",
    "--max-authority-violation-rate", "$AnchorsMaxAuthorityViolationRate"
)

Invoke-PythonChecked -StepName "model_holdout" -CommandArgs @(
    "-m", "goldevidencebench.cli", "model",
    "--data", $holdoutData,
    "--adapter", $Adapter,
    "--protocol", $Protocol,
    "--citations", "auto",
    "--max-support-k", "$MaxSupportK",
    "--out", $holdoutPreds
)
$scoreHoldoutExit = Invoke-PythonSoftFail -StepName "score_holdout" -CommandArgs @(
    ".\scripts\score_authority_under_interference.py",
    "--data", $holdoutData,
    "--preds", $holdoutPreds,
    "--out", $holdoutSummary,
    "--rows-out", (Join-Path $OutRoot "holdout_rows.jsonl"),
    "--min-value-acc", "$HoldoutMinValueAcc",
    "--min-exact-acc", "$HoldoutMinExactAcc",
    "--min-cite-f1", "$HoldoutMinCiteF1",
    "--min-latest-support-hit-rate", "$HoldoutMinLatestSupportHitRate",
    "--max-note-citation-rate", "$HoldoutMaxNoteCitationRate",
    "--max-stale-citation-rate", "$HoldoutMaxStaleCitationRate",
    "--max-authority-violation-rate", "$HoldoutMaxAuthorityViolationRate"
)

Invoke-PythonChecked -StepName "model_canary" -CommandArgs @(
    "-m", "goldevidencebench.cli", "model",
    "--data", $canaryData,
    "--adapter", $Adapter,
    "--protocol", $Protocol,
    "--citations", "auto",
    "--max-support-k", "$MaxSupportK",
    "--out", $canaryPreds
)
$scoreCanaryExit = Invoke-PythonSoftFail -StepName "score_canary" -CommandArgs @(
    ".\scripts\score_authority_under_interference.py",
    "--data", $canaryData,
    "--preds", $canaryPreds,
    "--out", $canarySummary,
    "--rows-out", (Join-Path $OutRoot "canary_rows.jsonl")
)

if (-not (Test-Path $anchorsSummary)) { throw "Missing anchors summary: $anchorsSummary" }
if (-not (Test-Path $holdoutSummary)) { throw "Missing holdout summary: $holdoutSummary" }
if (-not (Test-Path $canarySummary)) { throw "Missing canary summary: $canarySummary" }

$anchorsObj = Read-JsonFile -Path $anchorsSummary
$holdoutObj = Read-JsonFile -Path $holdoutSummary
$canaryObj = Read-JsonFile -Path $canarySummary

$hardGatePass = ($anchorsObj.status -eq "PASS") -and ($holdoutObj.status -eq "PASS")
$canaryExact = [double]$canaryObj.means.exact_acc
$canaryAlert = $canaryExact -ge $CanaryAlertExactRate
$canaryStatus = if ($canaryAlert) { "WARN" } else { "OK" }

$combined = [ordered]@{
    benchmark = "authority_under_interference"
    generated_at = (Get-Date).ToString("o")
    out_root = (Resolve-Path $OutRoot).Path
    adapter = $Adapter
    protocol = $Protocol
    hard_gate_status = if ($hardGatePass) { "PASS" } else { "FAIL" }
    canary_status = $canaryStatus
    canary_alert_exact_rate = $CanaryAlertExactRate
    anchors = $anchorsObj
    holdout = $holdoutObj
    canary = $canaryObj
    canary_exact_rate = $canaryExact
    canary_alert = $canaryAlert
}

$combinedPath = Join-Path $OutRoot "authority_under_interference_summary.json"
$combined | ConvertTo-Json -Depth 12 | Set-Content -Path $combinedPath -Encoding UTF8
Write-Host "Wrote $combinedPath"
Write-Host ("hard_gate_status={0} canary_status={1}" -f $combined.hard_gate_status, $combined.canary_status)

if (-not $hardGatePass) {
    exit 1
}

if (($scoreAnchorsExit -ne 0) -or ($scoreHoldoutExit -ne 0) -or ($scoreCanaryExit -ne 0)) {
    exit 1
}

exit 0
