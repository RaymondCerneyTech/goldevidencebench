param(
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL,
    [string]$Adapter = "goldevidencebench.adapters.retrieval_llama_cpp_adapter:create_adapter",
    [string]$Protocol = "closed_book",
    [int]$MaxSupportK = 16,
    [string]$CanonicalData = "",
    [int]$MaxBaseRows = 0,
    [int]$Sessions = 8,
    [int]$Turns = 12,
    [string]$Profiles = "persona_confident_expert,persona_creative_writer,persona_ultra_brief,persona_overly_helpful",
    [ValidateSet("auto", "required", "optional", "disabled")]
    [string]$StyleMarkerMode = "auto",
    [switch]$ForceRequireProfileMarker,
    [switch]$ForceRequireSupportMatch,
    [double]$MaxDriftRate = 0.0,
    [double]$MinProfileMatchRate = 1.0,
    [double]$MaxProfileFlipRate = 0.0,
    [double]$MinFactualMatchRate = 1.0,
    [int]$SampleLimit = 20,
    [string]$OutRoot = "",
    [string]$Prefix = "holdout",
    [string]$SummaryPath = "",
    [string]$RowsPath = "",
    [string]$ReportPath = ""
)

$ErrorActionPreference = "Stop"

function Invoke-PythonChecked {
    param([string[]]$CommandArgs, [string]$StepName)
    python @CommandArgs | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Step failed ($StepName) with exit code $LASTEXITCODE."
    }
}

function Test-TruthyEnv {
    param([string]$Name)
    $value = [Environment]::GetEnvironmentVariable($Name, "Process")
    if (-not $value) {
        return $false
    }
    $normalized = $value.Trim().ToLowerInvariant()
    return $normalized -in @("1", "true", "yes")
}

$requiresModelPath = $Adapter -like "*llama_cpp*"
if ($requiresModelPath -and -not $ModelPath) {
    Write-Error "Set -ModelPath or GOLDEVIDENCEBENCH_MODEL before running with llama_cpp adapters."
    exit 1
}
if ($ModelPath) {
    $env:GOLDEVIDENCEBENCH_MODEL = $ModelPath
}

if (-not $OutRoot) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutRoot = "runs\\persona_session_drift_$stamp"
}
New-Item -ItemType Directory -Path $OutRoot -Force | Out-Null

if (-not $SummaryPath) {
    $SummaryPath = Join-Path $OutRoot "persona_session_drift_summary.json"
}
if (-not $RowsPath) {
    $RowsPath = Join-Path $OutRoot "persona_session_drift_rows.jsonl"
}
if (-not $ReportPath) {
    $ReportPath = Join-Path $OutRoot "persona_session_drift_report.md"
}

$sessionData = Join-Path $OutRoot "${Prefix}_persona_session_drift_data.jsonl"
$sessionPreds = Join-Path $OutRoot "${Prefix}_persona_session_drift_preds.jsonl"

$resolvedStyleMarkerMode = $StyleMarkerMode
if ($resolvedStyleMarkerMode -eq "auto") {
    if ($Adapter -like "*retrieval_llama_cpp_adapter*") {
        $resolvedStyleMarkerMode = "disabled"
    } else {
        $resolvedStyleMarkerMode = "required"
    }
}
$requireProfileMarker = $true
if ($resolvedStyleMarkerMode -eq "disabled") {
    $requireProfileMarker = $false
}
if ($ForceRequireProfileMarker) {
    $requireProfileMarker = $true
}
$requireSupportMatch = $true
if ($resolvedStyleMarkerMode -eq "disabled") {
    $requireSupportMatch = $false
}
if ($ForceRequireSupportMatch) {
    $requireSupportMatch = $true
}
if ($resolvedStyleMarkerMode -eq "disabled") {
    if (-not $PSBoundParameters.ContainsKey("MinFactualMatchRate")) {
        $MinFactualMatchRate = 0.85
    }
    if (-not $PSBoundParameters.ContainsKey("MaxDriftRate")) {
        $MaxDriftRate = 0.15
    }
}
if ($Adapter -like "*retrieval_llama_cpp_adapter*") {
    if (Test-TruthyEnv -Name "GOLDEVIDENCEBENCH_RETRIEVAL_SELECTOR_ONLY") {
        Write-Error @"
GOLDEVIDENCEBENCH_RETRIEVAL_SELECTOR_ONLY is enabled in this shell.
Persona-session drift trap requires answerer mode (selector-only returns empty values).
Run:  `$env:GOLDEVIDENCEBENCH_RETRIEVAL_SELECTOR_ONLY='0'`  and retry.
"@
        exit 1
    }
}
Write-Host ("Persona session mode: style_marker_mode={0} require_profile_marker={1} require_support_match={2}" -f `
    $resolvedStyleMarkerMode, $requireProfileMarker, $requireSupportMatch)
Write-Host ("Persona session thresholds: min_factual_match_rate={0} max_drift_rate={1} max_profile_flip_rate={2}" -f `
    $MinFactualMatchRate, $MaxDriftRate, $MaxProfileFlipRate)

