param(
    [string]$OutRoot = "",
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL,
    [string]$Adapter = "goldevidencebench.adapters.llama_server_adapter:create_adapter",
    [string]$Protocol = "closed_book",
    [int]$MaxSupportK = 64,
    [switch]$OverwriteFixtures,
    [double]$ClbMinPrecision = 0.90,
    [double]$ClbMinRecall = 0.90,
    [double]$ClbMaxBloat = 0.20,
    [double]$CrvAnchorsMinValueAcc = 0.85,
    [double]$CrvAnchorsMinExactAcc = 0.85,
    [double]$CrvAnchorsMinCiteF1 = 0.85,
    [double]$CrvHoldoutMinValueAcc = 0.90,
    [double]$CrvHoldoutMinExactAcc = 0.90,
    [double]$CrvHoldoutMinCiteF1 = 0.90,
    [double]$CanaryAlertExactRate = 0.95
)

$ErrorActionPreference = "Stop"

function Invoke-PythonChecked {
    param([string[]]$CommandArgs, [string]$StepName)
    python @CommandArgs | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Step failed ($StepName) with exit code $LASTEXITCODE."
    }
}

function Read-JsonFile {
    param([string]$Path)
    return (Get-Content -Raw -Path $Path | ConvertFrom-Json)
}

function Get-ExactRate {
    param($Summary)
    if ($null -eq $Summary -or $null -eq $Summary.means) {
        return [double]::NaN
    }
    $means = $Summary.means
    if ($means.PSObject.Properties.Name -contains "exact_match_rate") {
        return [double]$means.exact_match_rate
    }
    if ($means.PSObject.Properties.Name -contains "exact_acc") {
        return [double]$means.exact_acc
    }
    return [double]::NaN
}

if (-not $OutRoot) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutRoot = "runs\compression_families_$stamp"
}

if ($ModelPath) {
    $env:GOLDEVIDENCEBENCH_MODEL = $ModelPath
}

$clbOut = Join-Path $OutRoot "compression_loss_bounded"
$crvOut = Join-Path $OutRoot "compression_recoverability"
New-Item -ItemType Directory -Path $clbOut -Force | Out-Null
New-Item -ItemType Directory -Path $crvOut -Force | Out-Null

Write-Host "Compression families run"
Write-Host "OutRoot: $OutRoot"
Write-Host "Adapter: $Adapter"
Write-Host "Protocol: $Protocol"
Write-Host "MaxSupportK: $MaxSupportK"

$clbAnchorsData = "data\compression_loss_bounded\compression_loss_bounded_anchors.jsonl"
$clbHoldoutData = "data\compression_loss_bounded\compression_loss_bounded_holdout.jsonl"
$clbCanaryData = "data\compression_loss_bounded\compression_loss_bounded_canary.jsonl"
$crvAnchorsData = "data\compression_recoverability\compression_recoverability_anchors.jsonl"
$crvHoldoutData = "data\compression_recoverability\compression_recoverability_holdout.jsonl"
$crvCanaryData = "data\compression_recoverability\compression_recoverability_canary.jsonl"

$needGenerateClb = $OverwriteFixtures -or -not ((Test-Path $clbAnchorsData) -and (Test-Path $clbHoldoutData) -and (Test-Path $clbCanaryData))
$needGenerateCrv = $OverwriteFixtures -or -not ((Test-Path $crvAnchorsData) -and (Test-Path $crvHoldoutData) -and (Test-Path $crvCanaryData))

if ($needGenerateClb) {
    $genClbArgs = @(".\scripts\generate_compression_loss_bounded_family.py")
    if ($OverwriteFixtures) { $genClbArgs += "--overwrite" }
    Invoke-PythonChecked -StepName "generate_compression_loss_bounded_family" -CommandArgs $genClbArgs
} else {
    Write-Host "Using existing compression_loss_bounded fixtures."
}

if ($needGenerateCrv) {
    $genCrvArgs = @(".\scripts\generate_compression_recoverability_family.py")
    if ($OverwriteFixtures) { $genCrvArgs += "--overwrite" }
    Invoke-PythonChecked -StepName "generate_compression_recoverability_family" -CommandArgs $genCrvArgs
} else {
    Write-Host "Using existing compression_recoverability fixtures."
}

