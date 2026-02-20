param(
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL,
    [string]$Adapter = "goldevidencebench.adapters.retrieval_llama_cpp_adapter:create_adapter",
    [string]$OutRoot = "",
    [double]$MinPolicyPass = 1.0,
    [double]$RagMinValueAcc = [double]::NaN,
    [double]$RagMinCiteF1 = [double]::NaN,
    [switch]$FailOnRagStrict
)

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
    $OutRoot = "runs\\trust_demo_$stamp"
}

New-Item -ItemType Directory -Path $OutRoot -Force | Out-Null

$summary = [ordered]@{
    out_root = $OutRoot
    generated_at = (Get-Date).ToString("o")
    steps = @()
    status = "PASS"
}

function Add-StepResult {
    param(
        [string]$Name,
        [string]$RunDir,
        [int]$ExitCode,
        [bool]$Required = $true
    )
    $status = if ($ExitCode -eq 0) { "PASS" } else { "FAIL" }
    $entry = [ordered]@{
        name = $Name
        status = $status
        exit_code = $ExitCode
        run_dir = $RunDir
        required = $Required
    }
    $summary.steps += $entry
    if ($Required -and $ExitCode -ne 0) {
        $summary.status = "FAIL"
    }
}

Write-Host "Trust demo"
Write-Host "OutRoot: $OutRoot"
Write-Host "Adapter: $Adapter"

$supportsDriftTrap = $Adapter -like "*retrieval_llama_cpp_adapter*"
$runRegressionCase = $supportsDriftTrap
if (-not $runRegressionCase) {
    Write-Warning "Adapter does not expose retrieval drift diagnostics; skipping regression_case step."
}

Write-Host "Step 1/4: Regression case (PASS + FAIL)"
$regOut = Join-Path $OutRoot "regression_case"
if ($runRegressionCase) {
    $regressionArgs = @{
        Adapter = $Adapter
        OutRoot = $regOut
        GenerateReports = $true
        ComparePassFail = $true
    }
    if ($ModelPath) {
        $regressionArgs.ModelPath = $ModelPath
    }
    .\scripts\run_regression_case.ps1 @regressionArgs | Out-Host
    $regCode = $LASTEXITCODE
    Add-StepResult -Name "regression_case" -RunDir $regOut -ExitCode $regCode -Required $true
    if ($regCode -ne 0) { Write-Error "Regression case failed."; }
} else {
    Add-StepResult -Name "regression_case" -RunDir $regOut -ExitCode 0 -Required $false
}

Write-Host "Step 2/4: Internal tooling benchmark"
$internalOut = Join-Path $OutRoot "internal_tooling_benchmark"
.\scripts\run_core_benchmark.ps1 -ConfigPath "configs\\internal_tooling_benchmark.json" -OutRoot $internalOut `
    -MinPolicyPass $MinPolicyPass | Out-Host
$internalCode = $LASTEXITCODE
Add-StepResult -Name "internal_tooling_benchmark" -RunDir $internalOut -ExitCode $internalCode -Required $true
if ($internalCode -ne 0) { Write-Error "Internal tooling benchmark failed."; }

Write-Host "Step 3/4: Compliance benchmark"
$complianceOut = Join-Path $OutRoot "compliance_benchmark"
.\scripts\run_core_benchmark.ps1 -ConfigPath "configs\\compliance_benchmark.json" -OutRoot $complianceOut `
    -MinPolicyPass $MinPolicyPass | Out-Host
$complianceCode = $LASTEXITCODE
Add-StepResult -Name "compliance_benchmark" -RunDir $complianceOut -ExitCode $complianceCode -Required $true
if ($complianceCode -ne 0) { Write-Error "Compliance benchmark failed."; }

