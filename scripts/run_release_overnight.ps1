<#
.SYNOPSIS
Runs release checks unattended with watchdog + retry logic.

.DESCRIPTION
Wrapper around `scripts/run_release_check.ps1` with:
- optional llama-server preflight,
- stall detection (no CPU/log activity),
- automatic retry,
- orthogonal holdout rotation (drift + bad actor).

The selected holdouts are fixed for all retries in the same wrapper run,
then advanced for the next wrapper invocation via a rotation state file.

.EXAMPLE
.\scripts\run_release_overnight.ps1 -GateAdapter "goldevidencebench.adapters.llama_server_adapter:create_adapter"

.EXAMPLE
.\scripts\run_release_overnight.ps1 -ModelPath "<MODEL_PATH>" -RunDriftHoldoutGate $true
#>
param(
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL,
    [string]$GateAdapter = "goldevidencebench.adapters.retrieval_llama_cpp_adapter:create_adapter",
    [int]$Cycles = 1,
    [double]$RunHours = 0,
    [int]$MaxAttempts = 2,
    [int]$PollSeconds = 20,
    [int]$StallMinutes = 8,
    [int]$SleepBetweenCyclesSeconds = 10,
    [switch]$SkipThresholds,
    [switch]$SkipReliabilitySignal,
    [switch]$SkipRequireControlFamilies,
    [bool]$RunDriftHoldoutGate = $false,
    [string]$DriftHoldoutList = "stale_tab_state,focus_drift",
    [string]$BadActorHoldoutListPath = "configs\\bad_actor_holdout_list.json",
    [string]$RotationStatePath = "runs\\release_gates\\overnight_holdout_rotation.json",
    [switch]$RotateUiHoldout,
    [string]$UiHoldoutListPath = "configs\\ui_holdout_list.json",
    [string]$UiHoldoutList = "",
    [string]$ServerRestartCommand = "",
    [int]$ServerStartupSeconds = 10,
    [int]$ServerPreflightTimeoutSeconds = 15
)

function Resolve-PreferredEnvValue {
    param([string]$Name)
    $scopes = @("Process", "User", "Machine")
    foreach ($scope in $scopes) {
        $value = [Environment]::GetEnvironmentVariable($Name, $scope)
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            return $value.Trim()
        }
    }
    return ""
}

if (-not $PSBoundParameters.ContainsKey("ModelPath")) {
    $resolvedModelPath = Resolve-PreferredEnvValue -Name "GOLDEVIDENCEBENCH_MODEL"
    if (-not [string]::IsNullOrWhiteSpace($resolvedModelPath)) {
        $ModelPath = $resolvedModelPath
    }
}
if (-not $PSBoundParameters.ContainsKey("GateAdapter")) {
    $resolvedGateAdapter = Resolve-PreferredEnvValue -Name "GOLDEVIDENCEBENCH_GATE_ADAPTER"
    if (-not [string]::IsNullOrWhiteSpace($resolvedGateAdapter)) {
        $GateAdapter = $resolvedGateAdapter
    }
}

$overnightUsesExternalModelService = ($GateAdapter -like "*llama_server_adapter*") -or ($GateAdapter -like "*mock_adapter*")

