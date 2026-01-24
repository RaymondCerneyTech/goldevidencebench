param(
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL,
    [switch]$LatestPass
)

$ErrorActionPreference = "Stop"

if (-not $ModelPath) {
    Write-Error "Set -ModelPath or GOLDEVIDENCEBENCH_MODEL before running."
    exit 1
}

$resumeScript = Join-Path $PSScriptRoot "resume_run.ps1"

function Get-LatestPassingRunDir {
    param([string]$RunsRoot)
    $rootPath = (Resolve-Path $RunsRoot).Path
    $diagnoses = Get-ChildItem $RunsRoot -Recurse -Filter diagnosis.json |
        Where-Object { $_.DirectoryName -ne $rootPath -and $_.FullName -notmatch '\\release_gates\\' }
    if (-not $diagnoses) {
        return $null
    }
    $passing = foreach ($diag in $diagnoses) {
        try {
            $raw = Get-Content -Raw -Path $diag.FullName
            $data = $raw.TrimStart([char]0xFEFF) | ConvertFrom-Json
        } catch {
            continue
        }
        if ($data.status -eq "PASS") {
            $diag
        }
    }
    if (-not $passing) {
        return $null
    }
    return ($passing | Sort-Object LastWriteTime -Descending | Select-Object -First 1).DirectoryName
}

function Get-ModelFingerprint {
    param([string]$Path)
    if (-not $Path -or -not (Test-Path $Path)) {
        return @{ path = $Path; exists = $false }
    }
    $file = Get-Item $Path
    $hashHex = $null
    try {
        $sha256 = [System.Security.Cryptography.SHA256]::Create()
        $stream = [System.IO.File]::OpenRead($Path)
        $buffer = New-Object byte[] (1024 * 1024)
        $read = $stream.Read($buffer, 0, $buffer.Length)
        $stream.Close()
        if ($read -gt 0) {
            $hash = $sha256.ComputeHash($buffer, 0, $read)
            $hashHex = ([BitConverter]::ToString($hash)).Replace("-", "").ToLower()
        }
    } catch {
        $hashHex = $null
    }
    return @{
        path = $Path
        exists = $true
        size_bytes = $file.Length
        mtime = $file.LastWriteTimeUtc.ToString("o")
        sha256_1mb = $hashHex
    }
}

Write-Host "Running health check (resume + drift gate)..."
$resumeParams = @{
    RunDriftGate = $true
    ModelPath = $ModelPath
}
if ($LatestPass) {
    $passingDir = Get-LatestPassingRunDir -RunsRoot "runs"
    if (-not $passingDir) {
        Write-Error "No passing run with diagnosis.json found under runs\."
        exit 1
    }
    $resumeParams["RunDir"] = $passingDir
} else {
    $resumeParams["Latest"] = $true
}
$resumeOutput = & $resumeScript @resumeParams 2>&1 | Tee-Object -Variable resumeOutput
if (-not $?) {
    exit 1
}

$resumeDir = Get-ChildItem .\runs -Directory -Filter "resume_*" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $resumeDir) {
    Write-Error "No resume_* run directory found under runs\."
    exit 1
}

$reportPath = Join-Path $resumeDir.FullName "report.md"
$overall = "UNKNOWN"
if (Test-Path $reportPath) {
    $overallLine = (Get-Content -Path $reportPath | Select-String -Pattern "^Overall:").Line
    if ($overallLine) {
        $overall = $overallLine -replace "^Overall:\s*", ""
    }
}

$warnLines = $resumeOutput | Where-Object { $_ -match "^\[FAIL\(warn\)\]" -or $_ -match "^\[WARN\]" }
$failLines = $resumeOutput | Where-Object { $_ -match "^\[(FAIL|MISSING)" -or $_ -match "Drift holdout gate: FAIL" }

$checksStatus = "PASS"
if ($failLines -or $warnLines) {
    $checksStatus = "FAIL"
}

$health = @{
    schema_version = "1"
    artifact_version = "1.0.0"
    timestamp = (Get-Date).ToUniversalTime().ToString("o")
    run_dir = $resumeDir.FullName
    report_path = $reportPath
    overall = $checksStatus
    checks_overall = $checksStatus
    report_overall = $overall
    model = (Get-ModelFingerprint -Path $ModelPath)
}

$healthPath = Join-Path $resumeDir.FullName "health_check.json"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($healthPath, ($health | ConvertTo-Json -Depth 6), $utf8NoBom)
python .\scripts\validate_artifact.py --schema .\schemas\health_check.schema.json --path $healthPath | Out-Host
if (-not $?) {
    throw "health_check.json schema validation failed"
}

Write-Host "Health check: $checksStatus (report=$overall)"
Write-Host "Health artifact: $healthPath"

if ($checksStatus -ne "PASS") {
    exit 1
}
