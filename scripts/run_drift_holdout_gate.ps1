param(
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL,
    [int]$Steps = 120,
    [int]$Keys = 4,
    [int]$Queries = 120,
    [int]$Seeds = 1,
    [string]$Adapter = "goldevidencebench.adapters.retrieval_llama_cpp_adapter:create_adapter",
    [ValidateSet("stale_tab_state", "focus_drift")]
    [string]$HoldoutName = "stale_tab_state",
    [double]$CanaryMin = 0.5,
    [string]$RunsDir = "",
    [string]$GateArtifactPath = "",
    [string]$LatestDir = "",
    [bool]$FixAuthorityFilter = $true,
    [ValidateSet("latest_step", "prefer_set_latest")]
    [string]$FixPreferRerank = "prefer_set_latest",
    [double]$AuthoritySpoofRate = 0.0,
    [int]$AuthoritySpoofSeed = 0
)

if (-not $ModelPath) {
    Write-Error "Set -ModelPath or GOLDEVIDENCEBENCH_MODEL before running."
    exit 1
}

$finalRunsDir = $RunsDir
if (-not $finalRunsDir) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $finalRunsDir = "runs\\release_gates\\drift_holdout_gate_$stamp"
}
New-Item -ItemType Directory -Path $finalRunsDir -Force | Out-Null

function Get-DriftMax {
    param([string]$ConfigPath)
    $fallback = 0.25
    if (-not (Test-Path $ConfigPath)) {
        return $fallback
    }
    try {
        $config = Get-Content -Raw -Path $ConfigPath | ConvertFrom-Json
        $check = $config.checks | Where-Object { $_.id -eq "drift_gate" } | Select-Object -First 1
        if (-not $check) {
            return $fallback
        }
        $metric = $check.metrics | Where-Object { $_.path -eq "drift.step_rate" } | Select-Object -First 1
        if ($metric -and $null -ne $metric.max) {
            return [double]$metric.max
        }
    } catch {
        return $fallback
    }
    return $fallback
}

function Get-CanaryMin {
    param([string]$ConfigPath)
    $fallback = 0.5
    if (-not (Test-Path $ConfigPath)) {
        return $fallback
    }
    try {
        $config = Get-Content -Raw -Path $ConfigPath | ConvertFrom-Json
        $check = $config.checks | Where-Object { $_.id -eq "drift_holdout_gate" } | Select-Object -First 1
        if (-not $check) {
            return $fallback
        }
        if ($null -ne $check.canary_min) {
            return [double]$check.canary_min
        }
    } catch {
        return $fallback
    }
    return $fallback
}

function Get-DriftRate {
    param([string]$SummaryPath)
    if (-not (Test-Path $SummaryPath)) {
        return $null
    }
    $data = Get-Content -Raw -Path $SummaryPath | ConvertFrom-Json
    if ($null -eq $data.drift) {
        return $null
    }
    return $data.drift.step_rate
}

$holdoutScript = Join-Path $PSScriptRoot "run_drift_holdouts.ps1"

$configPath = ".\\configs\\usecase_checks.json"
$driftMax = Get-DriftMax -ConfigPath $configPath
if (-not $PSBoundParameters.ContainsKey("CanaryMin")) {
    $CanaryMin = Get-CanaryMin -ConfigPath $configPath
}

