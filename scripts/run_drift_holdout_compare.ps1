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
    [switch]$AuthorityFilter,
    [string]$RunsDir = ""
)

if (-not $ModelPath) {
    Write-Error "Set -ModelPath or GOLDEVIDENCEBENCH_MODEL before running."
    exit 1
}

$finalRunsDir = $RunsDir
if (-not $finalRunsDir) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $finalRunsDir = "runs\\drift_holdout_compare_$stamp"
}
New-Item -ItemType Directory -Path $finalRunsDir -Force | Out-Null

if ($AuthorityFilter.IsPresent) {
    $env:GOLDEVIDENCEBENCH_RETRIEVAL_AUTHORITY_FILTER = "1"
} else {
    $env:GOLDEVIDENCEBENCH_RETRIEVAL_AUTHORITY_FILTER = "0"
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
        [string]$Rerank
    )
    $outDir = Join-Path $finalRunsDir $Label
    & $holdoutScript -ModelPath $ModelPath -Steps $Steps -Keys $Keys -Queries $Queries -Seeds $Seeds `
        -Rerank $Rerank -Adapter $Adapter -RunsDir $outDir -HoldoutName $HoldoutName | Out-Host
    if (-not $?) {
        throw "Holdout run failed for $Label"
    }
    $summaryPath = Join-Path $outDir "summary.json"
    return Get-DriftRate -SummaryPath $summaryPath
}

Write-Host "Drift holdout compare"
Write-Host "RunsDir: $finalRunsDir"
Write-Host "AuthorityFilter: $($AuthorityFilter.IsPresent)"

$baselineRate = Invoke-Holdout -Label "baseline_$BaselineRerank" -Rerank $BaselineRerank
$fixRate = Invoke-Holdout -Label "fix_$FixRerank" -Rerank $FixRerank
$baselineRateNum = if ($null -ne $baselineRate) { [double]$baselineRate } else { $null }
$fixRateNum = if ($null -ne $fixRate) { [double]$fixRate } else { $null }

Write-Host "Baseline rerank: $BaselineRerank drift.step_rate=$baselineRateNum"
Write-Host "Fix rerank: $FixRerank drift.step_rate=$fixRateNum"

if ($null -ne $baselineRateNum -and $null -ne $fixRateNum) {
    if ($baselineRateNum -le 0.001) {
        Write-Host "Baseline drift already zero; fix not needed."
    } elseif ($fixRateNum -lt $baselineRateNum) {
        Write-Host "Drift reduced."
    } else {
        Write-Host "Drift not reduced; inspect summary.json for details."
    }
}
