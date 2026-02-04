param(
    [ValidateSet("smoke", "standard")]
    [string]$Preset = "smoke",
    [string]$Adapter = "goldevidencebench.adapters.mock_adapter:create_adapter",
    [string]$OutRoot = "runs",
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL
)

$ErrorActionPreference = "Stop"

if ($ModelPath) {
    $env:GOLDEVIDENCEBENCH_MODEL = $ModelPath
}

if ($Preset -eq "smoke") {
    $seeds = 1
    $steps = 60
    $queries = 6
} else {
    $seeds = 2
    $steps = 120
    $queries = 12
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$runDir = Join-Path $OutRoot "adapter_baseline_${Preset}_$stamp"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

$combinedPath = Join-Path $runDir "combined.json"

goldevidencebench sweep --out $runDir --seeds $seeds --episodes 1 --steps $steps --queries $queries `
  --state-modes kv --distractor-profiles standard --note-rate 0.12 `
  --adapter $Adapter --no-derived-queries --no-twins --require-citations `
  --results-json $combinedPath
if (-not $?) {
    exit 1
}

python .\scripts\summarize_results.py --in $combinedPath --out-json (Join-Path $runDir "summary.json")
$exitCode = $LASTEXITCODE

$pointer = if ($Preset -eq "smoke") { "runs\\latest_smoke" } else { "runs\\latest_adapter_baseline" }
.\scripts\set_latest_pointer.ps1 -RunDir $runDir -PointerPath $pointer | Out-Host

exit $exitCode
