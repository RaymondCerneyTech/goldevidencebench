param(
    [string]$ConfigPath = "configs\\core_benchmark.json",
    [string]$ThresholdsPath = "configs\\core_thresholds.json",
    [string]$OutRoot = "",
    [int]$Seeds = 1,
    [int]$FuzzVariants = 0,
    [int]$FuzzSeed = 0,
    [double]$MinPolicyPass = [double]::NaN,
    [double]$MinGreedyPass = [double]::NaN,
    [double]$MinSaPass = [double]::NaN
)

if (-not (Test-Path $ConfigPath)) {
    Write-Error "Config not found: $ConfigPath"
    exit 1
}

if (-not $OutRoot) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutRoot = "runs\\core_benchmark_$stamp"
}

New-Item -ItemType Directory -Path $OutRoot -Force | Out-Null

$config = Get-Content -Raw -Path $ConfigPath | ConvertFrom-Json
if (-not $config.fixtures) {
    Write-Error "Config has no fixtures: $ConfigPath"
    exit 1
}

if ([double]::IsNaN($MinPolicyPass) -and (Test-Path $ThresholdsPath)) {
    try {
        $thresholds = Get-Content -Raw -Path $ThresholdsPath | ConvertFrom-Json
        $configName = if ($config.name) { $config.name } else { [System.IO.Path]::GetFileNameWithoutExtension($ConfigPath) }
        $configThresholds = $thresholds.$configName
        if ($configThresholds -and $configThresholds.min_policy_pass -ne $null) {
            $MinPolicyPass = [double]$configThresholds.min_policy_pass
        }
    } catch {
        Write-Host "Failed to parse thresholds file: $ThresholdsPath"
    }
}

Write-Host "Core benchmark"
Write-Host "Config: $ConfigPath"
Write-Host "RunsDir: $OutRoot"
Write-Host "Seeds: $Seeds"

foreach ($entry in $config.fixtures) {
    $id = $entry.id
    $fixture = $entry.fixture
    $observed = $entry.observed
    if (-not $id -or -not $fixture) {
        Write-Host "Skipping invalid fixture entry."
        continue
    }
    $outJson = Join-Path $OutRoot ("bench_{0}.json" -f $id)
    $outCsv = Join-Path $OutRoot ("bench_{0}_summary.csv" -f $id)
    $args = @(
        "--fixture", $fixture,
        "--out", $outJson,
        "--out-csv", $outCsv,
        "--seeds", "$Seeds"
    )
    if ($observed) {
        $args += @("--observed", $observed)
    }
    if ($FuzzVariants -gt 0) {
        $args += @("--fuzz-variants", "$FuzzVariants", "--fuzz-seed", "$FuzzSeed")
    }
    Write-Host ("Running {0}..." -f $id)
    python .\scripts\run_ui_search_baseline.py @args | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Baseline run failed for $id"
        exit 1
    }
}

$summaryPath = Join-Path $OutRoot "summary.json"
$reportPath = Join-Path $OutRoot "report.md"
$summaryArgs = @("--config", $ConfigPath, "--runs-dir", $OutRoot, "--out", $summaryPath, "--report", $reportPath)
if (-not [double]::IsNaN($MinPolicyPass)) {
    $summaryArgs += @("--min-policy-pass", "$MinPolicyPass")
}
if (-not [double]::IsNaN($MinGreedyPass)) {
    $summaryArgs += @("--min-greedy-pass", "$MinGreedyPass")
}
if (-not [double]::IsNaN($MinSaPass)) {
    $summaryArgs += @("--min-sa-pass", "$MinSaPass")
}
python .\scripts\summarize_core_benchmark.py @summaryArgs | Out-Host

Write-Host "Core benchmark summary: $summaryPath"
