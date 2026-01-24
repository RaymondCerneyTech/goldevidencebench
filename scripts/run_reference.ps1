param(
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL,
    [ValidateSet("quick", "standard")]
    [string]$Preset = "quick"
,
    [float]$NoteRate = 0.12,
    [switch]$ComparePreferSetLatest
)

if (-not $ModelPath) {
    Write-Error "Set -ModelPath or GOLDEVIDENCEBENCH_MODEL before running."
    exit 1
}

$env:GOLDEVIDENCEBENCH_MODEL = $ModelPath

Write-Host "Running reference (latest_step)..."
.\scripts\run_selector_bench.ps1 -Preset $Preset -ModelPath $ModelPath -NoteRate $NoteRate -RerankMode latest_step

if ($ComparePreferSetLatest) {
    Write-Host "Running comparison (prefer_set_latest)..."
    .\scripts\run_selector_bench.ps1 -Preset $Preset -ModelPath $ModelPath -NoteRate $NoteRate -RerankMode prefer_set_latest
}

Write-Host "Collecting summaries..."
python .\scripts\collect_runs.py --runs-dir .\runs --out-csv .\runs\summary_all.csv --latest-only

Write-Host "Done. See runs\summary_all.csv for comparison."
