param(
    [string]$RunsRoot = "runs",
    [string]$JobsConfigPath = "configs\\capability_check_jobs.json",
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL,
    [string]$Adapter = "goldevidencebench.adapters.llama_server_adapter:create_adapter",
    [string]$SnapshotPath = "",
    [string]$SnapshotArchiveDir = "",
    [string]$OutPath = "",
    [string]$MarkdownOutPath = "",
    [string]$BeforeSnapshotPath = "",
    [switch]$RunLiveEvals,
    [switch]$SkipLiveUtilityEval,
    [switch]$SkipLiveCasePack,
    [switch]$SkipLiveTrustDemo,
    [switch]$RunLiveDriftBaseline,
    [switch]$CasePackRunOpenBook,
    [switch]$UseExistingSnapshot,
    [switch]$AllowFail
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $JobsConfigPath)) {
    Write-Error "Jobs config not found: $JobsConfigPath"
    exit 1
}

if ($RunLiveEvals -and $UseExistingSnapshot) {
    Write-Error "RunLiveEvals and UseExistingSnapshot are mutually exclusive."
    exit 1
}

if (-not $SnapshotPath) {
    $SnapshotPath = Join-Path $RunsRoot "capability_snapshot_latest.json"
}
if (-not $SnapshotArchiveDir) {
    $SnapshotArchiveDir = Join-Path $RunsRoot "capability_snapshots"
}
if (-not $OutPath) {
    $OutPath = Join-Path $RunsRoot "capability_check_latest.json"
}
if (-not $MarkdownOutPath) {
    $MarkdownOutPath = Join-Path $RunsRoot "capability_check_latest.md"
}

$resolvedModelPath = $ModelPath
if ($resolvedModelPath -and $resolvedModelPath.Contains("<")) {
    $resolvedModelPath = $env:GOLDEVIDENCEBENCH_MODEL
}
if ($resolvedModelPath -and $resolvedModelPath.Contains("<")) {
    $resolvedModelPath = ""
}
$adapterRequiresModelPath = $Adapter -like "*llama_cpp*"

if ($RunLiveEvals) {
    if ($adapterRequiresModelPath -and -not $resolvedModelPath) {
        Write-Error "RunLiveEvals requires a real -ModelPath when using llama_cpp adapters."
        exit 1
    }
    if (-not $SkipLiveUtilityEval) {
        if (Test-Path ".\\scripts\\run_real_world_utility_eval.ps1") {
            Write-Host "Running live capability producer: real_world_utility_eval..."
            & .\scripts\run_real_world_utility_eval.ps1 -Adapter $Adapter | Out-Host
            if ($LASTEXITCODE -ne 0) {
                Write-Error "real_world_utility_eval producer failed."
                exit 1
            }
        } else {
            Write-Warning "Live utility producer script missing (.\\scripts\\run_real_world_utility_eval.ps1); reusing existing utility artifact."
        }
    }
    if (-not $SkipLiveCasePack) {
        if (-not (Test-Path ".\\scripts\\run_case_pack_latest.ps1")) {
            Write-Error "Missing producer script: .\\scripts\\run_case_pack_latest.ps1"
            exit 1
        }
        Write-Host "Running live capability producer: case_pack_latest..."
        $casePackArgs = @{
            Adapter = $Adapter
            SkipRunLog = $true
        }
        if (-not [string]::IsNullOrWhiteSpace($resolvedModelPath)) {
            $casePackArgs.ModelPath = $resolvedModelPath
        }
        if (-not $CasePackRunOpenBook) {
            $casePackArgs.SkipOpenBook = $true
        }
        & .\scripts\run_case_pack_latest.ps1 @casePackArgs | Out-Host
        if ($LASTEXITCODE -ne 0) {
            Write-Error "case_pack producer failed."
            exit 1
        }
    }
    if (-not $SkipLiveTrustDemo) {
        if (-not (Test-Path ".\\scripts\\run_trust_demo.ps1")) {
            Write-Error "Missing producer script: .\\scripts\\run_trust_demo.ps1"
            exit 1
        }
        Write-Host "Running live capability producer: trust_demo..."
        $trustDemoArgs = @{
            Adapter = $Adapter
        }
        if (-not [string]::IsNullOrWhiteSpace($resolvedModelPath)) {
            $trustDemoArgs.ModelPath = $resolvedModelPath
        }
        & .\scripts\run_trust_demo.ps1 @trustDemoArgs | Out-Host
        if ($LASTEXITCODE -ne 0) {
            Write-Error "trust_demo producer failed."
            exit 1
        }
    }
    if ($RunLiveDriftBaseline) {
        if (-not (Test-Path ".\\scripts\\run_drift_holdout_compare.ps1")) {
            Write-Error "Missing producer script: .\\scripts\\run_drift_holdout_compare.ps1"
            exit 1
        }
        if ($Adapter -notlike "*retrieval_llama_cpp_adapter*") {
            Write-Error "RunLiveDriftBaseline requires retrieval_llama_cpp_adapter (drift diagnostics are adapter-specific)."
            exit 1
        }
        if (-not $resolvedModelPath) {
            Write-Error "RunLiveDriftBaseline requires -ModelPath (or GOLDEVIDENCEBENCH_MODEL)."
            exit 1
        }
        Write-Host "Running live capability producer: drift_holdout_compare..."
        & .\scripts\run_drift_holdout_compare.ps1 -Adapter $Adapter -ModelPath $resolvedModelPath | Out-Host
        if ($LASTEXITCODE -ne 0) {
            Write-Error "drift_holdout_compare producer failed."
            exit 1
        }
    }
}

