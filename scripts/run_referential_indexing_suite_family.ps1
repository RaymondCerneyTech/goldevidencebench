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
    [double]$AnchorsMinValueAcc = 0.75,
    [double]$AnchorsMinExactAcc = 0.75,
    [double]$AnchorsMinCiteF1 = 0.65,
    [double]$AnchorsMinPartCoverageRecall = 0.70,
    [double]$AnchorsMinPointerPrecision = 0.65,
    [double]$AnchorsMinPointerRecall = 0.65,
    [double]$AnchorsMinReassemblyFidelity = 0.75,
    [double]$AnchorsMaxHallucinatedExpansionRate = 0.20,
    [double]$AnchorsMaxStalePointerOverrideRate = 0.20,
    [double]$AnchorsMaxLookupDepthCost = 6.0,
    [double]$AnchorsMinExceptionAcc = 0.55,
    [double]$AnchorsMinLargeSnapshotAcc = 0.55,
    [double]$HoldoutMinValueAcc = 0.85,
    [double]$HoldoutMinExactAcc = 0.85,
    [double]$HoldoutMinCiteF1 = 0.85,
    [double]$HoldoutMinPartCoverageRecall = 0.85,
    [double]$HoldoutMinPointerPrecision = 0.85,
    [double]$HoldoutMinPointerRecall = 0.85,
    [double]$HoldoutMinReassemblyFidelity = 0.85,
    [double]$HoldoutMaxHallucinatedExpansionRate = 0.10,
    [double]$HoldoutMaxStalePointerOverrideRate = 0.10,
    [double]$HoldoutMaxLookupDepthCost = 4.0,
    [double]$HoldoutMinExceptionAcc = 0.80,
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
    $OutRoot = "runs\referential_indexing_suite_$stamp"
}

if ($ModelPath) {
    $env:GOLDEVIDENCEBENCH_MODEL = $ModelPath
}

New-Item -ItemType Directory -Path $OutRoot -Force | Out-Null

$anchorsData = "data\referential_indexing_suite\referential_indexing_suite_anchors.jsonl"
$holdoutData = "data\referential_indexing_suite\referential_indexing_suite_holdout.jsonl"
$canaryData = "data\referential_indexing_suite\referential_indexing_suite_canary.jsonl"
$needGenerate = $OverwriteFixtures -or -not ((Test-Path $anchorsData) -and (Test-Path $holdoutData) -and (Test-Path $canaryData))

Write-Host "Referential indexing suite run"
Write-Host "OutRoot: $OutRoot"
Write-Host "Adapter: $Adapter"
Write-Host "Protocol: $Protocol"
Write-Host "MaxSupportK: $MaxSupportK"

$effectiveAnchorsMinValueAcc = $AnchorsMinValueAcc
$effectiveAnchorsMinExactAcc = $AnchorsMinExactAcc
$effectiveAnchorsMinCiteF1 = $AnchorsMinCiteF1
$effectiveAnchorsMinPartCoverageRecall = $AnchorsMinPartCoverageRecall
$effectiveAnchorsMinPointerPrecision = $AnchorsMinPointerPrecision
$effectiveAnchorsMinPointerRecall = $AnchorsMinPointerRecall
$effectiveAnchorsMinReassemblyFidelity = $AnchorsMinReassemblyFidelity
$effectiveAnchorsMaxHallucinatedExpansionRate = $AnchorsMaxHallucinatedExpansionRate
$effectiveAnchorsMaxStalePointerOverrideRate = $AnchorsMaxStalePointerOverrideRate
$effectiveAnchorsMaxLookupDepthCost = $AnchorsMaxLookupDepthCost
$effectiveAnchorsMinExceptionAcc = $AnchorsMinExceptionAcc
$effectiveAnchorsMinLargeSnapshotAcc = $AnchorsMinLargeSnapshotAcc

