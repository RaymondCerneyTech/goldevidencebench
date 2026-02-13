param(
    [string]$OutRoot = "",
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL,
    [string]$Adapter = "goldevidencebench.adapters.llama_server_adapter:create_adapter",
    [string]$Protocol = "closed_book",
    [int]$MaxSupportK = 64,
    [switch]$OverwriteFixtures,
    [switch]$UseRealPublicFixtures,
    [ValidateSet("observe","ramp","target","custom")]
    [string]$Stage = "observe",
    [double]$AnchorsMinValueAcc = 0.80,
    [double]$AnchorsMinExactAcc = 0.80,
    [double]$AnchorsMinCiteF1 = 0.75,
    [double]$AnchorsMinDirectAcc = 0.70,
    [double]$AnchorsMinAggregateAcc = 0.70,
    [double]$AnchorsMinExceptionAcc = 0.70,
    [double]$AnchorsMinNegationAcc = 0.70,
    [double]$AnchorsMinTailKeyAcc = 0.70,
    [double]$AnchorsMinNullTargetAcc = 0.70,
    [double]$AnchorsMinNonnullTargetAcc = 0.70,
    [double]$AnchorsMinLargeSnapshotAcc = 0.70,
    [double]$HoldoutMinValueAcc = 0.85,
    [double]$HoldoutMinExactAcc = 0.85,
    [double]$HoldoutMinCiteF1 = 0.85,
    [double]$HoldoutMinDirectAcc = 0.80,
    [double]$HoldoutMinAggregateAcc = 0.80,
    [double]$HoldoutMinExceptionAcc = 0.80,
    [double]$HoldoutMinNegationAcc = 0.80,
    [double]$HoldoutMinTailKeyAcc = 0.80,
    [double]$HoldoutMinNullTargetAcc = 0.80,
    [double]$HoldoutMinNonnullTargetAcc = 0.80,
    [double]$HoldoutMinLargeSnapshotAcc = 0.80,
    [double]$CanaryAlertExactRate = 0.90,
    [switch]$FailOnCanaryWarn,
    [bool]$RunPersonaTrap = $true,
    [string]$PersonaProfiles = "persona_confident_expert,persona_creative_writer,persona_ultra_brief,persona_overly_helpful"
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
    $OutRoot = "runs\compression_roundtrip_generalization_$stamp"
}

if ($ModelPath) {
    $env:GOLDEVIDENCEBENCH_MODEL = $ModelPath
}

New-Item -ItemType Directory -Path $OutRoot -Force | Out-Null

$anchorsData = "data\compression_roundtrip_generalization\compression_roundtrip_generalization_anchors.jsonl"
$holdoutData = "data\compression_roundtrip_generalization\compression_roundtrip_generalization_holdout.jsonl"
$canaryData = "data\compression_roundtrip_generalization\compression_roundtrip_generalization_canary.jsonl"
$needGenerate = $OverwriteFixtures -or -not ((Test-Path $anchorsData) -and (Test-Path $holdoutData) -and (Test-Path $canaryData))

Write-Host "Compression roundtrip generalization run"
Write-Host "OutRoot: $OutRoot"
Write-Host "Adapter: $Adapter"
Write-Host "Protocol: $Protocol"
Write-Host "MaxSupportK: $MaxSupportK"

$effectiveAnchorsMinValueAcc = $AnchorsMinValueAcc
$effectiveAnchorsMinExactAcc = $AnchorsMinExactAcc
$effectiveAnchorsMinCiteF1 = $AnchorsMinCiteF1
$effectiveAnchorsMinDirectAcc = $AnchorsMinDirectAcc
$effectiveAnchorsMinAggregateAcc = $AnchorsMinAggregateAcc
$effectiveAnchorsMinExceptionAcc = $AnchorsMinExceptionAcc
$effectiveAnchorsMinNegationAcc = $AnchorsMinNegationAcc
$effectiveAnchorsMinTailKeyAcc = $AnchorsMinTailKeyAcc
$effectiveAnchorsMinNullTargetAcc = $AnchorsMinNullTargetAcc
$effectiveAnchorsMinNonnullTargetAcc = $AnchorsMinNonnullTargetAcc
$effectiveAnchorsMinLargeSnapshotAcc = $AnchorsMinLargeSnapshotAcc

