param(
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL,
    [string]$Adapter = "goldevidencebench.adapters.retrieval_llama_cpp_adapter:create_adapter",
    [string]$HoldoutListPath = "configs\\bad_actor_holdout_list.json",
    [string]$HoldoutId = "",
    [string]$FixturePath = "",
    [string]$RunsDir = "",
    [string]$LatestDir = "runs\\bad_actor_holdout_latest",
    [ValidateSet("none", "latest_step", "prefer_set_latest", "prefer_update_latest")]
    [string]$Rerank = "prefer_update_latest",
    [bool]$AuthorityFilter = $true,
    [int]$MaxBookTokens = 400
)

if (-not $ModelPath) {
    Write-Error "Set -ModelPath or GOLDEVIDENCEBENCH_MODEL before running."
    exit 1
}

function Resolve-HoldoutFixture {
    param(
        [string]$ListPath,
        [string]$RequestedId,
        [string]$OverrideFixture
    )
    if ($OverrideFixture) {
        return $OverrideFixture
    }
    if (-not (Test-Path $ListPath)) {
        throw "Holdout list not found: $ListPath"
    }
    $config = Get-Content -Raw -Path $ListPath | ConvertFrom-Json
    if (-not $config -or -not $config.holdouts) {
        throw "Holdout list missing 'holdouts' in $ListPath"
    }
    $selected = $null
    foreach ($item in $config.holdouts) {
        if ($item -is [string]) {
            if (-not $RequestedId) {
                $selected = [pscustomobject]@{ id = ""; fixture = $item }
                break
            }
            continue
        }
        if ($RequestedId -and $item.id -eq $RequestedId) {
            $selected = $item
            break
        }
        if (-not $RequestedId -and -not $selected) {
            $selected = $item
        }
    }
    if (-not $selected) {
        throw "Holdout id '$RequestedId' not found in $ListPath"
    }
    if (-not $selected.fixture) {
        throw "Holdout entry missing fixture path in $ListPath"
    }
    return $selected.fixture
}

$fixture = $null
try {
    $fixture = Resolve-HoldoutFixture -ListPath $HoldoutListPath -RequestedId $HoldoutId -OverrideFixture $FixturePath
} catch {
    Write-Error $_
    exit 1
}
if (-not (Test-Path $fixture)) {
    Write-Error "Fixture not found: $fixture"
    exit 1
}

$finalRunsDir = $RunsDir
if (-not $finalRunsDir) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $finalRunsDir = "runs\\bad_actor_holdout_$stamp"
}
New-Item -ItemType Directory -Path $finalRunsDir -Force | Out-Null

$env:GOLDEVIDENCEBENCH_MODEL = $ModelPath
$env:GOLDEVIDENCEBENCH_RETRIEVAL_RERANK = $Rerank
$env:GOLDEVIDENCEBENCH_RETRIEVAL_WRONG_TYPE = "same_key"
$env:GOLDEVIDENCEBENCH_RETRIEVAL_ORDER = "shuffle"
$env:GOLDEVIDENCEBENCH_RETRIEVAL_ORDER_SEED = "0"
$env:GOLDEVIDENCEBENCH_RETRIEVAL_AUTHORITY_FILTER = if ($AuthorityFilter) { "1" } else { "0" }

Write-Host "Bad actor holdout gate"
Write-Host "RunsDir: $finalRunsDir"
Write-Host "Fixture: $fixture"
Write-Host "Rerank: $Rerank Adapter: $Adapter"
Write-Host ("Authority filter: {0}" -f $AuthorityFilter)

$dataPath = Join-Path $finalRunsDir "data.jsonl"
Copy-Item -Path $fixture -Destination $dataPath -Force

$combinedPath = Join-Path $finalRunsDir "combined.json"
$predsPath = Join-Path $finalRunsDir "preds.jsonl"
goldevidencebench model --data $dataPath --adapter $Adapter --protocol closed_book --max-book-tokens $MaxBookTokens --out $predsPath --results-json $combinedPath
if ($LASTEXITCODE -ne 0) {
    Write-Error "bad_actor holdout model run failed."
    exit 1
}

# summarize_results.py expects an array of run objects; normalize model output to a JSON array.
$rawCombined = Get-Content -Raw -Path $combinedPath
if ($rawCombined -and -not $rawCombined.TrimStart().StartsWith("[")) {
    $wrapped = "[`n" + $rawCombined.Trim() + "`n]"
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($combinedPath, $wrapped, $utf8NoBom)
}

$summaryPath = Join-Path $finalRunsDir "summary.json"
python .\scripts\summarize_results.py --in $combinedPath --out-json $summaryPath
if ($LASTEXITCODE -ne 0) {
    Write-Error "bad_actor holdout summary failed."
    exit 1
}

New-Item -ItemType Directory -Path $LatestDir -Force | Out-Null
if (Test-Path $summaryPath) {
    Copy-Item $summaryPath -Destination (Join-Path $LatestDir "summary.json") -Force
}
$compactJsonPath = Join-Path $finalRunsDir "summary_compact.json"
$compactCsvPath = Join-Path $finalRunsDir "summary_compact.csv"
if (Test-Path $compactJsonPath) {
    Copy-Item $compactJsonPath -Destination (Join-Path $LatestDir "summary_compact.json") -Force
}
if (Test-Path $compactCsvPath) {
    Copy-Item $compactCsvPath -Destination (Join-Path $LatestDir "summary_compact.csv") -Force
}
$diagnosisPath = Join-Path $finalRunsDir "diagnosis.json"
if (Test-Path $diagnosisPath) {
    Copy-Item $diagnosisPath -Destination (Join-Path $LatestDir "diagnosis.json") -Force
}

Write-Host "Latest bad actor holdout snapshot: $LatestDir"
