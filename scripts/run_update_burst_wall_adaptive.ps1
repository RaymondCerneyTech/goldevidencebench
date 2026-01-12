param(
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL,
    [string]$OutRoot = "",
    [float]$Threshold = 0.10,
    [ValidateSet("gte", "lte")]
    [string]$Direction = "gte",
    [string]$Adapter = "goldevidencebench.adapters.retrieval_llama_cpp_adapter:create_adapter",
    [string]$LinearModel = ".\\models\\linear_selector.json",
    [int]$K = 16,
    [int]$StepBucket = 10,
    [int]$Steps = 320,
    [int]$Queries = 16,
    [int]$MaxBookTokens = 400,
    [float[]]$CoarseRates = @(0.10, 0.20, 0.30, 0.40),
    [int]$CoarseSeeds = 1,
    [int]$ConfirmSeeds = 3,
    [int]$RefineCount = 4,
    [int]$RefineDecimals = 3
)

if (-not $ModelPath) {
    Write-Error "Set -ModelPath or GOLDEVIDENCEBENCH_MODEL before running."
    exit 1
}

if (-not (Test-Path $LinearModel)) {
    Write-Error "Linear model not found at $LinearModel"
    exit 1
}

if (-not $OutRoot) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutRoot = "runs\\wall_update_burst_full_linear_bucket${StepBucket}_adaptive_$stamp"
}
New-Item -ItemType Directory -Path $OutRoot -Force | Out-Null
Write-Host "RunsDir: $OutRoot"

$commonArgs = @(
    "--adapter", $Adapter,
    "--no-derived-queries",
    "--no-twins",
    "--require-citations",
    "--max-book-tokens", "$MaxBookTokens"
)

function Format-Rate {
    param([double]$Rate)
    return ("{0:0.###}" -f $Rate)
}

function Reset-GEBEnv {
    Remove-Item Env:\GOLDEVIDENCEBENCH_* -ErrorAction SilentlyContinue
    $env:GOLDEVIDENCEBENCH_MODEL = $ModelPath
    $env:GOLDEVIDENCEBENCH_RETRIEVAL_RERANK = "linear"
    $env:GOLDEVIDENCEBENCH_RETRIEVAL_LINEAR_MODEL = $LinearModel
    $env:GOLDEVIDENCEBENCH_RETRIEVAL_STEP_BUCKET = "$StepBucket"
    $env:GOLDEVIDENCEBENCH_RETRIEVAL_K = "$K"
}

function Invoke-RateSweep {
    param(
        [double]$Rate,
        [int]$Seeds,
        [string]$Tag
    )
    $rateTag = Format-Rate -Rate $Rate
    $outDir = Join-Path $OutRoot "wall_update_burst_full_linear_k${K}_bucket${StepBucket}_rate${rateTag}_s${Seeds}_$Tag"
    Write-Host ("Run: rate={0} seeds={1} tag={2}" -f $rateTag, $Seeds, $Tag)
    Reset-GEBEnv
    goldevidencebench sweep --out $outDir --seeds $Seeds --episodes 1 --steps $Steps --queries $Queries `
        --state-modes kv --distractor-profiles update_burst --update-burst-rate $rateTag `
        @commonArgs --results-json "$outDir\\combined.json"
    python .\scripts\summarize_results.py --in "$outDir\\combined.json" --out-json "$outDir\\summary.json"
}

function Get-WallResult {
    $output = python .\scripts\find_wall.py --runs-dir $OutRoot `
        --metric retrieval.wrong_update_rate --param update_burst_rate `
        --threshold $Threshold --direction $Direction --state-mode kv --profile update_burst
    $output | ForEach-Object { Write-Host $_ }
    $wallParam = $null
    $lastOkParam = $null
    foreach ($line in $output) {
        if ($line -match "^wall_param=([^ ]+)") {
            if ($matches[1] -ne "None") {
                $wallParam = [double]$matches[1]
            }
        }
        if ($line -match "^last_ok_param=([^ ]+)") {
            if ($matches[1] -ne "None") {
                $lastOkParam = [double]$matches[1]
            }
        }
    }
    return [PSCustomObject]@{
        WallParam = $wallParam
        LastOkParam = $lastOkParam
    }
}

function Get-RefineRates {
    param(
        [double]$Low,
        [double]$High,
        [int]$Count,
        [int]$Decimals
    )
    if ($High -le $Low -or $Count -le 0) {
        return @()
    }
    $rates = @()
    for ($i = 1; $i -le $Count; $i++) {
        $ratio = $i / ($Count + 1)
        $value = $Low + (($High - $Low) * $ratio)
        $rates += [Math]::Round($value, $Decimals)
    }
    return $rates | Sort-Object -Unique
}

foreach ($rate in $CoarseRates) {
    Invoke-RateSweep -Rate $rate -Seeds $CoarseSeeds -Tag "coarse"
}

$wallResult = Get-WallResult
if (-not $wallResult.WallParam -or -not $wallResult.LastOkParam) {
    Write-Host "No bracket found. Adjust CoarseRates or threshold."
    exit 0
}

$refineRates = Get-RefineRates -Low $wallResult.LastOkParam -High $wallResult.WallParam `
    -Count $RefineCount -Decimals $RefineDecimals
$refineRates = $refineRates | Where-Object { $CoarseRates -notcontains $_ }
foreach ($rate in $refineRates) {
    Invoke-RateSweep -Rate $rate -Seeds $CoarseSeeds -Tag "refine"
}

$wallResult = Get-WallResult
if ($ConfirmSeeds -gt $CoarseSeeds -and $wallResult.LastOkParam) {
    Invoke-RateSweep -Rate $wallResult.LastOkParam -Seeds $ConfirmSeeds -Tag "confirm"
    $wallResult = Get-WallResult
}

Write-Host "Adaptive wall search complete."
if ($wallResult.LastOkParam) {
    Write-Host ("Suggested pin (last_ok_param): {0}" -f $wallResult.LastOkParam)
} else {
    Write-Host "No last_ok_param found; consider expanding CoarseRates."
}
