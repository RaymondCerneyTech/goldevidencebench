param(
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL,
    [int[]]$Steps = @(80, 120, 160, 200),
    [int]$Queries = 12,
    [int]$Seeds = 1,
    [string]$Adapter = "goldevidencebench.adapters.retrieval_llama_cpp_adapter:create_adapter",
    [string]$RunsDir = "",
    [ValidateSet("none", "latest_step", "prefer_set_latest")]
    [string]$Rerank = "none",
    [float]$NoteRate = 0.12,
    [int]$MaxBookTokens = 400,
    [float]$Threshold = 0.10,
    [ValidateSet("gte", "lte")]
    [string]$Direction = "gte",
    [switch]$UpdateConfig
)

if (-not $ModelPath) {
    Write-Error "Set -ModelPath or GOLDEVIDENCEBENCH_MODEL before running."
    exit 1
}

$finalRunsDir = $RunsDir
if (-not $finalRunsDir) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $finalRunsDir = "runs\\drift_wall_$stamp"
}
New-Item -ItemType Directory -Path $finalRunsDir -Force | Out-Null

$env:GOLDEVIDENCEBENCH_MODEL = $ModelPath
$env:GOLDEVIDENCEBENCH_RETRIEVAL_RERANK = $Rerank
$env:GOLDEVIDENCEBENCH_RETRIEVAL_WRONG_TYPE = "same_key"
$env:GOLDEVIDENCEBENCH_RETRIEVAL_ORDER = "shuffle"
$env:GOLDEVIDENCEBENCH_RETRIEVAL_ORDER_SEED = "0"

Write-Host "Drift wall sweep"
Write-Host "RunsDir: $finalRunsDir"
Write-Host "Steps: $($Steps -join ',')"
Write-Host "Seeds: $Seeds Queries: $Queries"
Write-Host "Rerank: $Rerank Adapter: $Adapter"

foreach ($step in $Steps) {
    $outDir = Join-Path $finalRunsDir "drift_steps$step"
    New-Item -ItemType Directory -Path $outDir -Force | Out-Null

    goldevidencebench sweep --out $outDir --seeds $Seeds --episodes 1 --steps $step --queries $Queries `
        --state-modes kv --distractor-profiles standard --note-rate $NoteRate `
        --no-derived-queries --no-twins --require-citations --max-book-tokens $MaxBookTokens `
        --adapter $Adapter --results-json "$outDir\combined.json"

    python .\scripts\summarize_results.py --in "$outDir\combined.json" --out-json "$outDir\summary.json"
}

$wallOut = Join-Path $finalRunsDir "drift_wall.json"
$wallArgs = @(
    "--runs-dir", $finalRunsDir,
    "--threshold", "$Threshold",
    "--direction", $Direction,
    "--metric", "drift.step_rate",
    "--param", "steps",
    "--aggregate", "max",
    "--out", $wallOut
)
if ($UpdateConfig) {
    $wallArgs += @("--update-config", ".\\configs\\usecase_checks.json", "--check-id", "drift_gate")
}
python .\scripts\find_drift_wall.py @wallArgs

$latestDir = "runs\\drift_wall_latest"
New-Item -ItemType Directory -Path $latestDir -Force | Out-Null
$maxStep = ($Steps | Measure-Object -Maximum).Maximum
$latestRun = Join-Path $finalRunsDir "drift_steps$maxStep"
$latestSummary = Join-Path $latestRun "summary.json"
if (Test-Path $latestSummary) {
    Copy-Item $latestSummary -Destination (Join-Path $latestDir "summary.json") -Force
}
if (Test-Path $wallOut) {
    Copy-Item $wallOut -Destination (Join-Path $latestDir "drift_wall.json") -Force
}
Write-Host "Latest drift snapshot: $latestDir"
