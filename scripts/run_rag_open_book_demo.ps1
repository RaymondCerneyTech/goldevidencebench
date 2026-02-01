param(
    [string]$PdfPath = "",
    [ValidateSet("bm25", "dense")][string]$RetrieverMode = "bm25",
    [int]$TopK = 3,
    [int]$MaxDocs = 24,
    [int]$MinLineLen = 30,
    [int]$MaxLineLen = 160,
    [int]$MaxRows = 0,
    [string]$OutRoot = "",
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL
)

if (-not $PdfPath) {
    $pdfs = Get-ChildItem -Path . -Filter *.pdf -File
    if ($pdfs.Count -eq 1) {
        $PdfPath = $pdfs[0].FullName
    } elseif ($pdfs.Count -eq 0) {
        Write-Error "No PDF found in repo root. Pass -PdfPath."
        exit 1
    } else {
        Write-Error "Multiple PDFs found. Pass -PdfPath to select one."
        exit 1
    }
}

if (-not (Test-Path $PdfPath)) {
    Write-Error "PDF not found: $PdfPath"
    exit 1
}

if (-not $OutRoot) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutRoot = "runs\\rag_open_book_demo_$stamp"
}

$python = "python"
if ($env:VIRTUAL_ENV) {
    $venvPython = Join-Path $env:VIRTUAL_ENV "Scripts\\python.exe"
    if (Test-Path -LiteralPath $venvPython) {
        $python = $venvPython
    }
}
if ($python -eq "python") {
    $localVenv = Join-Path $PSScriptRoot "..\\.venv\\Scripts\\python.exe"
    if (Test-Path -LiteralPath $localVenv) {
        $python = $localVenv
    }
}
if ($python -ne "python") {
    $pythonDir = Split-Path -Parent $python
    if ($pythonDir -and ($env:PATH -notlike "$pythonDir*")) {
        $env:PATH = "$pythonDir;$env:PATH"
    }
}

$placeholderPattern = "<"
if ($ModelPath -and $ModelPath.Contains($placeholderPattern)) {
    $ModelPath = $env:GOLDEVIDENCEBENCH_MODEL
}
if ($ModelPath -and $ModelPath.Contains($placeholderPattern)) {
    $ModelPath = ""
}
if (-not $ModelPath) {
    Write-Error "Set -ModelPath or GOLDEVIDENCEBENCH_MODEL before running."
    exit 1
}
if ($ModelPath -and -not (Test-Path -LiteralPath $ModelPath)) {
    Write-Error "Model path not found: $ModelPath"
    exit 1
}

$indexPath = Join-Path $OutRoot "doc_index.jsonl"
$datasetPath = Join-Path $OutRoot "open_book_dataset.jsonl"
$configPath = Join-Path $OutRoot "rag_open_book_config.json"

New-Item -ItemType Directory -Path $OutRoot -Force | Out-Null

Write-Host "RAG open-book demo"
Write-Host "PDF: $PdfPath"
Write-Host "OutRoot: $OutRoot"

& $python .\scripts\build_rag_doc_index_from_pdf.py --pdf-path $PdfPath --out $indexPath --max-docs $MaxDocs --min-line-len $MinLineLen --max-line-len $MaxLineLen | Out-Host
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to build doc index from PDF."
    exit 1
}

& $python .\scripts\build_rag_open_book_dataset.py --index $indexPath --out $datasetPath | Out-Host
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to build open-book dataset."
    exit 1
}

$config = @{
    datasets = @(
        @{ id = "open_book_fact"; data = $datasetPath }
    )
}
$configJson = $config | ConvertTo-Json -Depth 4
[System.IO.File]::WriteAllText(
    $configPath,
    $configJson,
    (New-Object System.Text.UTF8Encoding $false)
)

$env:GOLDEVIDENCEBENCH_RAG_DOC_INDEX = $indexPath
$env:GOLDEVIDENCEBENCH_RAG_RETRIEVER_MODE = $RetrieverMode
$env:GOLDEVIDENCEBENCH_RAG_TOP_K = "$TopK"

$benchArgs = @{
    ConfigPath = $configPath
    OutRoot    = (Join-Path $OutRoot "rag_open_book_run")
    Adapter    = "goldevidencebench.adapters.open_book_retrieval_adapter:create_adapter"
    Protocol   = "open_book"
    NoEntailmentCheck = $true
}
if ($ModelPath) {
    $benchArgs.ModelPath = $ModelPath
}
if ($MaxRows -gt 0) {
    $benchArgs.MaxRows = $MaxRows
}

.\scripts\run_rag_benchmark.ps1 @benchArgs
