param(
    [string]$RunDir,
    [switch]$Latest,
    [switch]$RunDriftGate,
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL
)

$ErrorActionPreference = "Stop"

function Get-LatestRunDir {
    param([string]$RunsRoot)
    if (-not (Test-Path $RunsRoot)) {
        throw "Runs root not found: $RunsRoot"
    }
    $rootPath = (Resolve-Path $RunsRoot).Path
    $summaries = Get-ChildItem $RunsRoot -Recurse -Filter summary.json |
        Where-Object { $_.DirectoryName -ne $rootPath -and $_.FullName -notmatch '\\release_gates\\' }
    if (-not $summaries) {
        throw "No summary.json found under $RunsRoot"
    }
    $withDiag = $summaries | Where-Object { Test-Path (Join-Path $_.DirectoryName "diagnosis.json") }
    $preferred = if ($withDiag) { $withDiag } else { $summaries }
    return ($preferred | Sort-Object LastWriteTime -Descending | Select-Object -First 1).DirectoryName
}

function Resolve-ArtifactPath {
    param(
        [string]$BaseDir,
        [string]$Candidate
    )
    if (-not $Candidate) {
        return $null
    }
    $path = $Candidate
    if (-not [System.IO.Path]::IsPathRooted($path)) {
        $path = Join-Path $BaseDir $path
    }
    if (Test-Path $path) {
        return $path
    }
    return $null
}

if ($Latest) {
    $RunDir = Get-LatestRunDir -RunsRoot "runs"
}
if (-not $RunDir) {
    Write-Error "Set -RunDir or use -Latest."
    exit 1
}

$parentRunDir = (Resolve-Path $RunDir).Path
$parentCompact = Join-Path $parentRunDir "compact_state.json"
if (-not (Test-Path $parentCompact)) {
    Write-Error "compact_state.json not found in $parentRunDir"
    exit 1
}

$parentSummary = Join-Path $parentRunDir "summary.json"
$parentDiagnosis = Join-Path $parentRunDir "diagnosis.json"

$compactState = Get-Content -Raw -Path $parentCompact | ConvertFrom-Json
if ((-not (Test-Path $parentSummary)) -and $compactState.last_known_good) {
    $parentSummary = Resolve-ArtifactPath -BaseDir $parentRunDir -Candidate $compactState.last_known_good.summary
}
if ((-not (Test-Path $parentDiagnosis)) -and $compactState.last_known_good) {
    $parentDiagnosis = Resolve-ArtifactPath -BaseDir $parentRunDir -Candidate $compactState.last_known_good.diagnosis
}

