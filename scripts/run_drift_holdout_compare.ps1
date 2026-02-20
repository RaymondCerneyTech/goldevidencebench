param(
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL,
    [int]$Steps = 120,
    [int]$Keys = 4,
    [int]$Queries = 120,
    [int]$Seeds = 1,
    [string]$Adapter = "goldevidencebench.adapters.retrieval_llama_cpp_adapter:create_adapter",
    [ValidateSet("none", "latest_step", "prefer_set_latest")]
    [string]$BaselineRerank = "latest_step",
    [ValidateSet("none", "latest_step", "prefer_set_latest")]
    [string]$FixRerank = "prefer_set_latest",
    [ValidateSet("stale_tab_state", "focus_drift")]
    [string]$HoldoutName = "stale_tab_state",
    [bool]$BaselineAuthorityFilter = $false,
    [bool]$FixAuthorityFilter = $true,
    [double]$MinDelta = 0.01,
    [string]$OutPath = "runs\\drift_holdout_compare_latest.json",
    [string]$RunsDir = ""
)

$requiresModelPath = $Adapter -like "*llama_cpp*"
if ($requiresModelPath -and -not $ModelPath) {
    Write-Error "Set -ModelPath or GOLDEVIDENCEBENCH_MODEL before running with llama_cpp adapters."
    exit 1
}
if ($ModelPath) {
    $env:GOLDEVIDENCEBENCH_MODEL = $ModelPath
}

$finalRunsDir = $RunsDir
if (-not $finalRunsDir) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $finalRunsDir = "runs\\drift_holdout_compare_$stamp"
}
New-Item -ItemType Directory -Path $finalRunsDir -Force | Out-Null
$outParent = Split-Path -Parent $OutPath
if (-not [string]::IsNullOrWhiteSpace($outParent)) {
    New-Item -ItemType Directory -Path $outParent -Force | Out-Null
}

$holdoutScript = Join-Path $PSScriptRoot "run_drift_holdouts.ps1"

function Get-DriftRate {
    param([string]$SummaryPath)
    if (-not (Test-Path $SummaryPath)) {
        return $null
    }
    $data = Get-Content -Raw -Path $SummaryPath | ConvertFrom-Json
    if ($null -eq $data.drift) {
        return $null
    }
    return $data.drift.step_rate
}

function Invoke-Holdout {
    param(
        [string]$Label,
        [string]$Rerank,
        [bool]$AuthorityFilter
    )
    $env:GOLDEVIDENCEBENCH_RETRIEVAL_AUTHORITY_FILTER = if ($AuthorityFilter) { "1" } else { "0" }
    $outDir = Join-Path $finalRunsDir $Label
    $holdoutArgs = @{
        Steps = $Steps
        Keys = $Keys
        Queries = $Queries
        Seeds = $Seeds
        Rerank = $Rerank
        Adapter = $Adapter
        RunsDir = $outDir
        HoldoutName = $HoldoutName
    }
    if ($ModelPath) {
        $holdoutArgs.ModelPath = $ModelPath
    }
    & $holdoutScript @holdoutArgs | Out-Host
    if (-not $?) {
        throw "Holdout run failed for $Label"
    }
    $summaryPath = Join-Path $outDir "summary.json"
    return [ordered]@{
        label = $Label
        rerank = $Rerank
        authority_filter = $AuthorityFilter
        run_dir = $outDir
        summary_path = $summaryPath
        drift_step_rate = Get-DriftRate -SummaryPath $summaryPath
    }
}

Write-Host "Drift holdout compare"
Write-Host "RunsDir: $finalRunsDir"
Write-Host ("Baseline: rerank={0} authority_filter={1}" -f $BaselineRerank, $BaselineAuthorityFilter)
Write-Host ("Fix: rerank={0} authority_filter={1}" -f $FixRerank, $FixAuthorityFilter)

$baseline = Invoke-Holdout -Label "baseline_$BaselineRerank" -Rerank $BaselineRerank -AuthorityFilter $BaselineAuthorityFilter
$fix = Invoke-Holdout -Label "fix_$FixRerank" -Rerank $FixRerank -AuthorityFilter $FixAuthorityFilter
$baselineRateNum = if ($null -ne $baseline.drift_step_rate) { [double]$baseline.drift_step_rate } else { $null }
$fixRateNum = if ($null -ne $fix.drift_step_rate) { [double]$fix.drift_step_rate } else { $null }
$delta = $null
if ($null -ne $baselineRateNum -and $null -ne $fixRateNum) {
    $delta = $baselineRateNum - $fixRateNum
}
$improved = $false
if ($null -ne $delta) {
    $improved = $delta -ge $MinDelta
}

$status = "FAIL"
$statusReason = "missing_rates"
if ($null -ne $baselineRateNum -and $null -ne $fixRateNum) {
    if ($baselineRateNum -le 0.001) {
        $status = "PASS"
        $statusReason = "baseline_already_low_drift"
    } elseif ($improved) {
        $status = "PASS"
        $statusReason = "drift_reduced"
    } else {
        $status = "FAIL"
        $statusReason = "drift_not_reduced"
    }
}

$payload = [ordered]@{
    benchmark = "drift_holdout_compare"
    generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    status = $status
    status_reason = $statusReason
    adapter = $Adapter
    holdout = $HoldoutName
    min_delta = $MinDelta
    baseline = $baseline
    fix = $fix
    delta = $delta
    improved = $improved
    runs_dir = $finalRunsDir
}
$payload | ConvertTo-Json -Depth 8 | Set-Content -Path $OutPath -Encoding UTF8
.\scripts\set_latest_pointer.ps1 -RunDir $OutPath -PointerPath "runs\\latest_drift_holdout_compare" | Out-Host

Write-Host "Baseline rerank: $BaselineRerank drift.step_rate=$baselineRateNum"
Write-Host "Fix rerank: $FixRerank drift.step_rate=$fixRateNum"
if ($null -ne $delta) {
    Write-Host ("Delta (baseline-fix)={0} improved={1}" -f $delta, $improved)
}
Write-Host ("drift_holdout_compare status={0} reason={1} out={2}" -f $status, $statusReason, $OutPath)

if ($status -ne "PASS") {
    exit 1
}