$effectiveHoldoutMinValueAcc = $HoldoutMinValueAcc
$effectiveHoldoutMinExactAcc = $HoldoutMinExactAcc
$effectiveHoldoutMinCiteF1 = $HoldoutMinCiteF1
$effectiveHoldoutMinPartCoverageRecall = $HoldoutMinPartCoverageRecall
$effectiveHoldoutMinPointerPrecision = $HoldoutMinPointerPrecision
$effectiveHoldoutMinPointerRecall = $HoldoutMinPointerRecall
$effectiveHoldoutMinReassemblyFidelity = $HoldoutMinReassemblyFidelity
$effectiveHoldoutMaxHallucinatedExpansionRate = $HoldoutMaxHallucinatedExpansionRate
$effectiveHoldoutMaxStalePointerOverrideRate = $HoldoutMaxStalePointerOverrideRate
$effectiveHoldoutMaxLookupDepthCost = $HoldoutMaxLookupDepthCost
$effectiveHoldoutMinExceptionAcc = $HoldoutMinExceptionAcc
$effectiveHoldoutMinLargeSnapshotAcc = $HoldoutMinLargeSnapshotAcc

if ($Stage -ne "custom") {
    switch ($Stage) {
        "observe" {
            $effectiveAnchorsMinValueAcc = 0.55
            $effectiveAnchorsMinExactAcc = 0.55
            $effectiveAnchorsMinCiteF1 = 0.35
            $effectiveAnchorsMinPartCoverageRecall = 0.55
            $effectiveAnchorsMinPointerPrecision = 0.35
            $effectiveAnchorsMinPointerRecall = 0.35
            $effectiveAnchorsMinReassemblyFidelity = 0.55
            $effectiveAnchorsMaxHallucinatedExpansionRate = 0.55
            $effectiveAnchorsMaxStalePointerOverrideRate = 0.45
            $effectiveAnchorsMaxLookupDepthCost = 8.0
            $effectiveAnchorsMinExceptionAcc = 0.20
            $effectiveAnchorsMinLargeSnapshotAcc = 0.00

            $effectiveHoldoutMinValueAcc = 0.55
            $effectiveHoldoutMinExactAcc = 0.55
            $effectiveHoldoutMinCiteF1 = 0.35
            $effectiveHoldoutMinPartCoverageRecall = 0.55
            $effectiveHoldoutMinPointerPrecision = 0.35
            $effectiveHoldoutMinPointerRecall = 0.35
            $effectiveHoldoutMinReassemblyFidelity = 0.55
            $effectiveHoldoutMaxHallucinatedExpansionRate = 0.55
            $effectiveHoldoutMaxStalePointerOverrideRate = 0.45
            $effectiveHoldoutMaxLookupDepthCost = 8.0
            $effectiveHoldoutMinExceptionAcc = 0.20
            $effectiveHoldoutMinLargeSnapshotAcc = 0.00
        }
        "ramp" {
            $effectiveAnchorsMinValueAcc = 0.70
            $effectiveAnchorsMinExactAcc = 0.70
            $effectiveAnchorsMinCiteF1 = 0.55
            $effectiveAnchorsMinPartCoverageRecall = 0.70
            $effectiveAnchorsMinPointerPrecision = 0.55
            $effectiveAnchorsMinPointerRecall = 0.55
            $effectiveAnchorsMinReassemblyFidelity = 0.70
            $effectiveAnchorsMaxHallucinatedExpansionRate = 0.30
            $effectiveAnchorsMaxStalePointerOverrideRate = 0.25
            $effectiveAnchorsMaxLookupDepthCost = 6.0
            $effectiveAnchorsMinExceptionAcc = 0.45
            $effectiveAnchorsMinLargeSnapshotAcc = 0.35

            $effectiveHoldoutMinValueAcc = 0.70
            $effectiveHoldoutMinExactAcc = 0.70
            $effectiveHoldoutMinCiteF1 = 0.55
            $effectiveHoldoutMinPartCoverageRecall = 0.70
            $effectiveHoldoutMinPointerPrecision = 0.55
            $effectiveHoldoutMinPointerRecall = 0.55
            $effectiveHoldoutMinReassemblyFidelity = 0.70
            $effectiveHoldoutMaxHallucinatedExpansionRate = 0.30
            $effectiveHoldoutMaxStalePointerOverrideRate = 0.25
            $effectiveHoldoutMaxLookupDepthCost = 6.0
            $effectiveHoldoutMinExceptionAcc = 0.45
            $effectiveHoldoutMinLargeSnapshotAcc = 0.35
        }
        "target" {
            # Keep caller defaults.
        }
    }
}

Write-Host ("Stage: {0} (holdout floors: value/exact={1:0.00}, cite_f1={2:0.00}, exception={3:0.00}, large_snapshot={4:0.00})" -f $Stage, $effectiveHoldoutMinValueAcc, $effectiveHoldoutMinCiteF1, $effectiveHoldoutMinExceptionAcc, $effectiveHoldoutMinLargeSnapshotAcc)

