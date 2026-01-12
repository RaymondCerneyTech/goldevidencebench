param(
    [string]$FixturePath = "data\\ui_minipilot_notepad_wrong_directory_detour_fixture.jsonl",
    [string]$ObservedPath = "data\\ui_minipilot_notepad_wrong_directory_detour_observed_ok.jsonl",
    [string]$OutPath = "runs\\ui_minipilot_notepad_wrong_directory_detour_search.json",
    [int]$Seeds = 1
)

if (-not (Test-Path $FixturePath)) {
    Write-Error "Fixture not found: $FixturePath"
    exit 1
}

if (-not (Test-Path $ObservedPath)) {
    Write-Error "Observed deltas not found: $ObservedPath"
    exit 1
}

Write-Host "UI minipilot notepad wrong-directory detour baseline"
Write-Host "Fixture: $FixturePath"
Write-Host "Observed: $ObservedPath"
Write-Host "Out: $OutPath"

python .\scripts\run_ui_search_baseline.py `
    --fixture $FixturePath `
    --observed $ObservedPath `
    --out $OutPath `
    --seeds $Seeds
