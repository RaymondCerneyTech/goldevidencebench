[CmdletBinding()]
param(
    [ValidateSet("explore", "enforce")][string]$Mode = "explore",
    [ValidateSet("lenient", "strict")][string]$Preset = "strict",
    [string]$ConfigPath = "",
    [string]$OutRoot = "",
    [string]$RunDir = "",
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL,
    [string]$Adapter = "goldevidencebench.adapters.llama_server_adapter:create_adapter",
    [string]$Protocol = "closed_book",
    [string]$DatasetId = "",
    [ValidateSet("reason", "key", "both")][string]$CoverBy = "both",
    [int]$MaxRows = 0,
    [int]$MaxAnchors = 8,
    [string]$AnchorsOut = "",
    [string]$Family = "",
    [switch]$NoEntailmentCheck,
    [switch]$Append
)

function Resolve-RagConfigPath {
    param(
        [string]$Preset,
        [string]$ConfigPath
    )
    if ($ConfigPath) {
        return $ConfigPath
    }
    if ($Preset -eq "strict") {
        return "configs\rag_benchmark_strict.json"
    }
    return "configs\rag_benchmark_lenient.json"
}

function Resolve-LatestRunDir {
    param([string]$Preset)
    $pointer = if ($Preset -eq "strict") { "runs\latest_rag_strict" } else { "runs\latest_rag_lenient" }
    if (-not (Test-Path $pointer)) {
        throw "Latest pointer not found: $pointer"
    }
    $target = (Get-Content -Raw $pointer).Trim()
    if (-not $target) {
        throw "Latest pointer is empty: $pointer"
    }
    return $target
}

function Get-DatasetDataPath {
    param(
        [string]$ConfigPath,
        [string]$DatasetId
    )
    if (-not (Test-Path $ConfigPath)) {
        throw "Config not found: $ConfigPath"
    }
    $config = Get-Content -Raw -Path $ConfigPath | ConvertFrom-Json
    foreach ($entry in $config.datasets) {
        if ($entry.id -eq $DatasetId) {
            return [string]$entry.data
        }
    }
    throw "Dataset id '$DatasetId' not found in $ConfigPath"
}

$resolvedConfig = Resolve-RagConfigPath -Preset $Preset -ConfigPath $ConfigPath

if ($Mode -eq "explore") {
    $benchArgs = @{
        Preset = $Preset
        Adapter = $Adapter
        Protocol = $Protocol
    }
    if ($resolvedConfig) {
        $benchArgs["ConfigPath"] = $resolvedConfig
    }
    if ($OutRoot) {
        $benchArgs["OutRoot"] = $OutRoot
    }
    if ($ModelPath) {
        $benchArgs["ModelPath"] = $ModelPath
    }
    if ($MaxRows -gt 0) {
        $benchArgs["MaxRows"] = $MaxRows
    }
    if ($NoEntailmentCheck) {
        $benchArgs["NoEntailmentCheck"] = $true
    }
    .\scripts\run_rag_benchmark.ps1 @benchArgs
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }

    $resolvedRunDir = if ($OutRoot) { $OutRoot } else { Resolve-LatestRunDir -Preset $Preset }
    Write-Host "Explore run dir: $resolvedRunDir"

    if ($DatasetId) {
        $dataPath = Get-DatasetDataPath -ConfigPath $resolvedConfig -DatasetId $DatasetId
        $predsPath = Join-Path $resolvedRunDir ("preds_{0}.jsonl" -f $DatasetId)
        $drilldownPath = Join-Path $resolvedRunDir ("drilldown_{0}.jsonl" -f $DatasetId)
        $minPath = Join-Path $resolvedRunDir ("minimized_{0}.jsonl" -f $DatasetId)
        if (-not (Test-Path $predsPath)) {
            throw "Missing predictions for dataset '$DatasetId': $predsPath"
        }
        $drillArgs = @(
            ".\scripts\rag_failure_drilldown.py",
            "--data", $dataPath,
            "--preds", $predsPath,
            "--out", $drilldownPath
        )
        if ($NoEntailmentCheck) {
            $drillArgs += "--no-entailment-check"
        }
        python @drillArgs
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
        python .\scripts\minimize_counterexample.py --drilldown $drilldownPath --out $minPath --max-rows $MaxAnchors --cover-by $CoverBy
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
        Write-Host "Explore artifacts:"
        Write-Host "- $drilldownPath"
        Write-Host "- $minPath"
    }
    exit 0
}

# enforce mode
if (-not $DatasetId) {
    throw "Set -DatasetId in enforce mode."
}
$resolvedRunDir = if ($RunDir) { $RunDir } else { Resolve-LatestRunDir -Preset $Preset }
$dataPath = Get-DatasetDataPath -ConfigPath $resolvedConfig -DatasetId $DatasetId
$predsPath = Join-Path $resolvedRunDir ("preds_{0}.jsonl" -f $DatasetId)
$drilldownPath = Join-Path $resolvedRunDir ("drilldown_{0}.jsonl" -f $DatasetId)
$minPath = Join-Path $resolvedRunDir ("minimized_{0}.jsonl" -f $DatasetId)
if (-not $AnchorsOut) {
    $AnchorsOut = Join-Path "data\trap_anchors" ("{0}_anchors.jsonl" -f $DatasetId)
}

if (-not (Test-Path $predsPath)) {
    throw "Missing predictions for dataset '$DatasetId': $predsPath"
}

$drillArgs = @(
    ".\scripts\rag_failure_drilldown.py",
    "--data", $dataPath,
    "--preds", $predsPath,
    "--out", $drilldownPath
)
if ($NoEntailmentCheck) {
    $drillArgs += "--no-entailment-check"
}
python @drillArgs
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

python .\scripts\minimize_counterexample.py --drilldown $drilldownPath --out $minPath --max-rows $MaxAnchors --cover-by $CoverBy
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$promoteArgs = @(
    ".\scripts\promote_failures_to_anchors.py",
    "--data", $dataPath,
    "--drilldown", $drilldownPath,
    "--out", $AnchorsOut,
    "--max-anchors", "$MaxAnchors",
    "--cover-by", $CoverBy
)
if ($Family) {
    $promoteArgs += @("--family", $Family)
}
if ($Append) {
    $promoteArgs += "--append"
}
python @promoteArgs
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Enforce artifacts:"
Write-Host "- $drilldownPath"
Write-Host "- $minPath"
Write-Host "- $AnchorsOut"
