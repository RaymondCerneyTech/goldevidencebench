<#
.SYNOPSIS
Runs the case pack and prints the latest onepager path.

.DESCRIPTION
Convenience wrapper for run_case_pack.ps1 that resolves the latest
case pack run and optionally opens the onepager report.

.PARAMETER ModelPath
Path to GGUF model for LLM-dependent checks (or set GOLDEVIDENCEBENCH_MODEL).

.PARAMETER Adapter
Adapter factory path used by case-pack sub-runs.

.PARAMETER PdfPath
Path to a PDF used for the open-book demo (optional).

.PARAMETER OutRoot
Override the output root directory (default: runs\case_pack_<timestamp>).

.PARAMETER MaxRows
Max rows for RAG datasets (default: 24).

.PARAMETER RetrieverMode
Retriever mode for open-book demo (bm25 or dense).

.PARAMETER TopK
Top-k retrieval size for open-book demo.

.PARAMETER SkipOpenBook
Skip the open-book demo step.

.PARAMETER SkipRegressionCase
Skip the regression case step.

.PARAMETER SkipBadActor
Skip the bad-actor demo step.

.PARAMETER OpenOnepager
Open the generated case_pack_onepager.md in Notepad.
#>
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
    [switch]$SkipBadActor,
    [switch]$OpenOnepager,
    [switch]$SkipRunLog
)

$caseArgs = @{
    ModelPath = $ModelPath
    Adapter = $Adapter
    PdfPath = $PdfPath
    OutRoot = $OutRoot
    MaxRows = $MaxRows
    RetrieverMode = $RetrieverMode
    TopK = $TopK
    SkipOpenBook = $SkipOpenBook
    SkipRegressionCase = $SkipRegressionCase
    SkipBadActor = $SkipBadActor
}

.\scripts\run_case_pack.ps1 @caseArgs | Out-Host
$exitCode = $LASTEXITCODE

$latestFile = "runs\\case_pack_latest.txt"
if (Test-Path $latestFile) {
    $latest = (Get-Content -Path $latestFile -Raw).Trim()
    if ($latest) {
        $onepager = Join-Path $latest "case_pack_onepager.md"
        if (Test-Path $onepager) {
            Write-Host "Onepager: $onepager"
            if ($OpenOnepager) {
                notepad $onepager
            }
        } else {
            Write-Host "Onepager not found: $onepager"
        }
        if (-not $SkipRunLog) {
            $modelId = ""
            if ($ModelPath -and -not ($ModelPath.Contains("<"))) {
                $modelId = Split-Path -Leaf $ModelPath
            }
            if (-not $modelId) {
                $modelId = $Adapter
            }
            try {
                .\scripts\append_run_log.ps1 -RunDir $latest -ModelId $modelId | Out-Host
            } catch {
                Write-Host "Warning: run log append failed: $($_.Exception.Message)"
            }
        }
    }
} else {
    Write-Host "Latest file not found: $latestFile"
}

exit $exitCode
