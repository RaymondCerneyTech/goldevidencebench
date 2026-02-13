param(
    [string]$CanonicalData,
    [string]$CanonicalPreds,
    [string]$OutRoot,
    [string]$Adapter,
    [string]$Protocol = "closed_book",
    [int]$MaxSupportK = 16,
    [string]$PersonaProfiles = "persona_confident_expert,persona_creative_writer,persona_ultra_brief,persona_overly_helpful",
    [string]$Prefix = "holdout",
    [string]$SummaryPath = "",
    [string]$RowsPath = ""
)

$ErrorActionPreference = "Stop"

function Invoke-PythonChecked {
    param([string[]]$CommandArgs, [string]$StepName)
    python @CommandArgs | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Step failed ($StepName) with exit code $LASTEXITCODE."
    }
}

if (-not $SummaryPath) {
    $SummaryPath = Join-Path $OutRoot "persona_invariance_summary.json"
}
if (-not $RowsPath) {
    $RowsPath = Join-Path $OutRoot "persona_invariance_rows.jsonl"
}

$personaData = Join-Path $OutRoot "${Prefix}_persona_data.jsonl"
$personaPreds = Join-Path $OutRoot "${Prefix}_persona_preds.jsonl"

Invoke-PythonChecked -StepName "generate_persona_perturbations" -CommandArgs @(
    ".\scripts\generate_persona_perturbations.py",
    "--in", $CanonicalData,
    "--out", $personaData,
    "--profiles", $PersonaProfiles
)

Invoke-PythonChecked -StepName "model_persona_holdout" -CommandArgs @(
    "-m", "goldevidencebench.cli", "model",
    "--data", $personaData,
    "--adapter", $Adapter,
    "--protocol", $Protocol,
    "--citations", "auto",
    "--max-support-k", "$MaxSupportK",
    "--out", $personaPreds
)

python .\scripts\score_persona_invariance.py `
    --canonical-preds $CanonicalPreds `
    --perturbed-preds $personaPreds `
    --canonical-data $CanonicalData `
    --perturbed-data $personaData `
    --out $SummaryPath `
    --rows-out $RowsPath | Out-Host
$scoreExit = $LASTEXITCODE

if (Test-Path $SummaryPath) {
    try {
        $summary = Get-Content -Raw -Path $SummaryPath | ConvertFrom-Json
        Write-Host ("Persona invariance: status={0} row_invariance_rate={1}" -f $summary.status, $summary.row_invariance_rate)
    } catch {
        Write-Warning "Unable to parse persona invariance summary: $SummaryPath"
    }
}

if ($scoreExit -ne 0) {
    exit $scoreExit
}
exit 0
