param(
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL,
    [string]$Adapter = "goldevidencebench.adapters.retrieval_llama_cpp_adapter:create_adapter",
    [string]$PdfPath = "",
    [string]$OutRoot = "",
    [int]$MaxRows = 24,
    [ValidateSet("bm25", "dense")][string]$RetrieverMode = "bm25",
    [int]$TopK = 3,
    [switch]$SkipOpenBook,
    [switch]$SkipRegressionCase,
    [switch]$SkipBadActor
)

$resolvedModelPath = $ModelPath
if ($resolvedModelPath -and $resolvedModelPath.Contains("<")) {
    $resolvedModelPath = $env:GOLDEVIDENCEBENCH_MODEL
}
if ($resolvedModelPath -and $resolvedModelPath.Contains("<")) {
    $resolvedModelPath = ""
}
$adapterRequiresModelPath = $Adapter -like "*llama_cpp*"
if ($adapterRequiresModelPath -and -not $resolvedModelPath) {
    Write-Error "Set -ModelPath or GOLDEVIDENCEBENCH_MODEL before running with llama_cpp adapters."
    exit 1
}
if ($resolvedModelPath) {
    $env:GOLDEVIDENCEBENCH_MODEL = $resolvedModelPath
}

if (-not $OutRoot) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutRoot = "runs\\case_pack_$stamp"
}
New-Item -ItemType Directory -Path $OutRoot -Force | Out-Null