$effectiveHoldoutMinValueAcc = $HoldoutMinValueAcc
$effectiveHoldoutMinExactAcc = $HoldoutMinExactAcc
$effectiveHoldoutMinCiteF1 = $HoldoutMinCiteF1
$effectiveHoldoutMinDirectAcc = $HoldoutMinDirectAcc
$effectiveHoldoutMinAggregateAcc = $HoldoutMinAggregateAcc
$effectiveHoldoutMinExceptionAcc = $HoldoutMinExceptionAcc
$effectiveHoldoutMinNegationAcc = $HoldoutMinNegationAcc
$effectiveHoldoutMinTailKeyAcc = $HoldoutMinTailKeyAcc
$effectiveHoldoutMinNullTargetAcc = $HoldoutMinNullTargetAcc
$effectiveHoldoutMinNonnullTargetAcc = $HoldoutMinNonnullTargetAcc
$effectiveHoldoutMinLargeSnapshotAcc = $HoldoutMinLargeSnapshotAcc

if ($Stage -ne "custom") {
    switch ($Stage) {
        "observe" {
            $effectiveAnchorsMinValueAcc = 0.65
            $effectiveAnchorsMinExactAcc = 0.65
            $effectiveAnchorsMinCiteF1 = 0.50
            $effectiveAnchorsMinDirectAcc = 0.65
            $effectiveAnchorsMinAggregateAcc = 0.50
            $effectiveAnchorsMinExceptionAcc = 0.25
            $effectiveAnchorsMinNegationAcc = 0.80
            $effectiveAnchorsMinTailKeyAcc = 0.00
            $effectiveAnchorsMinNullTargetAcc = 0.80
            $effectiveAnchorsMinNonnullTargetAcc = 0.55
            $effectiveAnchorsMinLargeSnapshotAcc = 0.00

            $effectiveHoldoutMinValueAcc = 0.65
            $effectiveHoldoutMinExactAcc = 0.65
            $effectiveHoldoutMinCiteF1 = 0.50
            $effectiveHoldoutMinDirectAcc = 0.75
            $effectiveHoldoutMinAggregateAcc = 0.70
            $effectiveHoldoutMinExceptionAcc = 0.20
            $effectiveHoldoutMinNegationAcc = 0.85
            $effectiveHoldoutMinTailKeyAcc = 0.70
            $effectiveHoldoutMinNullTargetAcc = 0.85
            $effectiveHoldoutMinNonnullTargetAcc = 0.55
            $effectiveHoldoutMinLargeSnapshotAcc = 0.00
        }
        "ramp" {
            $effectiveAnchorsMinValueAcc = 0.75
            $effectiveAnchorsMinExactAcc = 0.75
            $effectiveAnchorsMinCiteF1 = 0.65
            $effectiveAnchorsMinDirectAcc = 0.70
            $effectiveAnchorsMinAggregateAcc = 0.70
            $effectiveAnchorsMinExceptionAcc = 0.45
            $effectiveAnchorsMinNegationAcc = 0.90
            $effectiveAnchorsMinTailKeyAcc = 0.60
            $effectiveAnchorsMinNullTargetAcc = 0.90
            $effectiveAnchorsMinNonnullTargetAcc = 0.65
            $effectiveAnchorsMinLargeSnapshotAcc = 0.25

            $effectiveHoldoutMinValueAcc = 0.75
            $effectiveHoldoutMinExactAcc = 0.75
            $effectiveHoldoutMinCiteF1 = 0.65
            $effectiveHoldoutMinDirectAcc = 0.78
            $effectiveHoldoutMinAggregateAcc = 0.75
            $effectiveHoldoutMinExceptionAcc = 0.45
            $effectiveHoldoutMinNegationAcc = 0.90
            $effectiveHoldoutMinTailKeyAcc = 0.75
            $effectiveHoldoutMinNullTargetAcc = 0.90
            $effectiveHoldoutMinNonnullTargetAcc = 0.70
            $effectiveHoldoutMinLargeSnapshotAcc = 0.35
        }
        "target" {
            # Keep caller-provided defaults (target contract).
        }
    }
}
Write-Host ("Stage: {0} (holdout floors: value/exact={1:0.00}, cite_f1={2:0.00}, exception={3:0.00}, large_snapshot={4:0.00})" -f $Stage, $effectiveHoldoutMinValueAcc, $effectiveHoldoutMinCiteF1, $effectiveHoldoutMinExceptionAcc, $effectiveHoldoutMinLargeSnapshotAcc)

