param(
    [ValidateSet("lenient", "strict")][string]$Preset = "lenient",
    [string]$ConfigPath = "",
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL,
    [string]$OutRoot = "",
    [double]$MinValueAcc = [double]::NaN,
    [double]$MinCiteF1 = [double]::NaN
)

if (-not $ModelPath) {
    Write-Error "Set -ModelPath or GOLDEVIDENCEBENCH_MODEL before running the retriever delta."
    exit 1
}

if (-not $OutRoot) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutRoot = "runs\\rag_retriever_delta_$stamp"
}

New-Item -ItemType Directory -Path $OutRoot -Force | Out-Null

$bm25Out = Join-Path $OutRoot "bm25"
$denseOut = Join-Path $OutRoot "dense"

$oldRetriever = $env:RETRIEVAL_RETRIEVER

Write-Host "RAG retriever delta"
Write-Host "RunsDir: $OutRoot"
Write-Host "Preset: $Preset"

$bm25Params = @{
    Preset = $Preset
    ModelPath = $ModelPath
    OutRoot = $bm25Out
}
if ($ConfigPath) { $bm25Params.ConfigPath = $ConfigPath }
if (-not [double]::IsNaN($MinValueAcc)) { $bm25Params.MinValueAcc = $MinValueAcc }
if (-not [double]::IsNaN($MinCiteF1)) { $bm25Params.MinCiteF1 = $MinCiteF1 }

$denseParams = @{
    Preset = $Preset
    ModelPath = $ModelPath
    OutRoot = $denseOut
}
if ($ConfigPath) { $denseParams.ConfigPath = $ConfigPath }
if (-not [double]::IsNaN($MinValueAcc)) { $denseParams.MinValueAcc = $MinValueAcc }
if (-not [double]::IsNaN($MinCiteF1)) { $denseParams.MinCiteF1 = $MinCiteF1 }

$env:RETRIEVAL_RETRIEVER = "bm25"
.\scripts\run_rag_benchmark.ps1 @bm25Params | Out-Host
$bm25Code = $LASTEXITCODE

$env:RETRIEVAL_RETRIEVER = "dense"
.\scripts\run_rag_benchmark.ps1 @denseParams | Out-Host
$denseCode = $LASTEXITCODE

if ($oldRetriever -ne $null) {
    $env:RETRIEVAL_RETRIEVER = $oldRetriever
} else {
    Remove-Item Env:RETRIEVAL_RETRIEVER -ErrorAction SilentlyContinue
}

$deltaPath = Join-Path $OutRoot "retriever_delta_report.md"
python .\scripts\compare_runs.py --base $bm25Out --other $denseOut --out $deltaPath --print | Out-Host

Write-Host "Retriever delta report: $deltaPath"
if ($bm25Code -ne 0 -or $denseCode -ne 0) {
    exit 1
}
