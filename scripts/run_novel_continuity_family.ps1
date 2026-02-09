param(
    [string]$OutRoot = "",
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL,
    [string]$Adapter = "goldevidencebench.adapters.llama_server_adapter:create_adapter",
    [string]$Protocol = "closed_book",
    [int]$MaxSupportK = 16,
    [switch]$OverwriteFixtures,
    [ValidateSet("observe","ramp","target","custom")]
    [string]$CiteStage = "observe",
    [double]$AnchorsMinValueAcc = 0.80,
    [double]$AnchorsMinExactAcc = 0.80,
    [double]$AnchorsMinCiteF1 = 0.00,
    [double]$AnchorsMinIdentityAcc = 0.70,
    [double]$AnchorsMinTimelineAcc = 0.70,
    [double]$AnchorsMinConstraintAcc = 0.70,
    [double]$HoldoutMinValueAcc = 0.85,
    [double]$HoldoutMinExactAcc = 0.85,
    [double]$HoldoutMinCiteF1 = 0.00,
    [double]$HoldoutMinIdentityAcc = 0.80,
    [double]$HoldoutMinTimelineAcc = 0.80,
    [double]$HoldoutMinConstraintAcc = 0.80,
    [double]$CanaryAlertExactRate = 0.90
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

if (-not $OutRoot) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutRoot = "runs\novel_continuity_$stamp"
}

if ($ModelPath) {
    $env:GOLDEVIDENCEBENCH_MODEL = $ModelPath
}

New-Item -ItemType Directory -Path $OutRoot -Force | Out-Null

$anchorsData = "data\novel_continuity\novel_continuity_anchors.jsonl"
$holdoutData = "data\novel_continuity\novel_continuity_holdout.jsonl"
$canaryData = "data\novel_continuity\novel_continuity_canary.jsonl"
$needGenerate = $OverwriteFixtures -or -not ((Test-Path $anchorsData) -and (Test-Path $holdoutData) -and (Test-Path $canaryData))

Write-Host "Novel continuity run"
Write-Host "OutRoot: $OutRoot"
Write-Host "Adapter: $Adapter"
Write-Host "Protocol: $Protocol"
Write-Host "MaxSupportK: $MaxSupportK"

$effectiveAnchorsMinCiteF1 = $AnchorsMinCiteF1
$effectiveHoldoutMinCiteF1 = $HoldoutMinCiteF1
if ($CiteStage -ne "custom") {
    $stageFloors = @{
        observe = 0.00
        ramp = 0.60
        target = 0.85
    }
    $effectiveAnchorsMinCiteF1 = [double]$stageFloors[$CiteStage]
    $effectiveHoldoutMinCiteF1 = [double]$stageFloors[$CiteStage]
}
Write-Host ("CiteStage: {0} (anchors min_cite_f1={1:0.00}, holdout min_cite_f1={2:0.00})" -f $CiteStage, $effectiveAnchorsMinCiteF1, $effectiveHoldoutMinCiteF1)

if ($needGenerate) {
    $genArgs = @(".\scripts\generate_novel_continuity_family.py")
    if ($OverwriteFixtures) { $genArgs += "--overwrite" }
    Invoke-PythonChecked -StepName "generate_novel_continuity_family" -CommandArgs $genArgs
} else {
    Write-Host "Using existing novel_continuity fixtures."
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
Invoke-PythonChecked -StepName "score_anchors" -CommandArgs @(
    ".\scripts\score_novel_continuity.py",
    "--data", $anchorsData,
    "--preds", $anchorsPreds,
    "--out", $anchorsSummary,
    "--rows-out", (Join-Path $OutRoot "anchors_rows.jsonl"),
    "--min-value-acc", "$AnchorsMinValueAcc",
    "--min-exact-acc", "$AnchorsMinExactAcc",
    "--min-cite-f1", "$effectiveAnchorsMinCiteF1",
    "--min-identity-acc", "$AnchorsMinIdentityAcc",
    "--min-timeline-acc", "$AnchorsMinTimelineAcc",
    "--min-constraint-acc", "$AnchorsMinConstraintAcc"
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
Invoke-PythonChecked -StepName "score_holdout" -CommandArgs @(
    ".\scripts\score_novel_continuity.py",
    "--data", $holdoutData,
    "--preds", $holdoutPreds,
    "--out", $holdoutSummary,
    "--rows-out", (Join-Path $OutRoot "holdout_rows.jsonl"),
    "--min-value-acc", "$HoldoutMinValueAcc",
    "--min-exact-acc", "$HoldoutMinExactAcc",
    "--min-cite-f1", "$effectiveHoldoutMinCiteF1",
    "--min-identity-acc", "$HoldoutMinIdentityAcc",
    "--min-timeline-acc", "$HoldoutMinTimelineAcc",
    "--min-constraint-acc", "$HoldoutMinConstraintAcc"
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
Invoke-PythonChecked -StepName "score_canary" -CommandArgs @(
    ".\scripts\score_novel_continuity.py",
    "--data", $canaryData,
    "--preds", $canaryPreds,
    "--out", $canarySummary,
    "--rows-out", (Join-Path $OutRoot "canary_rows.jsonl")
)

$anchorsObj = Read-JsonFile -Path $anchorsSummary
$holdoutObj = Read-JsonFile -Path $holdoutSummary
$canaryObj = Read-JsonFile -Path $canarySummary

$hardGatePass = ($anchorsObj.status -eq "PASS") -and ($holdoutObj.status -eq "PASS")
$canaryExact = [double]$canaryObj.means.exact_acc
$canaryAlert = $canaryExact -ge $CanaryAlertExactRate
$canaryStatus = if ($canaryAlert) { "WARN" } else { "OK" }
$releaseStageApproved = $CiteStage -eq "target"

$combined = [ordered]@{
    benchmark = "novel_continuity"
    generated_at = (Get-Date).ToString("o")
    out_root = (Resolve-Path $OutRoot).Path
    adapter = $Adapter
    protocol = $Protocol
    hard_gate_status = if ($hardGatePass) { "PASS" } else { "FAIL" }
    canary_status = $canaryStatus
    canary_alert_exact_rate = $CanaryAlertExactRate
    cite_stage = $CiteStage
    provenance = [ordered]@{
        release_stage_required = "target"
        release_stage_approved = $releaseStageApproved
    }
    effective_anchors_min_cite_f1 = $effectiveAnchorsMinCiteF1
    effective_holdout_min_cite_f1 = $effectiveHoldoutMinCiteF1
    anchors = $anchorsObj
    holdout = $holdoutObj
    canary = $canaryObj
    canary_exact_rate = $canaryExact
    canary_alert = $canaryAlert
}

$combinedPath = Join-Path $OutRoot "novel_continuity_summary.json"
$combined | ConvertTo-Json -Depth 12 | Set-Content -Path $combinedPath -Encoding UTF8
Write-Host "Wrote $combinedPath"
Write-Host ("hard_gate_status={0} canary_status={1}" -f $combined.hard_gate_status, $combined.canary_status)

if (-not $hardGatePass) {
    exit 1
}
exit 0