if (-not $UseExistingSnapshot) {
    Write-Host "Building capability snapshot..."
    python .\scripts\build_capability_snapshot.py `
        --runs-root $RunsRoot `
        --out $SnapshotPath `
        --archive-dir $SnapshotArchiveDir
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Capability snapshot build failed."
        exit 1
    }
} else {
    if (-not (Test-Path $SnapshotPath)) {
        Write-Error "UseExistingSnapshot requested, but snapshot missing: $SnapshotPath"
        exit 1
    }
}

$checkArgs = @(
    ".\scripts\build_capability_check_report.py",
    "--jobs-config", $JobsConfigPath,
    "--runs-root", $RunsRoot,
    "--snapshot-archive-dir", $SnapshotArchiveDir,
    "--after-snapshot", $SnapshotPath,
    "--out", $OutPath,
    "--markdown-out", $MarkdownOutPath
)
if (-not [string]::IsNullOrWhiteSpace($BeforeSnapshotPath)) {
    $checkArgs += @("--before-snapshot", $BeforeSnapshotPath)
}

Write-Host "Building capability check report..."
python @checkArgs
if ($LASTEXITCODE -ne 0) {
    Write-Error "Capability check report build failed."
    exit 1
}

if (-not (Test-Path $OutPath)) {
    Write-Error "Missing capability check report artifact: $OutPath"
    exit 1
}

$report = Get-Content -Raw -Path $OutPath | ConvertFrom-Json
$status = "$($report.status)"
$regressed = 0
if ($report.summary -and $report.summary.classification_counts -and `
    ($report.summary.classification_counts.PSObject.Properties.Name -contains "Regressed")) {
    $regressed = [int]$report.summary.classification_counts.Regressed
}

.\scripts\set_latest_pointer.ps1 -RunDir $SnapshotPath -PointerPath (Join-Path $RunsRoot "latest_capability_snapshot") | Out-Host
.\scripts\set_latest_pointer.ps1 -RunDir $OutPath -PointerPath (Join-Path $RunsRoot "latest_capability_check") | Out-Host
if (Test-Path $MarkdownOutPath) {
    .\scripts\set_latest_pointer.ps1 -RunDir $MarkdownOutPath -PointerPath (Join-Path $RunsRoot "latest_capability_check_md") | Out-Host
}

Write-Host ("capability_check status={0} regressed_jobs={1} report={2}" -f $status, $regressed, $OutPath)
if ($status -eq "FAIL" -and -not $AllowFail) {
    exit 1
}
exit 0
