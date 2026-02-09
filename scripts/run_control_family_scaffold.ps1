param(
    [ValidateSet("rpa_mode_switch", "intent_spec_layer", "noise_escalation")]
    [string]$Family,
    [string]$OutRoot = "",
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL,
    [string]$Adapter = "goldevidencebench.adapters.llama_server_adapter:create_adapter",
    [string]$Protocol = "closed_book",
    [int]$MaxSupportK = 16,
    [switch]$OverwriteFixtures,
    [ValidateSet("observe", "ramp", "target", "custom")]
    [string]$Stage = "observe",
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

function Get-ThresholdMap {
    param([string]$FamilyId, [string]$StageId)

    $map = @{
        "rpa_mode_switch" = @{
            "observe" = @{
                min_value_acc = 0.55
                min_exact_acc = 0.55
                min_cite_f1 = 0.35
                min_mode_switch_accuracy = 0.55
                max_premature_act_rate = 0.45
                max_unnecessary_plan_rate = 0.45
                min_verify_gate_rate = 0.30
            }
            "ramp" = @{
                min_value_acc = 0.75
                min_exact_acc = 0.75
                min_cite_f1 = 0.55
                min_mode_switch_accuracy = 0.75
                max_premature_act_rate = 0.25
                max_unnecessary_plan_rate = 0.25
                min_verify_gate_rate = 0.55
            }
            "target" = @{
                min_value_acc = 0.90
                min_exact_acc = 0.90
                min_cite_f1 = 0.80
                min_mode_switch_accuracy = 0.90
                max_premature_act_rate = 0.10
                max_unnecessary_plan_rate = 0.10
                min_verify_gate_rate = 0.80
            }
        }
        "intent_spec_layer" = @{
            "observe" = @{
                min_value_acc = 0.55
                min_exact_acc = 0.55
                min_cite_f1 = 0.35
                min_clarification_precision = 0.50
                min_clarification_recall = 0.50
                min_clarification_f1 = 0.45
                max_user_burden_score = 0.70
                min_downstream_error_reduction = 0.40
            }
            "ramp" = @{
                min_value_acc = 0.75
                min_exact_acc = 0.75
                min_cite_f1 = 0.55
                min_clarification_precision = 0.70
                min_clarification_recall = 0.70
                min_clarification_f1 = 0.70
                max_user_burden_score = 0.45
                min_downstream_error_reduction = 0.65
            }
            "target" = @{
                min_value_acc = 0.90
                min_exact_acc = 0.90
                min_cite_f1 = 0.80
                min_clarification_precision = 0.90
                min_clarification_recall = 0.90
                min_clarification_f1 = 0.90
                max_user_burden_score = 0.20
                min_downstream_error_reduction = 0.84
            }
        }
        "noise_escalation" = @{
            "observe" = @{
                min_value_acc = 0.55
                min_exact_acc = 0.55
                min_cite_f1 = 0.35
                min_noise_control_accuracy = 0.55
                max_noise_slope = 0.75
                max_recovery_latency = 5.00
                max_irrecoverable_drift_rate = 0.45
            }
            "ramp" = @{
                min_value_acc = 0.75
                min_exact_acc = 0.75
                min_cite_f1 = 0.55
                min_noise_control_accuracy = 0.75
                max_noise_slope = 0.45
                max_recovery_latency = 3.50
                max_irrecoverable_drift_rate = 0.25
            }
            "target" = @{
                min_value_acc = 0.90
                min_exact_acc = 0.90
                min_cite_f1 = 0.80
                min_noise_control_accuracy = 0.90
                max_noise_slope = 0.20
                max_recovery_latency = 2.00
                max_irrecoverable_drift_rate = 0.10
            }
        }
    }

    if ($StageId -eq "custom") {
        return $map[$FamilyId]["target"]
    }
    return $map[$FamilyId][$StageId]
}

function Get-ThresholdArgs {
    param([string]$FamilyId, [hashtable]$Floors)
    switch ($FamilyId) {
        "rpa_mode_switch" {
            return @(
                "--min-value-acc", "$($Floors.min_value_acc)",
                "--min-exact-acc", "$($Floors.min_exact_acc)",
                "--min-cite-f1", "$($Floors.min_cite_f1)",
                "--min-mode-switch-accuracy", "$($Floors.min_mode_switch_accuracy)",
                "--max-premature-act-rate", "$($Floors.max_premature_act_rate)",
                "--max-unnecessary-plan-rate", "$($Floors.max_unnecessary_plan_rate)",
                "--min-verify-gate-rate", "$($Floors.min_verify_gate_rate)"
            )
        }
        "intent_spec_layer" {
            return @(
                "--min-value-acc", "$($Floors.min_value_acc)",
                "--min-exact-acc", "$($Floors.min_exact_acc)",
                "--min-cite-f1", "$($Floors.min_cite_f1)",
                "--min-clarification-precision", "$($Floors.min_clarification_precision)",
                "--min-clarification-recall", "$($Floors.min_clarification_recall)",
                "--min-clarification-f1", "$($Floors.min_clarification_f1)",
                "--max-user-burden-score", "$($Floors.max_user_burden_score)",
                "--min-downstream-error-reduction", "$($Floors.min_downstream_error_reduction)"
            )
        }
        "noise_escalation" {
            return @(
                "--min-value-acc", "$($Floors.min_value_acc)",
                "--min-exact-acc", "$($Floors.min_exact_acc)",
                "--min-cite-f1", "$($Floors.min_cite_f1)",
                "--min-noise-control-accuracy", "$($Floors.min_noise_control_accuracy)",
                "--max-noise-slope", "$($Floors.max_noise_slope)",
                "--max-recovery-latency", "$($Floors.max_recovery_latency)",
                "--max-irrecoverable-drift-rate", "$($Floors.max_irrecoverable_drift_rate)"
            )
        }
    }
    throw "Unsupported family for thresholds: $FamilyId"
}

if (-not $OutRoot) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutRoot = "runs\${Family}_$stamp"
}

