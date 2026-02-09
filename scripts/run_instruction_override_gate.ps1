param(
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL,
    [string]$Adapter = "goldevidencebench.adapters.retrieval_llama_cpp_adapter:create_adapter",
    [string]$OutDir = "runs\\release_gates\\instruction_override_gate",
    [int]$ProgressPollSeconds = 10,
    [switch]$AllowConcurrent
)

if ($ModelPath -eq "<MODEL_PATH>") {
    Write-Error "Replace placeholder <MODEL_PATH> with a real path, or omit -ModelPath when using llama_server_adapter."
    exit 1
}

New-Item -ItemType Directory -Path $OutDir -Force | Out-Null

# Keep this gate deterministic and progress-readable: remove prior sweep shards.
$staleShards = Get-ChildItem -Path $OutDir -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "seed*-steps*" }
if ($staleShards) {
    foreach ($dir in $staleShards) {
        Remove-Item -Path $dir.FullName -Recurse -Force -ErrorAction SilentlyContinue
    }
}
foreach ($artifact in @("combined.json", "summary.json")) {
    $artifactPath = Join-Path $OutDir $artifact
    if (Test-Path $artifactPath) {
        Remove-Item -Path $artifactPath -Force -ErrorAction SilentlyContinue
    }
}

if (-not $AllowConcurrent) {
    $existingSweep = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.ProcessId -ne $PID -and
            $_.CommandLine -like "*goldevidencebench* sweep*" -and
            $_.CommandLine -like "*instruction_override_gate*"
        }
    if ($existingSweep) {
        Write-Error "Another instruction override sweep is already running. Stop it or pass -AllowConcurrent."
        $existingSweep | Select-Object ProcessId, Name, CommandLine | Format-List | Out-Host
        exit 1
    }
}

if (-not ($Adapter -like "*llama_server_adapter*")) {
    if (-not $ModelPath) {
        Write-Error "Set -ModelPath or GOLDEVIDENCEBENCH_MODEL before running."
        exit 1
    }
    $env:GOLDEVIDENCEBENCH_MODEL = $ModelPath
}

$env:GOLDEVIDENCEBENCH_RETRIEVAL_DETERMINISTIC_ANSWER = "1"
$env:GOLDEVIDENCEBENCH_RETRIEVAL_COPY_CLAMP = "1"
$env:GOLDEVIDENCEBENCH_RETRIEVAL_RERANK = "prefer_update_latest"
$env:GOLDEVIDENCEBENCH_RETRIEVAL_K = "4"

$seeds = 4
$stateModes = @("kv", "set")
$distractorProfiles = @("standard", "instruction_suite")
$totalRuns = $seeds * $stateModes.Count * $distractorProfiles.Count

$stdoutLog = Join-Path $OutDir "sweep_stdout.log"
$stderrLog = Join-Path $OutDir "sweep_stderr.log"
if (Test-Path $stdoutLog) { Remove-Item $stdoutLog -Force }
if (Test-Path $stderrLog) { Remove-Item $stderrLog -Force }

$sweepArgs = @(
    "sweep",
    "--out", $OutDir,
    "--seeds", "$seeds",
    "--episodes", "1",
    "--steps", "80",
    "--queries", "16",
    "--state-modes", ($stateModes -join ","),
    "--distractor-profiles", ($distractorProfiles -join ","),
    "--adapter", $Adapter,
    "--no-derived-queries",
    "--no-twins",
    "--require-citations",
    "--results-json", "$OutDir\combined.json",
    "--max-book-tokens", "400"
)
$pythonArgs = @(
    "-m",
    "goldevidencebench.cli"
) + $sweepArgs

$pythonExe = (Get-Command python -ErrorAction Stop).Source
Write-Host ("Instruction override sweep started (runs={0}, python={1})..." -f $totalRuns, $pythonExe)
$start = Get-Date
$startUtc = $start.ToUniversalTime()
$proc = Start-Process `
    -FilePath $pythonExe `
    -ArgumentList $pythonArgs `
    -NoNewWindow `
    -PassThru `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog

$lastCompleted = 0
while (-not $proc.HasExited) {
    Start-Sleep -Seconds $ProgressPollSeconds

    $completed = (
        Get-ChildItem -Path $OutDir -Directory -ErrorAction SilentlyContinue |
        ForEach-Object { Join-Path $_.FullName "results.json" } |
        Where-Object { Test-Path $_ } |
        ForEach-Object { Get-Item $_ } |
        Where-Object { $_.LastWriteTimeUtc -ge $startUtc } |
        Measure-Object
    ).Count
    if ($completed -gt $totalRuns) { $completed = $totalRuns }

    if ($completed -gt $lastCompleted) {
        $elapsed = (Get-Date) - $start
        Write-Host ("Instruction override progress: completed={0}/{1} ({2:mm\:ss})" -f $completed, $totalRuns, $elapsed)
        $lastCompleted = $completed
    }
}

$finalCompleted = (
    Get-ChildItem -Path $OutDir -Directory -ErrorAction SilentlyContinue |
    ForEach-Object { Join-Path $_.FullName "results.json" } |
    Where-Object { Test-Path $_ } |
    ForEach-Object { Get-Item $_ } |
    Where-Object { $_.LastWriteTimeUtc -ge $startUtc } |
    Measure-Object
).Count
if ($finalCompleted -gt $totalRuns) { $finalCompleted = $totalRuns }
Write-Host ("Instruction override final: {0}/{1} runs ({2:mm\:ss})" -f $finalCompleted, $totalRuns, ((Get-Date) - $start))

$proc.WaitForExit()
$proc.Refresh()
$exitCode = $proc.ExitCode
if ($null -eq $exitCode) {
    $exitCode = 1
}

$combinedPath = Join-Path $OutDir "combined.json"
$artifactsComplete = ($finalCompleted -ge $totalRuns) -and (Test-Path $combinedPath)
if ($exitCode -ne 0 -and -not $artifactsComplete) {
    Write-Error ("Instruction override sweep failed (exit {0}). See {1} and {2}" -f $exitCode, $stdoutLog, $stderrLog)
    if (Test-Path $stderrLog) {
        Get-Content $stderrLog -Tail 20 | ForEach-Object { Write-Host $_ }
    }
    exit $exitCode
}
if ($exitCode -ne 0 -and $artifactsComplete) {
    Write-Warning ("Instruction override sweep exited {0}, but artifacts are complete ({1}/{2}) and combined.json exists; continuing." -f $exitCode, $finalCompleted, $totalRuns)
}

python .\scripts\summarize_results.py --in "$OutDir\combined.json" --out-json "$OutDir\summary.json"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Instruction override summary failed."
    exit $LASTEXITCODE
}

Write-Host "Instruction override gate: $OutDir\\summary.json"
