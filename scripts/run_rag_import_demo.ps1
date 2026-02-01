param(
    [string]$PdfPath = "",
    [ValidateSet("lenient", "strict")][string]$Preset = "strict",
    [int]$MaxEntries = 16,
    [int]$MinLineLen = 30,
    [int]$MaxLineLen = 120,
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
    $OutRoot = "runs\\rag_import_demo_$stamp"
}

$packDir = Join-Path $OutRoot "domain_pack"
New-Item -ItemType Directory -Path $packDir -Force | Out-Null

Write-Host "RAG import demo"
Write-Host "PDF: $PdfPath"
Write-Host "Pack dir: $packDir"

$buildArgs = @(
    "--pdf-path", $PdfPath,
    "--out-dir", $packDir,
    "--max-entries", "$MaxEntries",
    "--min-line-len", "$MinLineLen",
    "--max-line-len", "$MaxLineLen"
)

python .\scripts\build_rag_domain_pack_from_pdf.py @buildArgs | Out-Host
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to build domain pack from PDF."
    exit 1
}

$configPath = Join-Path $OutRoot "rag_import_config.json"
$config = @{
    datasets = @(
        @{ id = "domain_stale"; data = (Join-Path $packDir "rag_domain_stale.jsonl") },
        @{ id = "domain_authority"; data = (Join-Path $packDir "rag_domain_authority.jsonl") }
    )
}
$configJson = $config | ConvertTo-Json -Depth 4
[System.IO.File]::WriteAllText(
    $configPath,
    $configJson,
    (New-Object System.Text.UTF8Encoding $false)
)

Write-Host "Config: $configPath"

$benchArgs = @{
    ConfigPath = $configPath
    OutRoot    = (Join-Path $OutRoot "rag_import_run")
    Preset     = $Preset
}
if ($ModelPath) {
    $benchArgs.ModelPath = $ModelPath
}

.\scripts\run_rag_benchmark.ps1 @benchArgs