if ($needGenerate) {
    $genArgs = @(".\scripts\generate_referential_indexing_suite_family.py")
    if ($OverwriteFixtures) { $genArgs += "--overwrite" }
    Invoke-PythonChecked -StepName "generate_referential_indexing_suite_family" -CommandArgs $genArgs
} else {
    Write-Host "Using existing referential_indexing_suite fixtures."
}

if ($UseRealPublicFixtures) {
    Invoke-PythonChecked -StepName "generate_real_public_fixtures" -CommandArgs @(
        ".\scripts\generate_real_public_family_fixtures.py",
        "--family", "referential_indexing_suite",
        "--overwrite"
    )
    $anchorsData = "data\referential_indexing_suite\referential_indexing_suite_anchors_real_public.jsonl"
    $holdoutData = "data\referential_indexing_suite\referential_indexing_suite_holdout_real_public.jsonl"
    $canaryData = "data\referential_indexing_suite\referential_indexing_suite_canary_real_public.jsonl"
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
    ".\scripts\score_referential_indexing_suite.py",
    "--data", $anchorsData,
    "--preds", $anchorsPreds,
    "--out", $anchorsSummary,
    "--rows-out", (Join-Path $OutRoot "anchors_rows.jsonl"),
    "--min-value-acc", "$effectiveAnchorsMinValueAcc",
    "--min-exact-acc", "$effectiveAnchorsMinExactAcc",
    "--min-cite-f1", "$effectiveAnchorsMinCiteF1",
    "--min-part-coverage-recall", "$effectiveAnchorsMinPartCoverageRecall",
    "--min-pointer-precision", "$effectiveAnchorsMinPointerPrecision",
    "--min-pointer-recall", "$effectiveAnchorsMinPointerRecall",
    "--min-reassembly-fidelity", "$effectiveAnchorsMinReassemblyFidelity",
    "--max-hallucinated-expansion-rate", "$effectiveAnchorsMaxHallucinatedExpansionRate",
    "--max-stale-pointer-override-rate", "$effectiveAnchorsMaxStalePointerOverrideRate",
    "--max-lookup-depth-cost", "$effectiveAnchorsMaxLookupDepthCost",
    "--min-exception-acc", "$effectiveAnchorsMinExceptionAcc",
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
    ".\scripts\score_referential_indexing_suite.py",
    "--data", $holdoutData,
    "--preds", $holdoutPreds,
    "--out", $holdoutSummary,
    "--rows-out", (Join-Path $OutRoot "holdout_rows.jsonl"),
    "--min-value-acc", "$effectiveHoldoutMinValueAcc",
    "--min-exact-acc", "$effectiveHoldoutMinExactAcc",
    "--min-cite-f1", "$effectiveHoldoutMinCiteF1",
    "--min-part-coverage-recall", "$effectiveHoldoutMinPartCoverageRecall",
    "--min-pointer-precision", "$effectiveHoldoutMinPointerPrecision",
    "--min-pointer-recall", "$effectiveHoldoutMinPointerRecall",
    "--min-reassembly-fidelity", "$effectiveHoldoutMinReassemblyFidelity",
    "--max-hallucinated-expansion-rate", "$effectiveHoldoutMaxHallucinatedExpansionRate",
    "--max-stale-pointer-override-rate", "$effectiveHoldoutMaxStalePointerOverrideRate",
    "--max-lookup-depth-cost", "$effectiveHoldoutMaxLookupDepthCost",
    "--min-exception-acc", "$effectiveHoldoutMinExceptionAcc",
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
    ".\scripts\score_referential_indexing_suite.py",
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
    benchmark = "referential_indexing_suite"
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

$combinedPath = Join-Path $OutRoot "referential_indexing_suite_summary.json"
$combined | ConvertTo-Json -Depth 14 | Set-Content -Path $combinedPath -Encoding UTF8
Write-Host "Wrote $combinedPath"
Write-Host ("hard_gate_status={0} canary_status={1} canary_gate_enforced={2}" -f $combined.hard_gate_status, $combined.canary_status, $combined.canary_gate_enforced)

if (-not $hardGatePass) {
    exit 1
}

if (($scoreAnchorsExit -ne 0) -or ($scoreHoldoutExit -ne 0) -or ($scoreCanaryExit -ne 0)) {
    exit 1
}

exit 0