# compression_loss_bounded
$clbAnchorsPreds = Join-Path $clbOut "anchors_preds.jsonl"
$clbHoldoutPreds = Join-Path $clbOut "holdout_preds.jsonl"
$clbCanaryPreds = Join-Path $clbOut "canary_preds.jsonl"

$clbAnchorsSummary = Join-Path $clbOut "anchors_summary.json"
$clbHoldoutSummary = Join-Path $clbOut "holdout_summary.json"
$clbCanarySummary = Join-Path $clbOut "canary_summary.json"

Invoke-PythonChecked -StepName "clb_model_anchors" -CommandArgs @(
    "-m", "goldevidencebench.cli", "model",
    "--data", $clbAnchorsData,
    "--adapter", $Adapter,
    "--protocol", $Protocol,
    "--max-support-k", "$MaxSupportK",
    "--out", $clbAnchorsPreds
)
Invoke-PythonChecked -StepName "clb_score_anchors" -CommandArgs @(
    ".\scripts\score_compression_loss_bounded.py",
    "--data", $clbAnchorsData,
    "--preds", $clbAnchorsPreds,
    "--out", $clbAnchorsSummary,
    "--rows-out", (Join-Path $clbOut "anchors_rows.jsonl"),
    "--min-precision", "$ClbMinPrecision",
    "--min-recall", "$ClbMinRecall",
    "--max-bloat", "$ClbMaxBloat"
)

Invoke-PythonChecked -StepName "clb_model_holdout" -CommandArgs @(
    "-m", "goldevidencebench.cli", "model",
    "--data", $clbHoldoutData,
    "--adapter", $Adapter,
    "--protocol", $Protocol,
    "--max-support-k", "$MaxSupportK",
    "--out", $clbHoldoutPreds
)
Invoke-PythonChecked -StepName "clb_score_holdout" -CommandArgs @(
    ".\scripts\score_compression_loss_bounded.py",
    "--data", $clbHoldoutData,
    "--preds", $clbHoldoutPreds,
    "--out", $clbHoldoutSummary,
    "--rows-out", (Join-Path $clbOut "holdout_rows.jsonl"),
    "--min-precision", "$ClbMinPrecision",
    "--min-recall", "$ClbMinRecall",
    "--max-bloat", "$ClbMaxBloat"
)

Invoke-PythonChecked -StepName "clb_model_canary" -CommandArgs @(
    "-m", "goldevidencebench.cli", "model",
    "--data", $clbCanaryData,
    "--adapter", $Adapter,
    "--protocol", $Protocol,
    "--max-support-k", "$MaxSupportK",
    "--out", $clbCanaryPreds
)
Invoke-PythonChecked -StepName "clb_score_canary" -CommandArgs @(
    ".\scripts\score_compression_loss_bounded.py",
    "--data", $clbCanaryData,
    "--preds", $clbCanaryPreds,
    "--out", $clbCanarySummary,
    "--rows-out", (Join-Path $clbOut "canary_rows.jsonl")
)

# compression_recoverability
$crvAnchorsPreds = Join-Path $crvOut "anchors_preds.jsonl"
$crvHoldoutPreds = Join-Path $crvOut "holdout_preds.jsonl"
$crvCanaryPreds = Join-Path $crvOut "canary_preds.jsonl"

$crvAnchorsSummary = Join-Path $crvOut "anchors_summary.json"
$crvHoldoutSummary = Join-Path $crvOut "holdout_summary.json"
$crvCanarySummary = Join-Path $crvOut "canary_summary.json"

Invoke-PythonChecked -StepName "crv_model_anchors" -CommandArgs @(
    "-m", "goldevidencebench.cli", "model",
    "--data", $crvAnchorsData,
    "--adapter", $Adapter,
    "--protocol", $Protocol,
    "--max-support-k", "$MaxSupportK",
    "--out", $crvAnchorsPreds
)
Invoke-PythonChecked -StepName "crv_score_anchors" -CommandArgs @(
    ".\scripts\score_compression_recoverability.py",
    "--data", $crvAnchorsData,
    "--preds", $crvAnchorsPreds,
    "--out", $crvAnchorsSummary,
    "--rows-out", (Join-Path $crvOut "anchors_rows.jsonl"),
    "--min-value-acc", "$CrvAnchorsMinValueAcc",
    "--min-exact-acc", "$CrvAnchorsMinExactAcc",
    "--min-cite-f1", "$CrvAnchorsMinCiteF1"
)