function Read-Json {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        return $null
    }
    try {
        return Get-Content -Raw -Path $Path | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Format-Num {
    param($Value, [int]$Digits = 3)
    if ($null -eq $Value) { return "n/a" }
    try {
        return ("{0:N$Digits}" -f [double]$Value)
    } catch {
        return "n/a"
    }
}

function Join-OptionalPath {
    param(
        [string]$BasePath,
        [string]$RelativePath
    )
    if ([string]::IsNullOrWhiteSpace($BasePath) -or [string]::IsNullOrWhiteSpace($RelativePath)) {
        return "n/a"
    }
    return (Join-Path $BasePath $RelativePath)
}

$summary = [ordered]@{
    artifact_version = "1.0"
    out_root = $OutRoot
    model_id = $(if ($resolvedModelPath) { Split-Path -Leaf $resolvedModelPath } else { $Adapter })
    generated_at = (Get-Date).ToString("o")
    status = "PASS"
    steps = @()
}

function Add-Step {
    param(
        [string]$Name,
        [string]$Status,
        [string]$RunDir,
        [bool]$Required = $true,
        [hashtable]$Details = @{}
    )
    $entry = [ordered]@{
        name = $Name
        status = $Status
        run_dir = $RunDir
        required = $Required
        details = $Details
    }
    $summary.steps += $entry
    if ($Required -and $Status -ne "PASS") {
        $summary.status = "FAIL"
    }
}

Write-Host "Case pack"
Write-Host "OutRoot: $OutRoot"
Write-Host "Adapter: $Adapter"

$supportsDriftTrap = $Adapter -like "*retrieval_llama_cpp_adapter*"
$runRegressionCase = -not $SkipRegressionCase
$runBadActor = -not $SkipBadActor
if (-not $supportsDriftTrap) {
    if ($runRegressionCase) {
        Write-Warning "Adapter does not expose retrieval drift diagnostics; skipping regression_case step."
    }
    if ($runBadActor) {
        Write-Warning "Adapter does not expose retrieval drift diagnostics; skipping bad_actor_demo step."
    }
    $runRegressionCase = $false
    $runBadActor = $false
}

$resolvedPdfPath = $PdfPath
if ($resolvedPdfPath -and $resolvedPdfPath.Contains("<")) {
    $resolvedPdfPath = ""
}
$openBookReady = $true
$openBookSkipReason = ""
if (-not $resolvedPdfPath) {
    $pdfs = Get-ChildItem -Path . -Filter *.pdf -File
    if ($pdfs.Count -eq 1) {
        $resolvedPdfPath = $pdfs[0].FullName
    } elseif ($pdfs.Count -eq 0) {
        $openBookReady = $false
        $openBookSkipReason = "No PDF found in repo root. Pass -PdfPath or use -SkipOpenBook."
    } else {
        $openBookReady = $false
        $openBookSkipReason = "Multiple PDFs found in repo root. Pass -PdfPath or use -SkipOpenBook."
    }
}
if ($resolvedPdfPath -and -not (Test-Path -LiteralPath $resolvedPdfPath)) {
    Write-Error "PdfPath not found: $resolvedPdfPath"
    exit 1
}

# RAG closed-book strict
$ragClosedDir = Join-Path $OutRoot "rag_closed_book_strict"
Write-Host "Step 1/4: RAG closed-book strict (expected FAIL)"
$ragClosedArgs = @{
    Preset = "strict"
    Adapter = $Adapter
    OutRoot = $ragClosedDir
    MaxRows = $MaxRows
}
if ($resolvedModelPath) {
    $ragClosedArgs.ModelPath = $resolvedModelPath
}
.\scripts\run_rag_benchmark.ps1 @ragClosedArgs | Out-Host
$ragClosedCode = $LASTEXITCODE
$ragClosedSummary = Read-Json (Join-Path $ragClosedDir "summary.json")
$ragClosedMeans = if ($ragClosedSummary) { $ragClosedSummary.means } else { $null }
Add-Step -Name "rag_closed_book_strict" -Status ($(if ($ragClosedCode -eq 0) { "PASS" } else { "FAIL" })) `
    -RunDir $ragClosedDir -Required $false -Details @{
        value_acc = $ragClosedMeans.value_acc
        cite_f1 = $ragClosedMeans.cite_f1
        retrieval_hit_rate = $ragClosedMeans.retrieval_hit_rate
    }

# RAG open-book demo
$ragOpenDir = Join-Path $OutRoot "rag_open_book"
if (-not $SkipOpenBook -and $openBookReady) {
    $summary.source_pdf = (Split-Path -Leaf $resolvedPdfPath)
    Write-Host "Step 2/4: RAG open-book demo"
    $openArgs = @{
        PdfPath = $resolvedPdfPath
        ModelPath = $resolvedModelPath
        OutRoot = $ragOpenDir
        RetrieverMode = $RetrieverMode
        TopK = $TopK
        MaxRows = $MaxRows
    }
    .\scripts\run_rag_open_book_demo.ps1 @openArgs | Out-Host
    $ragOpenCode = $LASTEXITCODE
    $ragOpenSummary = Read-Json (Join-Path $ragOpenDir "rag_open_book_run\\summary.json")
    $ragOpenMeans = if ($ragOpenSummary) { $ragOpenSummary.means } else { $null }
    $ragOpenRuntime = if ($ragOpenSummary) { $ragOpenSummary.runtime } else { $null }
    Add-Step -Name "rag_open_book" -Status ($(if ($ragOpenCode -eq 0) { "PASS" } else { "FAIL" })) `
        -RunDir $ragOpenDir -Required $true -Details @{
            value_acc = $ragOpenMeans.value_acc
            cite_f1 = $ragOpenMeans.cite_f1
            retrieval_hit_rate = $ragOpenMeans.retrieval_hit_rate
            tokens_per_q = $ragOpenRuntime.tokens_per_q
            wall_s_per_q = $ragOpenRuntime.wall_s_per_q
            source_pdf = (Split-Path -Leaf $resolvedPdfPath)
        }
} else {
    $reason = if ($SkipOpenBook) { "Skipped by flag." } else { $openBookSkipReason }
    Add-Step -Name "rag_open_book" -Status "SKIP" -RunDir $ragOpenDir -Required $false -Details @{ reason = $reason }
}

