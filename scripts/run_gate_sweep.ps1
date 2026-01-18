param(
    [string]$FixtureGlob = "data\\ui_minipilot_local_optimum_*_fixture.jsonl",
    [switch]$IncludeAmbiguous,
    [switch]$ForceTrain,
    [string]$ModelsDir = "models",
    [string]$RunsDir = "runs"
)

$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Force $ModelsDir,$RunsDir | Out-Null

$fixtures = Get-ChildItem $FixtureGlob
if (-not $IncludeAmbiguous) {
    $fixtures = $fixtures | Where-Object { $_.Name -notmatch "_ambiguous" }
}

foreach ($f in $fixtures) {
    $family = $f.BaseName -replace '^ui_minipilot_local_optimum_','' -replace '_fixture$',''
    $observed = "data\\ui_minipilot_local_optimum_${family}_observed_ok.jsonl"
    $model = Join-Path $ModelsDir ("ui_gate_{0}.json" -f $family)
    $gateOut = Join-Path $RunsDir ("ui_gate_{0}.json" -f $family)
    $searchOut = Join-Path $RunsDir ("ui_{0}_gate_search.json" -f $family)
    $searchCsv = Join-Path $RunsDir ("ui_{0}_gate_search.csv" -f $family)

    if (-not (Test-Path $observed)) {
        Write-Host "skip missing observed: $observed"
        continue
    }

    if ((-not (Test-Path $model)) -or $ForceTrain) {
        python .\scripts\train_ui_gate.py --fixture $f.FullName --observed $observed --out-model $model
        if ($LASTEXITCODE -ne 0) { throw "train_ui_gate failed for $family" }
    } else {
        Write-Host "skip existing model: $model"
    }

    python .\scripts\run_ui_gate_baseline.py --fixture $f.FullName --observed $observed --model $model --out $gateOut
    if ($LASTEXITCODE -ne 0) { throw "run_ui_gate_baseline failed for $family" }

    python .\scripts\run_ui_search_baseline.py --fixture $f.FullName --observed $observed --gate-model $model --out $searchOut --out-csv $searchCsv
    if ($LASTEXITCODE -ne 0) { throw "run_ui_search_baseline failed for $family" }
}