function Invoke-Variant {
    param(
        [string]$Label,
        [string]$Rerank,
        [bool]$AuthorityFilter
    )
    $env:GOLDEVIDENCEBENCH_RETRIEVAL_AUTHORITY_FILTER = if ($AuthorityFilter) { "1" } else { "0" }
    $env:GOLDEVIDENCEBENCH_RETRIEVAL_AUTHORITY_SPOOF_RATE = "$AuthoritySpoofRate"
    $env:GOLDEVIDENCEBENCH_RETRIEVAL_AUTHORITY_SPOOF_SEED = "$AuthoritySpoofSeed"
    $outDir = Join-Path $finalRunsDir $Label
    & $holdoutScript -ModelPath $ModelPath -Steps $Steps -Keys $Keys -Queries $Queries -Seeds $Seeds `
        -Rerank $Rerank -Adapter $Adapter -RunsDir $outDir -HoldoutName $HoldoutName | Out-Host
    if (-not $?) {
        throw "Holdout run failed for $Label"
    }
    $summaryPath = Join-Path $outDir "summary.json"
    [pscustomobject]@{
        name = $Label
        rerank = $Rerank
        authority_filter = $AuthorityFilter
        summary_path = $summaryPath
        drift_step_rate = Get-DriftRate -SummaryPath $summaryPath
    }
}

Write-Host "Drift holdout gate"
Write-Host "RunsDir: $finalRunsDir"
Write-Host "Holdout: $HoldoutName"
Write-Host "Canary min drift.step_rate: $CanaryMin"
Write-Host "Drift max (fix paths): $driftMax"

$canary = Invoke-Variant -Label "canary_latest_step" -Rerank "latest_step" -AuthorityFilter:$false
$fixAuthority = Invoke-Variant -Label "fix_authority_latest_step" -Rerank "latest_step" -AuthorityFilter:$FixAuthorityFilter
$fixPrefer = Invoke-Variant -Label "fix_prefer_set_latest" -Rerank $FixPreferRerank -AuthorityFilter:$FixAuthorityFilter

function Test-Variant {
    param(
        [Nullable[double]]$Rate,
        [Nullable[double]]$Min,
        [Nullable[double]]$Max
    )
    if ($null -eq $Rate) {
        return $false
    }
    if ($null -ne $Min -and $Rate -lt $Min) {
        return $false
    }
    if ($null -ne $Max -and $Rate -gt $Max) {
        return $false
    }
    return $true
}

$canaryRate = if ($canary.drift_step_rate -ne $null) { [double]$canary.drift_step_rate } else { $null }
$fixAuthorityRate = if ($fixAuthority.drift_step_rate -ne $null) { [double]$fixAuthority.drift_step_rate } else { $null }
$fixPreferRate = if ($fixPrefer.drift_step_rate -ne $null) { [double]$fixPrefer.drift_step_rate } else { $null }

$canaryPass = Test-Variant -Rate $canaryRate -Min $CanaryMin -Max $null
$fixAuthorityPass = Test-Variant -Rate $fixAuthorityRate -Min $null -Max $driftMax
$fixPreferPass = Test-Variant -Rate $fixPreferRate -Min $null -Max $driftMax

$status = if ($canaryPass -and $fixAuthorityPass -and $fixPreferPass) { "PASS" } else { "FAIL" }

$gateArtifact = $GateArtifactPath
if (-not $gateArtifact) {
    $gateDir = "runs\\release_gates"
    New-Item -ItemType Directory -Path $gateDir -Force | Out-Null
    $gateArtifact = Join-Path $gateDir "drift_holdout_gate.json"
} else {
    $gateDir = Split-Path -Parent $gateArtifact
    if ($gateDir) {
        New-Item -ItemType Directory -Path $gateDir -Force | Out-Null
    }
}

$artifact = [ordered]@{
    status = $status
    holdout = $HoldoutName
    drift_max = $driftMax
    canary_min = $CanaryMin
    runs_dir = $finalRunsDir
    canary = [ordered]@{
        rerank = $canary.rerank
        authority_filter = $canary.authority_filter
        drift_step_rate = $canaryRate
        pass = $canaryPass
        summary_path = $canary.summary_path
    }
    fix_authority = [ordered]@{
        rerank = $fixAuthority.rerank
        authority_filter = $fixAuthority.authority_filter
        drift_step_rate = $fixAuthorityRate
        pass = $fixAuthorityPass
        summary_path = $fixAuthority.summary_path
    }
    fix_prefer_set_latest = [ordered]@{
        rerank = $fixPrefer.rerank
        authority_filter = $fixPrefer.authority_filter
        drift_step_rate = $fixPreferRate
        pass = $fixPreferPass
        summary_path = $fixPrefer.summary_path
    }
}

$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($gateArtifact, ($artifact | ConvertTo-Json -Depth 6), $utf8NoBom)

if (-not $LatestDir) {
    $LatestDir = "runs\\drift_holdout_latest"
}
New-Item -ItemType Directory -Path $LatestDir -Force | Out-Null
$snapshot = $canary
if ($fixAuthorityPass) {
    $snapshot = $fixAuthority
} elseif ($fixPreferPass) {
    $snapshot = $fixPrefer
}
$summaryPath = $snapshot.summary_path
$diagnosisPath = Join-Path (Split-Path $summaryPath) "diagnosis.json"
if (Test-Path $summaryPath) {
    Copy-Item $summaryPath -Destination (Join-Path $LatestDir "summary.json") -Force
}
if (Test-Path $diagnosisPath) {
    Copy-Item $diagnosisPath -Destination (Join-Path $LatestDir "diagnosis.json") -Force
}

Write-Host "Canary drift.step_rate=$canaryRate pass=$canaryPass"
Write-Host "Fix authority drift.step_rate=$fixAuthorityRate pass=$fixAuthorityPass"
Write-Host "Fix prefer_set_latest (authority filter on) drift.step_rate=$fixPreferRate pass=$fixPreferPass"
Write-Host "Drift holdout gate: $status"
Write-Host "Latest drift holdout snapshot: $LatestDir"
Write-Host "Gate artifact: $gateArtifact"

if ($status -ne "PASS") {
    exit 1
}