# Regression case (internal tooling)
if ($runRegressionCase) {
    $regDir = Join-Path $OutRoot "regression_case"
    Write-Host "Step 3/4: Regression case (internal tooling)"
    $regArgs = @{
        Adapter = $Adapter
        OutRoot = $regDir
        GenerateReports = $true
        ComparePassFail = $true
    }
    if ($resolvedModelPath) {
        $regArgs.ModelPath = $resolvedModelPath
    }
    .\scripts\run_regression_case.ps1 @regArgs | Out-Host
    $regCode = $LASTEXITCODE
    Add-Step -Name "regression_case" -Status ($(if ($regCode -eq 0) { "PASS" } else { "FAIL" })) `
        -RunDir $regDir -Required $true -Details @{
            pass_gate = "pass\\drift_holdout_gate.json"
            fail_gate = "fail\\drift_holdout_gate.json"
        }
} else {
    Add-Step -Name "regression_case" -Status "SKIP" -RunDir "" -Required $false
}

# Bad actor demo (compliance/safety)
if ($runBadActor) {
    $badDir = Join-Path $OutRoot "bad_actor"
    Write-Host "Step 4/4: Bad actor demo (compliance/safety)"
    $badArgs = @{
        Adapter = $Adapter
        OutRoot = $badDir
        GenerateReports = $true
        AllowWallFail = $true
    }
    if ($resolvedModelPath) {
        $badArgs.ModelPath = $resolvedModelPath
    }
    .\scripts\run_bad_actor_demo.ps1 @badArgs | Out-Host
    $badCode = $LASTEXITCODE
    $badExpectedFail = $true
    $badGateStatus = $null
    $badGatePath = Join-Path $badDir "holdout\\drift_holdout_gate.json"
    if (Test-Path $badGatePath) {
        try {
            $badGate = Get-Content -Raw -Path $badGatePath | ConvertFrom-Json
            $badGateStatus = $badGate.status
        } catch {
            $badGateStatus = $null
        }
    }
    $badObservedFail = if ($badGateStatus) { $badGateStatus -ne "PASS" } else { $badCode -ne 0 }
    $wallRate = $null
    $wallSummaryPath = "runs\\drift_wall_latest\\summary.json"
    if (Test-Path $wallSummaryPath) {
        try {
            $wallData = Get-Content -Raw -Path $wallSummaryPath | ConvertFrom-Json
            if ($wallData.drift -and $null -ne $wallData.drift.step_rate) {
                $wallRate = [double]$wallData.drift.step_rate
            }
        } catch {
            $wallRate = $null
        }
    }
    Add-Step -Name "bad_actor_demo" -Status ($(if ($badObservedFail) { "PASS" } else { "FAIL" })) `
        -RunDir $badDir -Required $true -Details @{
            holdout_gate = "holdout\\drift_holdout_gate.json"
            wall_summary = "runs\drift_wall_latest\summary.json"
            wall_rate = $wallRate
            expected_fail = $badExpectedFail
            expected_fail_observed = $badObservedFail
            gate_status = $badGateStatus
        }
} else {
    Add-Step -Name "bad_actor_demo" -Status "SKIP" -RunDir "" -Required $false
}

$summaryPath = Join-Path $OutRoot "case_pack_summary.json"
$summary | ConvertTo-Json -Depth 6 | Set-Content -Path $summaryPath

$latestFile = "runs\\case_pack_latest.txt"
$prevOut = ""
if (Test-Path $latestFile) {
    $prevOut = (Get-Content -Path $latestFile -Raw).Trim()
}
Set-Content -Path $latestFile -Value $OutRoot

$deltaPath = Join-Path $OutRoot "case_pack_delta_report.md"
if ($prevOut -and (Test-Path $prevOut)) {
    python .\scripts\compare_runs.py --base $prevOut --other $OutRoot --out $deltaPath | Out-Host
}

python .\scripts\generate_case_pack_onepager.py --run-dir $OutRoot | Out-Host