if (-not $parentSummary -or -not (Test-Path $parentSummary)) {
    Write-Error "summary.json not found for $parentRunDir"
    exit 1
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$resumeDir = Join-Path "runs" "resume_$stamp"
New-Item -ItemType Directory -Path $resumeDir -Force | Out-Null

Copy-Item $parentSummary -Destination (Join-Path $resumeDir "summary.json") -Force
if ($parentDiagnosis -and (Test-Path $parentDiagnosis)) {
    Copy-Item $parentDiagnosis -Destination (Join-Path $resumeDir "diagnosis.json") -Force
}
$parentRepro = Join-Path $parentRunDir "repro_commands.json"
if (Test-Path $parentRepro) {
    $reproOut = Join-Path $resumeDir "repro_commands.json"
    Copy-Item $parentRepro -Destination $reproOut -Force
    try {
        $reproData = Get-Content -Raw -Path $reproOut | ConvertFrom-Json
        $defaults = @{
            schema_version = "1"
            artifact_version = "1.0.0"
            generated_at = (Get-Date).ToUniversalTime().ToString("o")
            commands = @()
            command_line = ""
            args = @()
            config = @{}
            env = @{}
            key_env = @{}
            model = @{
                path = $ModelPath
                exists = $false
                size_bytes = $null
                mtime = $null
                sha256_1mb = $null
            }
            config_paths = @{
                combined_json = $null
                summary_json = "summary.json"
                data_path = $null
            }
            authority_mode = "unknown"
        }
        foreach ($key in $defaults.Keys) {
            if (-not $reproData.PSObject.Properties.Match($key)) {
                $reproData | Add-Member -MemberType NoteProperty -Name $key -Value $defaults[$key] -Force
            }
        }
        $utf8NoBom = New-Object System.Text.UTF8Encoding $false
        [System.IO.File]::WriteAllText($reproOut, ($reproData | ConvertTo-Json -Depth 6), $utf8NoBom)
    } catch {
        # Best-effort update only; schema validation will surface issues.
    }
    python .\scripts\validate_artifact.py --schema .\schemas\repro_commands.schema.json --path $reproOut | Out-Host
    if (-not $?) {
        throw "repro_commands.json schema validation failed"
    }
} else {
    $resumeCommand = $MyInvocation.Line
    $repro = @{
        schema_version = "1"
        artifact_version = "1.0.0"
        generated_at = (Get-Date).ToUniversalTime().ToString("o")
        commands = @($resumeCommand)
        command_line = $resumeCommand
        args = @()
        baseline = $null
        adapter = $null
        protocol = $null
        state_mode = $null
        seed = $null
        steps = $null
        retrieval = @{}
        config = @{}
        env = @{}
        key_env = @{}
        model = @{
            path = $ModelPath
            exists = $false
            size_bytes = $null
            mtime = $null
            sha256_1mb = $null
        }
        git_commit = $null
        config_paths = @{
            combined_json = $null
            summary_json = "summary.json"
            data_path = $null
        }
        authority_mode = "unknown"
        note = "resume_run did not find parent repro_commands.json"
        parent_run_dir = $parentRunDir
    }
    $reproOut = Join-Path $resumeDir "repro_commands.json"
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($reproOut, ($repro | ConvertTo-Json -Depth 6), $utf8NoBom)
    python .\scripts\validate_artifact.py --schema .\schemas\repro_commands.schema.json --path $reproOut | Out-Host
    if (-not $?) {
        throw "repro_commands.json schema validation failed"
    }
}

$resumeRunId = Split-Path -Leaf $resumeDir
$resumeRunPath = (Resolve-Path $resumeDir).Path
$resumeUpdated = [DateTime]::UtcNow.ToString("o")

$compactState | Add-Member -MemberType NoteProperty -Name run_id -Value $resumeRunId -Force
$compactState | Add-Member -MemberType NoteProperty -Name run_dir -Value $resumeRunPath -Force
$compactState | Add-Member -MemberType NoteProperty -Name updated_at -Value $resumeUpdated -Force
$compactState | Add-Member -MemberType NoteProperty -Name parent_run_dir -Value $parentRunDir -Force
if (-not $compactState.PSObject.Properties.Match("schema_version")) {
    $compactState | Add-Member -MemberType NoteProperty -Name schema_version -Value "1" -Force
}
if (-not $compactState.PSObject.Properties.Match("artifact_version")) {
    $compactState | Add-Member -MemberType NoteProperty -Name artifact_version -Value "1.0.0" -Force
}

if (-not $compactState.PSObject.Properties.Match("last_known_good")) {
    $compactState | Add-Member -MemberType NoteProperty -Name last_known_good -Value @{}
}
$compactState.last_known_good.summary = "summary.json"
$compactState.last_known_good.diagnosis = if (Test-Path (Join-Path $resumeDir "diagnosis.json")) { "diagnosis.json" } else { $null }
$compactState.last_known_good.report = "report.md"
$compactState.last_known_good.gate_artifacts = @()

$utf8NoBom = New-Object System.Text.UTF8Encoding $false
$compactOut = Join-Path $resumeDir "compact_state.json"
[System.IO.File]::WriteAllText($compactOut, ($compactState | ConvertTo-Json -Depth 6), $utf8NoBom)
python .\scripts\validate_artifact.py --schema .\schemas\compact_state.schema.json --path $compactOut | Out-Host
if (-not $?) {
    throw "compact_state.json schema validation failed"
}

Write-Host "Resumed run dir: $resumeDir"
Write-Host "Parent run dir: $parentRunDir"

python .\scripts\generate_report.py --run-dir $resumeDir | Out-Host
if (-not $?) {
    throw "generate_report failed"
}

python .\scripts\check_thresholds.py --config .\configs\usecase_checks.json | Out-Host
if (-not $?) {
    throw "check_thresholds failed"
}

if ($RunDriftGate) {
    if (-not $ModelPath) {
        Write-Error "Set -ModelPath or GOLDEVIDENCEBENCH_MODEL before running -RunDriftGate."
        exit 1
    }
    $driftRunsDir = Join-Path $resumeDir "drift_holdout_gate"
    .\scripts\run_drift_holdout_gate.ps1 -ModelPath $ModelPath -RunsDir $driftRunsDir | Out-Host
    if (-not $?) {
        throw "run_drift_holdout_gate failed"
    }

    $fixDirs = @(
        (Join-Path $driftRunsDir "fix_authority_latest_step"),
        (Join-Path $driftRunsDir "fix_prefer_set_latest")
    )
    $bestDir = $null
    $bestRate = $null
    foreach ($dir in $fixDirs) {
        $summary = Join-Path $dir "summary.json"
        if (-not (Test-Path $summary)) {
            continue
        }
        try {
            $data = Get-Content -Raw -Path $summary | ConvertFrom-Json
        } catch {
            continue
        }
        $rate = $null
        if ($data.drift -and $null -ne $data.drift.step_rate) {
            $rate = [double]$data.drift.step_rate
        }
        if ($null -eq $bestDir) {
            $bestDir = $dir
            $bestRate = $rate
            continue
        }
        if ($null -ne $rate -and ($null -eq $bestRate -or $rate -lt $bestRate)) {
            $bestDir = $dir
            $bestRate = $rate
        }
    }
    if ($bestDir) {
        python .\scripts\generate_report.py --run-dir $bestDir --print | Out-Host
        if (-not $?) {
            throw "generate_report failed for drift fix run"
        }
        Write-Host "Drift fix report: $(Join-Path $bestDir 'report.md')"
    } else {
        Write-Warning "No drift fix runs found to generate a report."
    }
}
