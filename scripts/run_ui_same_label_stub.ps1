param(
    [string]$FixturePath = "data\\ui_same_label_fixture.jsonl",
    [string]$ConfigPath = "configs\\ui_same_label.json"
)

if (-not (Test-Path $ConfigPath)) {
    Write-Error "Config not found: $ConfigPath"
    exit 1
}

if (-not (Test-Path $FixturePath)) {
    Write-Error "Fixture not found: $FixturePath"
    exit 1
}

$lineCount = (Get-Content $FixturePath).Count
Write-Host "UI same_label stub"
Write-Host "Config: $ConfigPath"
Write-Host "Fixture: $FixturePath ($lineCount steps)"
python .\scripts\validate_ui_fixture.py --fixture $FixturePath
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
python .\scripts\score_ui_fixture.py --fixture $FixturePath --mode gold
python .\scripts\score_ui_fixture.py --fixture $FixturePath --mode first
python .\scripts\run_ui_adapter_stub.py --fixture $FixturePath
Write-Host "Adapter not implemented yet. Use this fixture to build the UI adapter."