Write-Host "Step 4/4: RAG benchmarks (lenient + strict)"
$ragLenientOut = Join-Path $OutRoot "rag_lenient"
$ragLenientParams = @{
    Preset = "lenient"
    Adapter = $Adapter
    OutRoot = $ragLenientOut
}
if ($ModelPath) {
    $ragLenientParams.ModelPath = $ModelPath
}
if (-not [double]::IsNaN($RagMinValueAcc)) { $ragLenientParams.MinValueAcc = $RagMinValueAcc }
if (-not [double]::IsNaN($RagMinCiteF1)) { $ragLenientParams.MinCiteF1 = $RagMinCiteF1 }
.\scripts\run_rag_benchmark.ps1 @ragLenientParams | Out-Host
$ragLenientCode = $LASTEXITCODE
Add-StepResult -Name "rag_benchmark_lenient" -RunDir $ragLenientOut -ExitCode $ragLenientCode -Required $true
if ($ragLenientCode -ne 0) { Write-Error "RAG lenient benchmark failed."; }

$ragStrictOut = Join-Path $OutRoot "rag_strict"
$ragStrictParams = @{
    Preset = "strict"
    Adapter = $Adapter
    OutRoot = $ragStrictOut
}
if ($ModelPath) {
    $ragStrictParams.ModelPath = $ModelPath
}
if (-not [double]::IsNaN($RagMinValueAcc)) { $ragStrictParams.MinValueAcc = $RagMinValueAcc }
if (-not [double]::IsNaN($RagMinCiteF1)) { $ragStrictParams.MinCiteF1 = $RagMinCiteF1 }
.\scripts\run_rag_benchmark.ps1 @ragStrictParams | Out-Host
$ragStrictCode = $LASTEXITCODE
Add-StepResult -Name "rag_benchmark_strict" -RunDir $ragStrictOut -ExitCode $ragStrictCode -Required:$FailOnRagStrict.IsPresent
if ($ragStrictCode -ne 0 -and $FailOnRagStrict) { Write-Error "RAG strict benchmark failed."; }

$summaryPath = Join-Path $OutRoot "trust_demo_summary.json"
$summary | ConvertTo-Json -Depth 6 | Set-Content -Path $summaryPath

$reportPath = Join-Path $OutRoot "trust_demo_report.md"
$lines = @(
    "# Trust Demo Report",
    "",
    "Out root: $OutRoot",
    "Status: $($summary.status)",
    "",
    "## Steps"
)
foreach ($step in $summary.steps) {
    $req = if ($step.required) { "required" } else { "optional" }
    $lines += "- {0}: {1} ({2}) - {3}" -f $step.name, $step.status, $req, $step.run_dir
}
$lines | Set-Content -Path $reportPath

$summaryJson = @{
    "artifact_version" = "1.0"
    "status" = $summary.status
    "steps_total" = $summary.steps.Count
    "steps_failed" = @($summary.steps | Where-Object { $_.status -ne "PASS" }).Count
    "generated_at" = $summary.generated_at
}
$summaryJson | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $OutRoot "summary.json")
$diagnosisJson = @{
    "status" = $summary.status
    "primary_bottleneck" = if ($summary.status -eq "PASS") { "none" } else { "trust_demo" }
    "supporting_metrics" = @{
        "trust_demo_steps_total" = $summary.steps.Count
        "trust_demo_steps_failed" = @($summary.steps | Where-Object { $_.status -ne "PASS" }).Count
    }
}
$diagnosisJson | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $OutRoot "diagnosis.json")
$compactJson = @{
    "run_dir" = $OutRoot
    "last_known_good" = @{
        "gate_artifacts" = @()
    }
}
$compactJson | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $OutRoot "compact_state.json")

$latestFile = "runs\\trust_demo_latest.txt"
$prevOut = ""
if (Test-Path $latestFile) {
    $prevOut = (Get-Content -Path $latestFile -Raw).Trim()
}
Set-Content -Path $latestFile -Value $OutRoot

if ($prevOut -and (Test-Path $prevOut)) {
    $deltaPath = Join-Path $OutRoot "trust_demo_delta_report.md"
    python .\scripts\compare_runs.py --base $prevOut --other $OutRoot --print | Out-Null
    python .\scripts\compare_runs.py --base $prevOut --other $OutRoot --out $deltaPath | Out-Host
}

Write-Host "Trust demo summary: $summaryPath"
Write-Host "Trust demo report: $reportPath"
if ($summary.status -ne "PASS") {
    exit 1
}
