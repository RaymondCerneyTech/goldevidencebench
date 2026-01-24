param(
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL,
    [int]$Steps = 120,
    [int]$Keys = 4,
    [int]$Queries = 120,
    [int]$Seeds = 1,
    [string]$Adapter = "goldevidencebench.adapters.retrieval_llama_cpp_adapter:create_adapter",
    [ValidateSet("none", "latest_step", "prefer_set_latest")]
    [string]$Rerank = "latest_step",
    [ValidateSet("stale_tab_state", "focus_drift")]
    [string]$HoldoutName = "stale_tab_state",
    [string]$RunsDir = ""
)

if (-not $ModelPath) {
    Write-Error "Set -ModelPath or GOLDEVIDENCEBENCH_MODEL before running."
    exit 1
}

$finalRunsDir = $RunsDir
if (-not $finalRunsDir) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $finalRunsDir = "runs\\drift_holdout_$stamp"
}
New-Item -ItemType Directory -Path $finalRunsDir -Force | Out-Null

$env:GOLDEVIDENCEBENCH_MODEL = $ModelPath
$env:GOLDEVIDENCEBENCH_RETRIEVAL_RERANK = $Rerank
$env:GOLDEVIDENCEBENCH_RETRIEVAL_SELECTOR_ONLY = "1"
$env:GOLDEVIDENCEBENCH_RETRIEVAL_SELECTOR_VALUE = "1"
$env:GOLDEVIDENCEBENCH_RETRIEVAL_ORDER = "shuffle"
$env:GOLDEVIDENCEBENCH_RETRIEVAL_ORDER_SEED = "0"

Write-Host ("Drift holdout: {0}" -f $HoldoutName)
Write-Host "RunsDir: $finalRunsDir"
Write-Host "Steps: $Steps Keys: $Keys Queries: $Queries Seeds: $Seeds"
Write-Host "Rerank: $Rerank Adapter: $Adapter"

goldevidencebench sweep --out $finalRunsDir --seeds $Seeds --episodes 1 --steps $Steps --keys $Keys --queries $Queries `
    --state-modes kv_commentary --distractor-profiles $HoldoutName --note-rate 0.12 `
    --no-derived-queries --no-twins --require-citations --adapter $Adapter --results-json "$finalRunsDir\combined.json"

python .\scripts\summarize_results.py --in "$finalRunsDir\combined.json" --out-json "$finalRunsDir\summary.json"

$summaryPath = Join-Path $finalRunsDir "summary.json"
if (Test-Path $summaryPath) {
    python -c "import json; p=r'$summaryPath'; data=json.load(open(p,'r',encoding='utf-8')); drift=data.get('drift',{}); print('Holdout drift observed: drift.step_rate=%s' % drift.get('step_rate'))"
} else {
    Write-Warning "Missing summary.json at $summaryPath"
}