if ($needGenerate) {
    $genArgs = @(".\scripts\generate_compression_roundtrip_generalization_family.py")
    if ($OverwriteFixtures) { $genArgs += "--overwrite" }
    Invoke-PythonChecked -StepName "generate_compression_roundtrip_generalization_family" -CommandArgs $genArgs
} else {
    Write-Host "Using existing compression_roundtrip_generalization fixtures."
}

if ($UseRealPublicFixtures) {
    Invoke-PythonChecked -StepName "generate_real_public_fixtures" -CommandArgs @(
        ".\scripts\generate_real_public_family_fixtures.py",
        "--family", "compression_roundtrip_generalization",
        "--overwrite"
    )
    $anchorsData = "data\compression_roundtrip_generalization\compression_roundtrip_generalization_anchors_real_public.jsonl"
    $holdoutData = "data\compression_roundtrip_generalization\compression_roundtrip_generalization_holdout_real_public.jsonl"
    $canaryData = "data\compression_roundtrip_generalization\compression_roundtrip_generalization_canary_real_public.jsonl"
    Write-Host "Data mode: real_public"
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
    ".\scripts\score_compression_roundtrip_generalization.py",
    "--data", $anchorsData,
    "--preds", $anchorsPreds,
    "--out", $anchorsSummary,
    "--rows-out", (Join-Path $OutRoot "anchors_rows.jsonl"),
    "--min-value-acc", "$effectiveAnchorsMinValueAcc",
    "--min-exact-acc", "$effectiveAnchorsMinExactAcc",
    "--min-cite-f1", "$effectiveAnchorsMinCiteF1",
    "--min-direct-acc", "$effectiveAnchorsMinDirectAcc",
    "--min-aggregate-acc", "$effectiveAnchorsMinAggregateAcc",
    "--min-exception-acc", "$effectiveAnchorsMinExceptionAcc",
    "--min-negation-acc", "$effectiveAnchorsMinNegationAcc",
    "--min-tail-key-acc", "$effectiveAnchorsMinTailKeyAcc",
    "--min-null-target-acc", "$effectiveAnchorsMinNullTargetAcc",
    "--min-nonnull-target-acc", "$effectiveAnchorsMinNonnullTargetAcc",
    "--min-large-snapshot-acc", "$effectiveAnchorsMinLargeSnapshotAcc"
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
    ".\scripts\score_compression_roundtrip_generalization.py",
    "--data", $holdoutData,
    "--preds", $holdoutPreds,
    "--out", $holdoutSummary,
    "--rows-out", (Join-Path $OutRoot "holdout_rows.jsonl"),
    "--min-value-acc", "$effectiveHoldoutMinValueAcc",
    "--min-exact-acc", "$effectiveHoldoutMinExactAcc",
    "--min-cite-f1", "$effectiveHoldoutMinCiteF1",
    "--min-direct-acc", "$effectiveHoldoutMinDirectAcc",
    "--min-aggregate-acc", "$effectiveHoldoutMinAggregateAcc",
    "--min-exception-acc", "$effectiveHoldoutMinExceptionAcc",
    "--min-negation-acc", "$effectiveHoldoutMinNegationAcc",
    "--min-tail-key-acc", "$effectiveHoldoutMinTailKeyAcc",
    "--min-null-target-acc", "$effectiveHoldoutMinNullTargetAcc",
    "--min-nonnull-target-acc", "$effectiveHoldoutMinNonnullTargetAcc",
    "--min-large-snapshot-acc", "$effectiveHoldoutMinLargeSnapshotAcc"
)

