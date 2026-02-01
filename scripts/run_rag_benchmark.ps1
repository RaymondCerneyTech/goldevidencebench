param(
    [ValidateSet("lenient", "strict")][string]$Preset = "lenient",
    [string]$ConfigPath = "",
    [string]$ThresholdsPath = "configs\\rag_thresholds.json",
    [string]$OutRoot = "",
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL,
    [string]$Adapter = "goldevidencebench.adapters.retrieval_llama_cpp_adapter:create_adapter",
    [string]$Protocol = "closed_book",
    [string]$Citations = "auto",
    [int]$MaxSupportK = 3,
    [string]$SupportMetric = "f1",
    [switch]$NoEntailmentCheck,
    [int]$MaxBookTokens = 0,
    [int]$MaxRows = 0,
    [double]$MinValueAcc = [double]::NaN,
    [double]$MinCiteF1 = [double]::NaN,
    [double]$MinInstructionAcc = [double]::NaN,
    [double]$MinStateIntegrity = [double]::NaN
)

$resolvedConfig = $ConfigPath
if (-not $PSBoundParameters.ContainsKey("ConfigPath") -or -not $ConfigPath) {
    if ($Preset -eq "strict") {
        $resolvedConfig = "configs\\rag_benchmark_strict.json"
    } else {
        $resolvedConfig = "configs\\rag_benchmark_lenient.json"
    }
}

if (-not (Test-Path $resolvedConfig)) {
    Write-Error "Config not found: $resolvedConfig"
    exit 1
}

if (-not $OutRoot) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutRoot = "runs\\rag_benchmark_$stamp"
}

New-Item -ItemType Directory -Path $OutRoot -Force | Out-Null

$config = Get-Content -Raw -Path $resolvedConfig | ConvertFrom-Json
if (-not $config.datasets) {
    Write-Error "Config has no datasets: $resolvedConfig"
    exit 1
}

if (-not $ModelPath -and $Adapter -like "*llama_cpp*") {
    Write-Error "Set -ModelPath or GOLDEVIDENCEBENCH_MODEL before running the rag benchmark."
    exit 1
}

if ($ModelPath) {
    $env:GOLDEVIDENCEBENCH_MODEL = $ModelPath
}

Write-Host "RAG benchmark"
Write-Host "Config: $resolvedConfig"
Write-Host "RunsDir: $OutRoot"
Write-Host "Adapter: $Adapter"
Write-Host "Protocol: $Protocol"

if ([double]::IsNaN($MinValueAcc) -or [double]::IsNaN($MinCiteF1)) {
    if (Test-Path $ThresholdsPath) {
        try {
            $thresholds = Get-Content -Raw -Path $ThresholdsPath | ConvertFrom-Json
            $presetThresholds = $thresholds.$Preset
            if ($presetThresholds) {
                if ([double]::IsNaN($MinValueAcc) -and $presetThresholds.min_value_acc -ne $null) {
                    $MinValueAcc = [double]$presetThresholds.min_value_acc
                }
                if ([double]::IsNaN($MinCiteF1) -and $presetThresholds.min_cite_f1 -ne $null) {
                    $MinCiteF1 = [double]$presetThresholds.min_cite_f1
                }
            }
        } catch {
            Write-Host "Failed to parse thresholds file: $ThresholdsPath"
        }
    }
}

foreach ($entry in $config.datasets) {
    $id = $entry.id
    $data = $entry.data
    if (-not $id -or -not $data) {
        Write-Host "Skipping invalid dataset entry."
        continue
    }
    if ($MaxRows -gt 0) {
        $limitedPath = Join-Path $OutRoot ("limit_{0}.jsonl" -f $id)
        python .\scripts\limit_jsonl.py --in $data --out $limitedPath --max-rows $MaxRows | Out-Host
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to limit dataset rows for $id"
            exit 1
        }
        $data = $limitedPath
    }
    $outJson = Join-Path $OutRoot ("rag_{0}.json" -f $id)
    $args = @(
        "-m", "goldevidencebench.cli", "model",
        "--data", $data,
        "--adapter", $Adapter,
        "--protocol", $Protocol,
        "--citations", $Citations,
        "--support-metric", $SupportMetric,
        "--max-support-k", "$MaxSupportK",
        "--results-json", $outJson
    )
    if ($NoEntailmentCheck) {
        $args += "--no-entailment-check"
    }
    if ($MaxBookTokens -gt 0) {
        $args += @("--max-book-tokens", "$MaxBookTokens")
    }
    Write-Host ("Running {0}..." -f $id)
    python @args | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Write-Error "RAG benchmark run failed for $id"
        exit 1
    }
}

$summaryPath = Join-Path $OutRoot "summary.json"
$reportPath = Join-Path $OutRoot "report.md"
$summaryArgs = @("--config", $resolvedConfig, "--runs-dir", $OutRoot, "--out", $summaryPath, "--report", $reportPath)
if (-not [double]::IsNaN($MinValueAcc)) {
    $summaryArgs += @("--min-value-acc", "$MinValueAcc")
}
if (-not [double]::IsNaN($MinCiteF1)) {
    $summaryArgs += @("--min-cite-f1", "$MinCiteF1")
}
if (-not [double]::IsNaN($MinInstructionAcc)) {
    $summaryArgs += @("--min-instruction-acc", "$MinInstructionAcc")
}
if (-not [double]::IsNaN($MinStateIntegrity)) {
    $summaryArgs += @("--min-state-integrity", "$MinStateIntegrity")
}
python .\scripts\summarize_rag_benchmark.py @summaryArgs | Out-Host

Write-Host "RAG benchmark summary: $summaryPath"
