param(
    [string]$OutRoot = "runs\cross_app_intent_preservation_pack",
    [string]$Adapter = "goldevidencebench.adapters.mock_adapter:create_adapter",
    [ValidateSet("observe", "target")]
    [string]$Stage = "target",
    [ValidateSet("fixture", "live-smoke", "hybrid")]
    [string]$DataMode = "fixture",
    [switch]$FailOnCanaryWarn
)

$ErrorActionPreference = "Stop"

function Invoke-SplitScore {
    param(
        [string]$SplitName,
        [string]$SplitStage
    )

    $dataPath = Join-Path $OutRoot "$($SplitName)_data.jsonl"
    $predPath = Join-Path $OutRoot "$($SplitName)_predictions.jsonl"
    $summaryPath = Join-Path $OutRoot "$($SplitName)_summary.json"
    $rowsPath = Join-Path $OutRoot "$($SplitName)_rows.jsonl"

    python -m goldevidencebench model `
        --data $dataPath `
        --adapter $Adapter `
        --protocol closed_book `
        --out $predPath | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Model run failed for split=$SplitName"
    }

    python .\scripts\score_cross_app_intent_preservation_pack.py `
        --data $dataPath `
        --pred $predPath `
        --stage $SplitStage `
        --out-summary $summaryPath `
        --out-rows $rowsPath | Out-Host
    $exitCode = $LASTEXITCODE
    $summary = Get-Content $summaryPath -Raw | ConvertFrom-Json
    return @{
        split = $SplitName
        stage = $SplitStage
        exit_code = $exitCode
        summary_path = $summaryPath
        rows_path = $rowsPath
        summary = $summary
    }
}

Write-Host "Cross-app intent-preservation pack run"
Write-Host "OutRoot: $OutRoot"
Write-Host "Adapter: $Adapter"
Write-Host "Stage: $Stage"
Write-Host "DataMode: $DataMode"

New-Item -ItemType Directory -Path $OutRoot -Force | Out-Null

python .\scripts\generate_cross_app_intent_preservation_pack.py --out-root $OutRoot | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Generator failed."
}

$anchors = Invoke-SplitScore -SplitName "anchors" -SplitStage "observe"
$holdout = Invoke-SplitScore -SplitName "holdout" -SplitStage $Stage
$canary = Invoke-SplitScore -SplitName "canary" -SplitStage "observe"

$canaryValueAcc = [double]($canary.summary.means.value_acc)
$canaryStatus = if ($canaryValueAcc -gt 0.50) { "WARN" } else { "OK" }

$liveSmokeSummaryPath = Join-Path $OutRoot "live_smoke_summary.json"
$liveSmokeRowsPath = Join-Path $OutRoot "live_smoke_rows.jsonl"
$liveSmokeStatus = "SKIP"
if ($DataMode -in @("live-smoke", "hybrid")) {
    $liveSmoke = Invoke-SplitScore -SplitName "live_smoke" -SplitStage "observe"
    $liveSmokeStatus = [string]$liveSmoke.summary.status
    Copy-Item $liveSmoke.summary_path $liveSmokeSummaryPath -Force
    Copy-Item $liveSmoke.rows_path $liveSmokeRowsPath -Force
} else {
    $skipPayload = @{
        benchmark = "cross_app_intent_preservation_pack"
        stage = "observe"
        status = "SKIP"
        reason = "data_mode_fixture"
    }
    $skipPayload | ConvertTo-Json -Depth 6 | Set-Content -Path $liveSmokeSummaryPath
    "" | Set-Content -Path $liveSmokeRowsPath
}

$hardGateStatus = if ($holdout.exit_code -eq 0) { "PASS" } else { "FAIL" }
$canaryGateEnforced = [bool]$FailOnCanaryWarn
if ($canaryGateEnforced -and $canaryStatus -eq "WARN") {
    $hardGateStatus = "FAIL"
}

$summaryPath = Join-Path $OutRoot "cross_app_intent_preservation_pack_summary.json"
$rowsPath = Join-Path $OutRoot "cross_app_intent_preservation_pack_rows.jsonl"
Copy-Item $holdout.rows_path $rowsPath -Force

$summary = @{
    benchmark = "cross_app_intent_preservation_pack"
    status = if ($hardGateStatus -eq "PASS") { "PASS" } else { "FAIL" }
    stage = $Stage
    adapter = $Adapter
    data_mode = $DataMode
    hard_gate_status = $hardGateStatus
    canary_status = $canaryStatus
    canary_gate_enforced = $canaryGateEnforced
    anchors = $anchors.summary
    holdout = $holdout.summary
    canary = $canary.summary
    live_smoke = (Get-Content $liveSmokeSummaryPath -Raw | ConvertFrom-Json)
    artifacts = @{
        anchors_summary = $anchors.summary_path
        holdout_summary = $holdout.summary_path
        canary_summary = $canary.summary_path
        live_smoke_summary = $liveSmokeSummaryPath
        rows = $rowsPath
    }
}
$summary | ConvertTo-Json -Depth 12 | Set-Content -Path $summaryPath

$pointerScript = ".\scripts\set_latest_pointer.ps1"
if (Test-Path $pointerScript) {
    & $pointerScript -RunDir $summaryPath -PointerPath "runs\latest_cross_app_intent_preservation_pack" | Out-Host
}

Write-Host "Wrote $summaryPath"
Write-Host "hard_gate_status=$hardGateStatus canary_status=$canaryStatus canary_gate_enforced=$canaryGateEnforced"

if ($hardGateStatus -ne "PASS") {
    exit 1
}
exit 0