$personaObj = $null
$personaGatePass = $true
if ($RunPersonaTrap) {
    $personaSummaryPath = Join-Path $OutRoot "persona_invariance_summary.json"
    $personaRowsPath = Join-Path $OutRoot "persona_invariance_rows.jsonl"
    & .\scripts\run_persona_invariance_trap.ps1 `
        -CanonicalData $holdoutData `
        -CanonicalPreds $holdoutPreds `
        -OutRoot $OutRoot `
        -Adapter $Adapter `
        -Protocol $Protocol `
        -MaxSupportK $MaxSupportK `
        -PersonaProfiles $PersonaProfiles `
        -Prefix "holdout" `
        -SummaryPath $personaSummaryPath `
        -RowsPath $personaRowsPath
    if (-not (Test-Path $personaSummaryPath)) {
        $personaGatePass = $false
    } else {
        $personaObj = Read-JsonFile -Path $personaSummaryPath
        $personaRate = [double]$personaObj.row_invariance_rate
        $personaGatePass = $personaRate -ge 1.0
    }
}

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
    ".\scripts\score_compression_roundtrip_generalization.py",
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
$enforceCanaryGate = [bool]$FailOnCanaryWarn -or $releaseStageApproved
$canaryGatePass = -not $canaryAlert
$hardGatePass = $hardGatePass -and ((-not $enforceCanaryGate) -or $canaryGatePass)
$hardGatePass = $hardGatePass -and $personaGatePass

$combined = [ordered]@{
    benchmark = "compression_roundtrip_generalization"
    generated_at = (Get-Date).ToString("o")
    out_root = (Resolve-Path $OutRoot).Path
    adapter = $Adapter
    protocol = $Protocol
    stage = $Stage
    provenance = [ordered]@{
        release_stage_required = "target"
        release_stage_approved = $releaseStageApproved
        canary_gate_enforced = $enforceCanaryGate
    }
    effective_anchors_min_cite_f1 = $effectiveAnchorsMinCiteF1
    effective_holdout_min_cite_f1 = $effectiveHoldoutMinCiteF1
    hard_gate_status = if ($hardGatePass) { "PASS" } else { "FAIL" }
    canary_gate_enforced = $enforceCanaryGate
    canary_status = $canaryStatus
    canary_alert_exact_rate = $CanaryAlertExactRate
    anchors = $anchorsObj
    holdout = $holdoutObj
    canary = $canaryObj
    persona_invariance = if ($RunPersonaTrap) {
        if ($personaObj) {
            $personaObj
        } else {
            [ordered]@{
                status = "FAIL"
                row_invariance_rate = 0.0
                rows_total = 0
                rows_changed = 0
                failure_category = "persona_contract_drift"
            }
        }
    } else {
        [ordered]@{
            status = "SKIP"
            row_invariance_rate = $null
            rows_total = 0
            rows_changed = 0
            enabled = $false
        }
    }
    canary_exact_rate = $canaryExact
    canary_alert = $canaryAlert
}

$combinedPath = Join-Path $OutRoot "compression_roundtrip_generalization_summary.json"
$combined | ConvertTo-Json -Depth 12 | Set-Content -Path $combinedPath -Encoding UTF8
Write-Host "Wrote $combinedPath"
Write-Host ("hard_gate_status={0} canary_status={1} canary_gate_enforced={2}" -f $combined.hard_gate_status, $combined.canary_status, $combined.canary_gate_enforced)

if (-not $hardGatePass) {
    exit 1
}

if (($scoreAnchorsExit -ne 0) -or ($scoreHoldoutExit -ne 0) -or ($scoreCanaryExit -ne 0)) {
    exit 1
}

exit 0