if ($MaxAttempts -lt 1) {
    Write-Error "MaxAttempts must be >= 1."
    exit 1
}
if ($Cycles -lt 1) {
    Write-Error "Cycles must be >= 1."
    exit 1
}
if ($RunHours -lt 0) {
    Write-Error "RunHours must be >= 0."
    exit 1
}
if ($PollSeconds -lt 1) {
    Write-Error "PollSeconds must be >= 1."
    exit 1
}
if ($StallMinutes -lt 1) {
    Write-Error "StallMinutes must be >= 1."
    exit 1
}
if ($RunDriftHoldoutGate -and -not $overnightUsesExternalModelService -and -not $ModelPath) {
    Write-Error ("RunDriftHoldoutGate requires -ModelPath (or GOLDEVIDENCEBENCH_MODEL) for adapter '{0}'." -f $GateAdapter)
    exit 1
}
$explicitCycles = $PSBoundParameters.ContainsKey("Cycles")
$explicitRunHours = $PSBoundParameters.ContainsKey("RunHours")
if ($RunHours -gt 0 -and $explicitCycles) {
    Write-Warning "Both -RunHours and -Cycles were provided. -RunHours mode takes precedence; -Cycles is ignored."
}
if ($RunHours -eq 0 -and $Cycles -eq 1) {
    if (-not $explicitCycles -and -not $explicitRunHours) {
        Write-Warning "Default mode is a single release cycle (not a true overnight window). Set -RunHours 8 (or -Cycles N) to run longer."
    } else {
        Write-Warning "Configured for a single release cycle. Use -RunHours 8 (or -Cycles N) for a longer overnight run."
    }
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$overnightDir = "runs\\release_overnight_$stamp"
$logsDir = Join-Path $overnightDir "logs"
New-Item -ItemType Directory -Path $logsDir -Force | Out-Null

function Read-JsonObject {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        return $null
    }
    try {
        return Get-Content -Raw -Path $Path | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Write-JsonObject {
    param(
        [string]$Path,
        [object]$Object
    )
    $dir = Split-Path -Parent $Path
    if ($dir) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($Path, ($Object | ConvertTo-Json -Depth 8), $utf8NoBom)
}

function Resolve-LlamaServerUrl {
    $full = $env:GOLDEVIDENCEBENCH_LLAMA_SERVER_URL
    if ($full) {
        return $full
    }
    $base = $env:GOLDEVIDENCEBENCH_LLAMA_SERVER_BASE_URL
    if (-not $base) {
        $base = "http://localhost:8080"
    }
    $endpoint = $env:GOLDEVIDENCEBENCH_LLAMA_SERVER_ENDPOINT
    if (-not $endpoint) {
        $endpoint = "/completion"
    }
    if (-not $endpoint.StartsWith("/")) {
        $endpoint = "/$endpoint"
    }
    return ($base.TrimEnd("/") + $endpoint)
}

function Test-LlamaServerReady {
    param(
        [string]$Url,
        [int]$TimeoutSeconds
    )
    try {
        $payload = @{
            prompt = "ping"
            n_predict = 1
            stop = @("###")
        } | ConvertTo-Json -Compress
        $null = Invoke-RestMethod -Method Post -Uri $Url -ContentType "application/json" -Body $payload -TimeoutSec $TimeoutSeconds
        return $true
    } catch {
        return $false
    }
}

function Restart-LlamaServerIfConfigured {
    param(
        [string]$Reason,
        [string]$ServerUrl
    )
    if (-not $ServerRestartCommand) {
        Write-Warning ("Cannot auto-restart llama server ({0}): -ServerRestartCommand not set." -f $Reason)
        return $false
    }
    Write-Warning ("Restarting llama server ({0})..." -f $Reason)
    $llamaProcs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ieq "llama-server.exe" }
    foreach ($proc in $llamaProcs) {
        try { Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue } catch {}
    }
    Start-Process -FilePath "powershell" `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $ServerRestartCommand) `
        -WindowStyle Hidden | Out-Null
    Start-Sleep -Seconds $ServerStartupSeconds
    return (Test-LlamaServerReady -Url $ServerUrl -TimeoutSeconds $ServerPreflightTimeoutSeconds)
}

function Get-ListFromCsv {
    param([string]$Csv)
    return @(
        $Csv -split "," |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ }
    )
}

function Get-BadActorIds {
    param([string]$ListPath)
    if (-not (Test-Path $ListPath)) {
        return @()
    }
    try {
        $cfg = Get-Content -Raw -Path $ListPath | ConvertFrom-Json
    } catch {
        return @()
    }
    if (-not $cfg -or -not $cfg.holdouts) {
        return @()
    }
    $ids = @()
    foreach ($entry in $cfg.holdouts) {
        if ($entry -is [string]) {
            continue
        }
        if ($entry.id) {
            $ids += $entry.id.ToString()
        }
    }
    return @($ids)
}

function Select-And-Advance {
    param(
        [string[]]$Items,
        [int]$Index
    )
    if (-not $Items -or $Items.Count -eq 0) {
        return [pscustomobject]@{
            selected = ""
            next_index = 0
            used_index = 0
        }
    }
    $used = 0
    if ($Index -ge 0) {
        $used = $Index % $Items.Count
    }
    return [pscustomobject]@{
        selected = $Items[$used]
        next_index = (($used + 1) % $Items.Count)
        used_index = $used
    }
}

$driftCandidates = Get-ListFromCsv -Csv $DriftHoldoutList
$badActorCandidates = Get-BadActorIds -ListPath $BadActorHoldoutListPath