$reportPath = Join-Path $OutRoot "case_pack_report.md"
$lines = @(
    "# Case Pack Report",
    "",
    "Out root: $OutRoot",
    "Status: $($summary.status)",
    "",
    "## RAG: closed-book vs open-book",
    "- Closed-book strict run: $ragClosedDir",
    "- Open-book run: $ragOpenDir",
    ""
)

$closedMetrics = $summary.steps | Where-Object { $_.name -eq "rag_closed_book_strict" } | Select-Object -First 1
$openMetrics = $summary.steps | Where-Object { $_.name -eq "rag_open_book" } | Select-Object -First 1
if ($closedMetrics) {
    $lines += "Closed-book strict (expected FAIL):"
    $lines += "- status: $($closedMetrics.status)"
    $lines += "- value_acc: $(Format-Num $closedMetrics.details.value_acc)"
    $lines += "- cite_f1: $(Format-Num $closedMetrics.details.cite_f1)"
    $lines += "- retrieval_hit_rate: $(Format-Num $closedMetrics.details.retrieval_hit_rate)"
    $lines += ""
}
if ($openMetrics) {
    $lines += "Open-book demo:"
    $lines += "- status: $($openMetrics.status)"
    $lines += "- value_acc: $(Format-Num $openMetrics.details.value_acc)"
    $lines += "- cite_f1: $(Format-Num $openMetrics.details.cite_f1)"
    $lines += "- retrieval_hit_rate: $(Format-Num $openMetrics.details.retrieval_hit_rate)"
    $lines += "- tokens_per_q: $(Format-Num $openMetrics.details.tokens_per_q 1)"
    $lines += "- wall_s_per_q: $(Format-Num $openMetrics.details.wall_s_per_q 2)"
    if ($openMetrics.details.source_pdf) {
        $lines += "- source_pdf: $($openMetrics.details.source_pdf)"
    }
    $lines += ""
}

$regMetrics = $summary.steps | Where-Object { $_.name -eq "regression_case" } | Select-Object -First 1
if ($regMetrics) {
    $lines += "## Internal tooling: regression case"
    $lines += "- status: $($regMetrics.status)"
    if ($regMetrics.status -eq "SKIP") {
        $lines += "- artifacts: skipped (adapter does not expose retrieval drift diagnostics or step disabled)"
    } else {
        $lines += "- pass gate: $(Join-OptionalPath -BasePath $regMetrics.run_dir -RelativePath $regMetrics.details.pass_gate)"
        $lines += "- fail gate: $(Join-OptionalPath -BasePath $regMetrics.run_dir -RelativePath $regMetrics.details.fail_gate)"
    }
    $lines += ""
}

$badMetrics = $summary.steps | Where-Object { $_.name -eq "bad_actor_demo" } | Select-Object -First 1
if ($badMetrics) {
    $lines += "## Compliance/safety: bad actor demo"
    $badStatus = $badMetrics.status
    if ($badMetrics.details.expected_fail) {
        if ($badMetrics.details.expected_fail_observed) {
            $badStatus = "PASS (expected holdout FAIL)"
        } else {
            $badStatus = "FAIL (expected holdout FAIL)"
        }
    }
    $lines += "- status: $badStatus"
    if ($badMetrics.status -eq "SKIP") {
        $lines += "- holdout gate: skipped (adapter does not expose retrieval drift diagnostics or step disabled)"
    } else {
        $lines += "- holdout gate: $(Join-OptionalPath -BasePath $badMetrics.run_dir -RelativePath $badMetrics.details.holdout_gate)"
    }
    $lines += "- wall summary: $($badMetrics.details.wall_summary)"
    $lines += ""
}

$lines += "## Notes"
$lines += "- Closed-book strict is expected to fail until open-book retrieval is used."
$lines += "- A PASS in this pack means the demos behaved as expected; investigate FAILs in the referenced artifacts."
$lines | Set-Content -Path $reportPath

Write-Host "Case pack summary: $summaryPath"
Write-Host "Case pack report: $reportPath"
if ($summary.status -ne "PASS") {
    exit 1
}
