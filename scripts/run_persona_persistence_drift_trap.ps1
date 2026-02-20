param(
    [string]$CanonicalData,
    [string]$CanonicalPreds,
    [string]$OutRoot,
    [string]$Adapter,
    [string]$Protocol = "closed_book",
    [int]$MaxSupportK = 16,
    [string]$PersonaProfiles = "persona_confident_expert,persona_creative_writer,persona_ultra_brief,persona_overly_helpful",
    [double]$MinRowInvarianceRate = 1.0,
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
    $SummaryPath = Join-Path $OutRoot "persona_persistence_drift_summary.json"
}
if (-not $RowsPath) {
    $RowsPath = Join-Path $OutRoot "persona_persistence_drift_rows.jsonl"
}

$perturbedData = Join-Path $OutRoot "${Prefix}_persona_persistence_data.jsonl"
$perturbedPreds = Join-Path $OutRoot "${Prefix}_persona_persistence_preds.jsonl"

Invoke-PythonChecked -StepName "generate_persona_persistence_perturbations" -CommandArgs @(
    ".\scripts\generate_persona_persistence_perturbations.py",
    "--in", $CanonicalData,
    "--out", $perturbedData,
    "--profiles", $PersonaProfiles
)

Invoke-PythonChecked -StepName "model_persona_persistence_perturbed" -CommandArgs @(
    "-m", "goldevidencebench.cli", "model",
    "--data", $perturbedData,
    "--adapter", $Adapter,
    "--protocol", $Protocol,
    "--citations", "auto",
    "--max-support-k", "$MaxSupportK",
    "--out", $perturbedPreds
)

python .\scripts\score_persona_persistence_drift.py `
    --canonical-preds $CanonicalPreds `
    --perturbed-preds $perturbedPreds `
    --canonical-data $CanonicalData `
    --perturbed-data $perturbedData `
    --out $SummaryPath `
    --rows-out $RowsPath `
    --min-row-invariance-rate $MinRowInvarianceRate | Out-Host
$scoreExit = $LASTEXITCODE

if (Test-Path $SummaryPath) {
    try {
        $summary = Get-Content -Raw -Path $SummaryPath | ConvertFrom-Json
        Write-Host ("Persona persistence drift: status={0} row_invariance_rate={1} drift_rate={2}" -f `
            $summary.status, $summary.row_invariance_rate, $summary.drift_rate)
    } catch {
        Write-Warning "Unable to parse persona persistence drift summary: $SummaryPath"
    }
}

if ($scoreExit -ne 0) {
    exit $scoreExit
}
exit 0