function Get-NextHoldoutSelection {
    $state = Read-JsonObject -Path $RotationStatePath
    $driftIdx = 0
    $badActorIdx = 0
    if ($state) {
        if ($state.drift_index -is [int]) { $driftIdx = [int]$state.drift_index }
        if ($state.bad_actor_index -is [int]) { $badActorIdx = [int]$state.bad_actor_index }
    }

    $driftPick = Select-And-Advance -Items $driftCandidates -Index $driftIdx
    $badActorPick = Select-And-Advance -Items $badActorCandidates -Index $badActorIdx

    Write-JsonObject -Path $RotationStatePath -Object ([ordered]@{
        drift_index = $driftPick.next_index
        bad_actor_index = $badActorPick.next_index
        drift_selected = $driftPick.selected
        bad_actor_selected = $badActorPick.selected
        drift_candidates = $driftCandidates
        bad_actor_candidates = $badActorCandidates
        updated_at = (Get-Date -Format "s")
    })

    return [pscustomobject]@{
        drift = $driftPick.selected
        bad_actor = $badActorPick.selected
    }
}

Write-Host "Release overnight wrapper"
Write-Host "OutDir: $overnightDir"
if ($RunHours -gt 0) {
    Write-Host ("Mode: run-for-hours ({0}h)" -f $RunHours)
} else {
    Write-Host ("Mode: fixed-cycles ({0})" -f $Cycles)
}
if ($RotateUiHoldout) {
    Write-Host "UI holdout rotation: enabled"
}
if ($SkipRequireControlFamilies) {
    Write-Warning "SkipRequireControlFamilies enabled: overnight run will not require RPA/intent/noise families in release gate."
}

$usesServerAdapter = $GateAdapter -like "*llama_server_adapter*"
$serverUrl = ""
if ($usesServerAdapter) {
    $serverUrl = Resolve-LlamaServerUrl
    Write-Host "llama-server preflight URL: $serverUrl"
    $ready = Test-LlamaServerReady -Url $serverUrl -TimeoutSeconds $ServerPreflightTimeoutSeconds
    if (-not $ready) {
        Write-Warning "llama-server preflight failed."
        $ready = Restart-LlamaServerIfConfigured -Reason "preflight_failed" -ServerUrl $serverUrl
    }
    if (-not $ready) {
        Write-Error "llama-server is not ready; aborting overnight run."
        exit 1
    }
}

function Get-LatestReleaseDir {
    $latestPath = "runs\\latest_release"
    if (-not (Test-Path $latestPath)) {
        return ""
    }
    return (Get-Content -Raw -Path $latestPath).Trim()
}