$generateArgs = @(
    ".\scripts\generate_persona_session_drift_dataset.py",
    "--out", $sessionData,
    "--sessions", "$Sessions",
    "--turns", "$Turns",
    "--profiles", $Profiles,
    "--style-marker-mode", $resolvedStyleMarkerMode
)
if ($CanonicalData) {
    $generateArgs += @("--canonical-data", $CanonicalData)
    if ($MaxBaseRows -gt 0) {
        $generateArgs += @("--max-base-rows", "$MaxBaseRows")
    }
}
Invoke-PythonChecked -StepName "generate_persona_session_drift_dataset" -CommandArgs $generateArgs

Invoke-PythonChecked -StepName "model_persona_session_drift" -CommandArgs @(
    "-m", "goldevidencebench.cli", "model",
    "--data", $sessionData,
    "--adapter", $Adapter,
    "--protocol", $Protocol,
    "--citations", "auto",
    "--max-support-k", "$MaxSupportK",
    "--out", $sessionPreds
)

if (-not (Test-Path $sessionPreds)) {
    Write-Error "Persona session drift predictions artifact missing: $sessionPreds"
    exit 1
}
$predRows = @()
try {
    $predRows = @(Get-Content -Path $sessionPreds | ForEach-Object { $_ | ConvertFrom-Json })
} catch {
    Write-Error ("Unable to parse predictions artifact: {0} ({1})" -f $sessionPreds, $_.Exception.Message)
    exit 1
}
if ($predRows.Count -gt 0) {
    $emptyValueRows = @(
        $predRows | Where-Object {
            $value = $_.value
            $null -eq $value -or "$value".Trim() -eq ""
        }
    ).Count
    if ($emptyValueRows -eq $predRows.Count) {
        Write-Error @"
All persona-session predictions are empty values.
This indicates retrieval answer generation did not run (or was forced into selector-only behavior).
Check:
  - adapter: $Adapter
  - model path exists and is readable
  - env flag GOLDEVIDENCEBENCH_RETRIEVAL_SELECTOR_ONLY is 0/unset
  - run from repo root with local source active (`src/goldevidencebench/...`)
"@
        exit 1
    }
}

$profileFlag = if ($requireProfileMarker) { "--require-profile-marker" } else { "--no-require-profile-marker" }
$supportFlag = if ($requireSupportMatch) { "--require-support-match" } else { "--no-require-support-match" }
python .\scripts\score_persona_session_drift.py `
    --data $sessionData `
    --preds $sessionPreds `
    --out $SummaryPath `
    --rows-out $RowsPath `
    --report-out $ReportPath `
    --max-drift-rate $MaxDriftRate `
    --min-profile-match-rate $MinProfileMatchRate `
    --max-profile-flip-rate $MaxProfileFlipRate `
    --min-factual-match-rate $MinFactualMatchRate `
    --sample-limit $SampleLimit `
    $profileFlag `
    $supportFlag | Out-Host
$scoreExit = $LASTEXITCODE

if (Test-Path $SummaryPath) {
    try {
        $summary = Get-Content -Raw -Path $SummaryPath | ConvertFrom-Json
        Write-Host ("Persona session drift: status={0} profile_match_rate={1} factual_match_rate={2} drift_rate={3} profile_flip_rate={4}" -f `
            $summary.status, $summary.profile_match_rate, $summary.factual_match_rate, $summary.drift_rate, $summary.profile_flip_rate)
    } catch {
        Write-Warning "Unable to parse persona session drift summary: $SummaryPath"
    }
    .\scripts\set_latest_pointer.ps1 -RunDir $SummaryPath -PointerPath "runs\\latest_persona_session_drift" | Out-Host
}
if (Test-Path $ReportPath) {
    .\scripts\set_latest_pointer.ps1 -RunDir $ReportPath -PointerPath "runs\\latest_persona_session_drift_report" | Out-Host
}

if ($scoreExit -ne 0) {
    exit $scoreExit
}
exit 0