Invoke-PythonChecked -StepName "crv_model_holdout" -CommandArgs @(
    "-m", "goldevidencebench.cli", "model",
    "--data", $crvHoldoutData,
    "--adapter", $Adapter,
    "--protocol", $Protocol,
    "--max-support-k", "$MaxSupportK",
    "--out", $crvHoldoutPreds
)
Invoke-PythonChecked -StepName "crv_score_holdout" -CommandArgs @(
    ".\scripts\score_compression_recoverability.py",
    "--data", $crvHoldoutData,
    "--preds", $crvHoldoutPreds,
    "--out", $crvHoldoutSummary,
    "--rows-out", (Join-Path $crvOut "holdout_rows.jsonl"),
    "--min-value-acc", "$CrvHoldoutMinValueAcc",
    "--min-exact-acc", "$CrvHoldoutMinExactAcc",
    "--min-cite-f1", "$CrvHoldoutMinCiteF1"
)

Invoke-PythonChecked -StepName "crv_model_canary" -CommandArgs @(
    "-m", "goldevidencebench.cli", "model",
    "--data", $crvCanaryData,
    "--adapter", $Adapter,
    "--protocol", $Protocol,
    "--max-support-k", "$MaxSupportK",
    "--out", $crvCanaryPreds
)
Invoke-PythonChecked -StepName "crv_score_canary" -CommandArgs @(
    ".\scripts\score_compression_recoverability.py",
    "--data", $crvCanaryData,
    "--preds", $crvCanaryPreds,
    "--out", $crvCanarySummary,
    "--rows-out", (Join-Path $crvOut "canary_rows.jsonl")
)

$clbAnch = Read-JsonFile -Path $clbAnchorsSummary
$clbHold = Read-JsonFile -Path $clbHoldoutSummary
$clbCan = Read-JsonFile -Path $clbCanarySummary
$crvAnch = Read-JsonFile -Path $crvAnchorsSummary
$crvHold = Read-JsonFile -Path $crvHoldoutSummary
$crvCan = Read-JsonFile -Path $crvCanarySummary

$clbHardPass = ($clbAnch.status -eq "PASS") -and ($clbHold.status -eq "PASS")
$crvHardPass = ($crvAnch.status -eq "PASS") -and ($crvHold.status -eq "PASS")
$hardGatePass = $clbHardPass -and $crvHardPass

$clbCanaryExact = Get-ExactRate -Summary $clbCan
$crvCanaryExact = Get-ExactRate -Summary $crvCan
$clbCanaryAlert = (-not [double]::IsNaN($clbCanaryExact)) -and ($clbCanaryExact -ge $CanaryAlertExactRate)
$crvCanaryAlert = (-not [double]::IsNaN($crvCanaryExact)) -and ($crvCanaryExact -ge $CanaryAlertExactRate)
$canaryStatus = if ($clbCanaryAlert -or $crvCanaryAlert) { "WARN" } else { "OK" }

$combined = [ordered]@{
    benchmark = "compression_families"
    generated_at = (Get-Date).ToString("o")
    out_root = (Resolve-Path $OutRoot).Path
    adapter = $Adapter
    protocol = $Protocol
    hard_gate_status = if ($hardGatePass) { "PASS" } else { "FAIL" }
    canary_status = $canaryStatus
    canary_alert_exact_rate = $CanaryAlertExactRate
    families = [ordered]@{
        compression_loss_bounded = [ordered]@{
            anchors = $clbAnch
            holdout = $clbHold
            canary = $clbCan
            hard_gate_status = if ($clbHardPass) { "PASS" } else { "FAIL" }
            canary_exact_rate = $clbCanaryExact
            canary_alert = $clbCanaryAlert
        }
        compression_recoverability = [ordered]@{
            anchors = $crvAnch
            holdout = $crvHold
            canary = $crvCan
            hard_gate_status = if ($crvHardPass) { "PASS" } else { "FAIL" }
            canary_exact_rate = $crvCanaryExact
            canary_alert = $crvCanaryAlert
        }
    }
}

$combinedPath = Join-Path $OutRoot "compression_families_summary.json"
$combined | ConvertTo-Json -Depth 12 | Set-Content -Path $combinedPath -Encoding UTF8

Write-Host "Wrote $combinedPath"
Write-Host ("hard_gate_status={0} canary_status={1}" -f $combined.hard_gate_status, $combined.canary_status)

if (-not $hardGatePass) {
    exit 1
}
exit 0