function Start-ReleaseAttempt {
    param(
        [int]$CycleNumber,
        [int]$AttemptNumber
    )
    $stdoutLog = Join-Path $logsDir ("cycle_{0}_attempt_{1}_stdout.log" -f $CycleNumber, $AttemptNumber)
    $stderrLog = Join-Path $logsDir ("cycle_{0}_attempt_{1}_stderr.log" -f $CycleNumber, $AttemptNumber)
    $exitCodePath = Join-Path $logsDir ("cycle_{0}_attempt_{1}_exitcode.txt" -f $CycleNumber, $AttemptNumber)
    if (Test-Path $stdoutLog) { Remove-Item $stdoutLog -Force }
    if (Test-Path $stderrLog) { Remove-Item $stderrLog -Force }
    if (Test-Path $exitCodePath) { Remove-Item $exitCodePath -Force }

    $args = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ".\scripts\run_release_check.ps1")
    $args += @("-GateAdapter", $GateAdapter)
    if ($ModelPath) {
        $args += @("-ModelPath", $ModelPath)
    }
    if ($SkipThresholds) {
        $args += "-SkipThresholds"
    }
    if ($SkipReliabilitySignal) {
        $args += "-SkipReliabilitySignal"
    }
    if ($SkipRequireControlFamilies) {
        $args += "-SkipRequireControlFamilies"
    }
    if ($RunDriftHoldoutGate) {
        $args += "-RunDriftHoldoutGate"
        if ($selectedDriftHoldout) {
            $args += @("-DriftHoldoutName", $selectedDriftHoldout)
        }
    }
    if ($selectedBadActorHoldout) {
        $args += @("-BadActorHoldoutId", $selectedBadActorHoldout)
    }
    if ($BadActorHoldoutListPath) {
        $args += @("-BadActorHoldoutListPath", $BadActorHoldoutListPath)
    }
    if ($RotateUiHoldout) {
        $args += "-RotateHoldout"
        if ($UiHoldoutListPath) {
            $args += @("-HoldoutListPath", $UiHoldoutListPath)
        }
        if ($UiHoldoutList) {
            $args += @("-HoldoutList", $UiHoldoutList)
        }
    }

    Write-Host ("Cycle {0} attempt {1}/{2}: launching release check..." -f $CycleNumber, $AttemptNumber, $MaxAttempts)
    $start = Get-Date
    $quotedArgs = @(
        $args | ForEach-Object {
            '"' + ($_.ToString().Replace('"', '\"')) + '"'
        }
    )
    $cmdLine = @(
        "powershell",
        ($quotedArgs -join " "),
        ('1>"{0}"' -f $stdoutLog),
        ('2>"{0}"' -f $stderrLog),
        ('& echo %errorlevel% > "{0}"' -f $exitCodePath)
    ) -join " "
    $proc = Start-Process `
        -FilePath "cmd.exe" `
        -WorkingDirectory (Get-Location).Path `
        -ArgumentList @("/c", $cmdLine) `
        -NoNewWindow `
        -PassThru

    $lastActivity = Get-Date
    $lastBytes = 0L
    $lastCpuMs = 0.0
    while ($true) {
        $proc.Refresh()
        if ($proc.HasExited) {
            break
        }

        Start-Sleep -Seconds $PollSeconds

        $proc.Refresh()
        if ($proc.HasExited) {
            break
        }

        $stdoutBytes = 0L
        $stderrBytes = 0L
        if (Test-Path $stdoutLog) {
            $stdoutBytes = (Get-Item $stdoutLog).Length
        }
        if (Test-Path $stderrLog) {
            $stderrBytes = (Get-Item $stderrLog).Length
        }
        $bytes = $stdoutBytes + $stderrBytes
        $cpuMs = $lastCpuMs
        try { $cpuMs = $proc.TotalProcessorTime.TotalMilliseconds } catch {}

        $activity = ($bytes -gt $lastBytes) -or ($cpuMs -gt $lastCpuMs)
        if ($activity) {
            $lastActivity = Get-Date
            $lastBytes = $bytes
            $lastCpuMs = $cpuMs
        } else {
            $idle = (Get-Date) - $lastActivity
            if ($idle.TotalMinutes -ge $StallMinutes) {
                Write-Warning ("Attempt {0}: stall detected (idle {1:mm\:ss}); terminating run_release_check." -f $AttemptNumber, $idle)
                try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch {}
                return [pscustomobject]@{
                    status = "stalled"
                    exit_code = 124
                    stdout_log = $stdoutLog
                    stderr_log = $stderrLog
                    elapsed_s = [math]::Round(((Get-Date) - $start).TotalSeconds, 1)
                    latest_release = Get-LatestReleaseDir
                }
            }
        }
    }

    $proc.WaitForExit()
    $proc.Refresh()
    $exitCode = $null
    if (Test-Path $exitCodePath) {
        try {
            $exitText = (Get-Content -Raw -Path $exitCodePath).Trim()
            if ($exitText -match "^-?\d+$") {
                $exitCode = [int]$exitText
            }
        } catch {}
    }
    if ($null -eq $exitCode) {
        $proc.Refresh()
        $exitCode = $proc.ExitCode
    }
    if ($null -eq $exitCode) {
        $exitCode = 1
    }
    $status = if ($exitCode -eq 0) { "pass" } else { "fail" }
    return [pscustomobject]@{
        status = $status
        exit_code = $exitCode
        stdout_log = $stdoutLog
        stderr_log = $stderrLog
        elapsed_s = [math]::Round(((Get-Date) - $start).TotalSeconds, 1)
        latest_release = Get-LatestReleaseDir
    }
}

$cycleResults = @()
$allCyclesPass = $true
$deadline = $null
if ($RunHours -gt 0) {
    $deadline = (Get-Date).AddHours($RunHours)
}

$cycle = 1
while ($true) {
    if ($RunHours -gt 0 -and (Get-Date) -ge $deadline) {
        break
    }
    if ($RunHours -le 0 -and $cycle -gt $Cycles) {
        break
    }

    $selection = Get-NextHoldoutSelection
    $selectedDriftHoldout = $selection.drift
    $selectedBadActorHoldout = $selection.bad_actor
    Write-Host ("Cycle {0}: selected holdouts drift={1}, bad_actor={2}" -f $cycle, $selectedDriftHoldout, $selectedBadActorHoldout)

    $attempts = @()
    $cycleStatus = "FAIL"
    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        if ($usesServerAdapter) {
            $ready = Test-LlamaServerReady -Url $serverUrl -TimeoutSeconds $ServerPreflightTimeoutSeconds
            if (-not $ready) {
                Write-Warning ("Cycle {0} attempt {1}: llama-server preflight failed before launch." -f $cycle, $attempt)
                $ready = Restart-LlamaServerIfConfigured -Reason ("cycle_{0}_attempt_{1}_preflight_failed" -f $cycle, $attempt) -ServerUrl $serverUrl
                if (-not $ready) {
                    $attempts += [pscustomobject]@{
                        cycle = $cycle
                        attempt = $attempt
                        status = "server_unavailable"
                        exit_code = 125
                        stdout_log = ""
                        stderr_log = ""
                        elapsed_s = 0
                        latest_release = Get-LatestReleaseDir
                    }
                    continue
                }
            }
        }

        $result = Start-ReleaseAttempt -CycleNumber $cycle -AttemptNumber $attempt
        $attempts += [pscustomobject]@{
            cycle = $cycle
            attempt = $attempt
            status = $result.status
            exit_code = $result.exit_code
            stdout_log = $result.stdout_log
            stderr_log = $result.stderr_log
            elapsed_s = $result.elapsed_s
            latest_release = $result.latest_release
        }

        if ($result.status -eq "pass") {
            $cycleStatus = "PASS"
            break
        }

        if ($attempt -lt $MaxAttempts) {
            Write-Warning ("Cycle {0} attempt {1} failed ({2}); preparing retry..." -f $cycle, $attempt, $result.status)
            if ($usesServerAdapter) {
                $null = Restart-LlamaServerIfConfigured -Reason ("cycle_{0}_attempt_{1}_{2}" -f $cycle, $attempt, $result.status) -ServerUrl $serverUrl
            }
        }
    }

    $cycleResults += [pscustomobject]@{
        cycle = $cycle
        status = $cycleStatus
        selected_holdouts = [ordered]@{
            drift = $selectedDriftHoldout
            bad_actor = $selectedBadActorHoldout
        }
        attempts = $attempts
        latest_release = Get-LatestReleaseDir
    }

    if ($cycleStatus -ne "PASS") {
        $allCyclesPass = $false
        break
    }

    $cycle += 1
    if ($RunHours -le 0 -and $cycle -gt $Cycles) {
        break
    }
    if ($RunHours -gt 0 -and (Get-Date) -ge $deadline) {
        break
    }
    if ($SleepBetweenCyclesSeconds -gt 0) {
        Start-Sleep -Seconds $SleepBetweenCyclesSeconds
    }
}

$finalStatus = if ($allCyclesPass -and $cycleResults.Count -gt 0) { "PASS" } else { "FAIL" }
$latestRelease = Get-LatestReleaseDir
$summary = [ordered]@{
    benchmark = "release_overnight"
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    status = $finalStatus
    out_dir = (Resolve-Path $overnightDir).Path
    gate_adapter = $GateAdapter
    model_path = $ModelPath
    mode = if ($RunHours -gt 0) { "run_hours" } else { "cycles" }
    cycles_requested = $Cycles
    run_hours_requested = $RunHours
    cycles_completed = $cycleResults.Count
    run_drift_holdout_gate = $RunDriftHoldoutGate
    skip_require_control_families = $SkipRequireControlFamilies
    latest_release = $latestRelease
    cycles = $cycleResults
}

$summaryPath = "runs\\release_overnight_latest.json"
Write-JsonObject -Path $summaryPath -Object $summary
.\scripts\set_latest_pointer.ps1 -RunDir $summaryPath -PointerPath "runs\\latest_release_overnight" | Out-Host
Write-Host "Overnight summary: $summaryPath"

if ($finalStatus -ne "PASS") {
    Write-Error "Overnight release run failed."
    exit 1
}

Write-Host "Overnight release run passed."