if ($ModelPath) {
    $env:GOLDEVIDENCEBENCH_MODEL = $ModelPath
}

$generatorScript = ""
$scorerScript = ""
switch ($Family) {
    "rpa_mode_switch" {
        $generatorScript = ".\scripts\generate_rpa_mode_switch_family.py"
        $scorerScript = ".\scripts\score_rpa_mode_switch.py"
    }
    "intent_spec_layer" {
        $generatorScript = ".\scripts\generate_intent_spec_family.py"
        $scorerScript = ".\scripts\score_intent_spec.py"
    }
    "noise_escalation" {
        $generatorScript = ".\scripts\generate_noise_escalation_family.py"
        $scorerScript = ".\scripts\score_noise_escalation.py"
    }
}

$anchorsData = "data\$Family\${Family}_anchors.jsonl"
$holdoutData = "data\$Family\${Family}_holdout.jsonl"
$canaryData = "data\$Family\${Family}_canary.jsonl"
$needGenerate = $OverwriteFixtures -or -not ((Test-Path $anchorsData) -and (Test-Path $holdoutData) -and (Test-Path $canaryData))

$floors = Get-ThresholdMap -FamilyId $Family -StageId $Stage
$thresholdArgs = Get-ThresholdArgs -FamilyId $Family -Floors $floors

Write-Host "$($Family -replace '_', ' ') run"
Write-Host "OutRoot: $OutRoot"
Write-Host "Adapter: $Adapter"
Write-Host "Protocol: $Protocol"
Write-Host "MaxSupportK: $MaxSupportK"
Write-Host "Stage: $Stage"

New-Item -ItemType Directory -Path $OutRoot -Force | Out-Null

if ($needGenerate) {
    $genArgs = @($generatorScript)
    if ($OverwriteFixtures) { $genArgs += "--overwrite" }
    Invoke-PythonChecked -StepName "generate_family" -CommandArgs $genArgs
} else {
    Write-Host "Using existing $Family fixtures."
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
$anchorsScoreArgs = @(
    $scorerScript,
    "--data", $anchorsData,
    "--preds", $anchorsPreds,
    "--out", $anchorsSummary,
    "--rows-out", (Join-Path $OutRoot "anchors_rows.jsonl")
)
$anchorsScoreArgs += $thresholdArgs
$scoreAnchorsExit = Invoke-PythonSoftFail -StepName "score_anchors" -CommandArgs $anchorsScoreArgs

Invoke-PythonChecked -StepName "model_holdout" -CommandArgs @(
    "-m", "goldevidencebench.cli", "model",
    "--data", $holdoutData,
    "--adapter", $Adapter,
    "--protocol", $Protocol,
    "--citations", "auto",
    "--max-support-k", "$MaxSupportK",
    "--out", $holdoutPreds
)
$holdoutScoreArgs = @(
    $scorerScript,
    "--data", $holdoutData,
    "--preds", $holdoutPreds,
    "--out", $holdoutSummary,
    "--rows-out", (Join-Path $OutRoot "holdout_rows.jsonl")
)
$holdoutScoreArgs += $thresholdArgs
$scoreHoldoutExit = Invoke-PythonSoftFail -StepName "score_holdout" -CommandArgs $holdoutScoreArgs

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
    $scorerScript,
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
$releaseStageApproved = $Stage -eq "target"

$combined = [ordered]@{
    benchmark = $Family
    generated_at = (Get-Date).ToString("o")
    out_root = (Resolve-Path $OutRoot).Path
    adapter = $Adapter
    protocol = $Protocol
    stage = $Stage
    provenance = [ordered]@{
        release_stage_required = "target"
        release_stage_approved = $releaseStageApproved
    }
    effective_holdout_floors = $floors
    hard_gate_status = if ($hardGatePass) { "PASS" } else { "FAIL" }
    canary_status = $canaryStatus
    canary_alert_exact_rate = $CanaryAlertExactRate
    anchors = $anchorsObj
    holdout = $holdoutObj
    canary = $canaryObj
    canary_exact_rate = $canaryExact
    canary_alert = $canaryAlert
}

$combinedPath = Join-Path $OutRoot "${Family}_summary.json"
$combined | ConvertTo-Json -Depth 16 | Set-Content -Path $combinedPath -Encoding UTF8
Write-Host "Wrote $combinedPath"
Write-Host ("hard_gate_status={0} canary_status={1}" -f $combined.hard_gate_status, $combined.canary_status)

if (-not $hardGatePass) {
    exit 1
}

if (($scoreAnchorsExit -ne 0) -or ($scoreHoldoutExit -ne 0) -or ($scoreCanaryExit -ne 0)) {
    exit 1
}

exit 0
