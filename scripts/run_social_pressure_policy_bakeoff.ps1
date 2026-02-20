param(
    [string]$OutRoot = "",
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL,
    [string]$Adapter = "goldevidencebench.adapters.llama_server_adapter:create_adapter",
    [string]$Protocol = "closed_book",
    [int]$MaxSupportK = 16,
    [ValidateSet("observe", "ramp", "target", "custom")]
    [string]$Stage = "observe",
    [string[]]$Policies = @("baseline", "eval_reframe", "evidence_gate", "self_consistency", "goal_lock"),
    [string[]]$PromptModes = @("answer_only"),
    [ValidateSet("off", "heuristic")]
    [string[]]$GuardModes = @("off"),
    [ValidateSet("off", "heuristic")]
    [string]$GuardMode = "",
    [int]$FatigueTurns = 4,
    [switch]$OverwriteFixtures,
    [switch]$FailOnCanaryWarn
)

$ErrorActionPreference = "Stop"

function Read-JsonFile {
    param([string]$Path)
    return (Get-Content -Raw -Path $Path | ConvertFrom-Json)
}

function Metric-Value {
    param(
        [object]$Obj,
        [string]$Metric
    )
    if ($null -eq $Obj) {
        return $null
    }
    if ($null -eq $Obj.holdout) {
        return $null
    }
    if ($null -eq $Obj.holdout.means) {
        return $null
    }
    return $Obj.holdout.means.$Metric
}

function To-MinMetric {
    param([object]$Value)
    if ($null -eq $Value) {
        return [double]::PositiveInfinity
    }
    return [double]$Value
}

function To-MaxMetric {
    param([object]$Value)
    if ($null -eq $Value) {
        return [double]::NegativeInfinity
    }
    return [double]$Value
}

function Test-Dominates {
    param(
        [object]$A,
        [object]$B
    )
    $aGoal = To-MinMetric $A.holdout_suggestion_hijacking_goal_drift_rate
    $aInstr = To-MinMetric $A.holdout_suggestion_hijacking_instruction_violation_rate
    $aCap = To-MinMetric $A.holdout_capitulation_rate
    $aResp = To-MaxMetric $A.holdout_responsiveness_rate

    $bGoal = To-MinMetric $B.holdout_suggestion_hijacking_goal_drift_rate
    $bInstr = To-MinMetric $B.holdout_suggestion_hijacking_instruction_violation_rate
    $bCap = To-MinMetric $B.holdout_capitulation_rate
    $bResp = To-MaxMetric $B.holdout_responsiveness_rate

    $betterOrEqual = ($aGoal -le $bGoal) -and ($aInstr -le $bInstr) -and ($aCap -le $bCap) -and ($aResp -ge $bResp)
    if (-not $betterOrEqual) {
        return $false
    }
    return ($aGoal -lt $bGoal) -or ($aInstr -lt $bInstr) -or ($aCap -lt $bCap) -or ($aResp -gt $bResp)
}

if (-not $OutRoot) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutRoot = "runs\social_pressure_policy_bakeoff_$stamp"
}

if ($ModelPath) {
    $env:GOLDEVIDENCEBENCH_MODEL = $ModelPath
}

if (-not [string]::IsNullOrWhiteSpace($GuardMode)) {
    $GuardModes = @($GuardMode)
}

New-Item -ItemType Directory -Path $OutRoot -Force | Out-Null

Write-Host "social pressure policy bakeoff"
Write-Host "OutRoot: $OutRoot"
Write-Host "Adapter: $Adapter"
Write-Host "Protocol: $Protocol"
Write-Host "Stage: $Stage"
Write-Host "Policies: $($Policies -join ', ')"
Write-Host "PromptModes: $($PromptModes -join ', ')"
Write-Host "GuardModes: $($GuardModes -join ', ')"

$runs = New-Object System.Collections.Generic.List[object]
$firstRun = $true

foreach ($policy in $Policies) {
    foreach ($promptMode in $PromptModes) {
        foreach ($guardMode in $GuardModes) {
            $safePolicy = ($policy -replace "[^A-Za-z0-9_]", "_")
            $safeMode = ($promptMode -replace "[^A-Za-z0-9_]", "_")
            $safeGuard = ($guardMode -replace "[^A-Za-z0-9_]", "_")
            $runName = "policy_${safePolicy}__mode_${safeMode}__guard_${safeGuard}"
            $runDir = Join-Path $OutRoot $runName

            $runArgs = @{
                OutRoot = $runDir
                Adapter = $Adapter
                Protocol = $Protocol
                MaxSupportK = $MaxSupportK
                Stage = $Stage
                Policy = $policy
                PromptMode = $promptMode
                GuardMode = $guardMode
                FatigueTurns = $FatigueTurns
                FailOnCanaryWarn = [bool]$FailOnCanaryWarn
            }
            if ($ModelPath) {
                $runArgs.ModelPath = $ModelPath
            }
            if ($OverwriteFixtures -and $firstRun) {
                $runArgs.OverwriteFixtures = $true
            }

            & .\scripts\run_social_pressure_self_doubt_family.ps1 @runArgs
            $exitCode = $LASTEXITCODE

            $summaryPath = Join-Path $runDir "social_pressure_self_doubt_summary.json"
            $summaryObj = $null
            if (Test-Path $summaryPath) {
                $summaryObj = Read-JsonFile -Path $summaryPath
            }

            $runs.Add([pscustomobject]@{
                run_name = $runName
                run_dir = $runDir
                policy = $policy
                prompt_mode = $promptMode
                guard_mode = $guardMode
                exit_code = $exitCode
                summary_path = $summaryPath
                summary_found = (Test-Path $summaryPath)
                hard_gate_status = if ($summaryObj) { $summaryObj.hard_gate_status } else { "MISSING" }
                holdout_value_acc = Metric-Value -Obj $summaryObj -Metric "value_acc"
                holdout_capitulation_rate = Metric-Value -Obj $summaryObj -Metric "capitulation_rate"
                holdout_responsiveness_rate = Metric-Value -Obj $summaryObj -Metric "responsiveness_rate"
                holdout_suggestion_hijacking_goal_drift_rate = Metric-Value -Obj $summaryObj -Metric "suggestion_hijacking_goal_drift_rate"
                holdout_suggestion_hijacking_instruction_violation_rate = Metric-Value -Obj $summaryObj -Metric "suggestion_hijacking_instruction_violation_rate"
                holdout_emotional_capitulation_rate = Metric-Value -Obj $summaryObj -Metric "emotional_capitulation_rate"
                holdout_fatigue_degradation = Metric-Value -Obj $summaryObj -Metric "fatigue_degradation"
            })

            $firstRun = $false
        }
    }
}

$comparison = foreach ($row in $runs) {
    $baseline = $runs | Where-Object {
        $_.policy -eq "baseline" -and $_.prompt_mode -eq $row.prompt_mode -and $_.guard_mode -eq $row.guard_mode
    } | Select-Object -First 1
    if ($null -eq $baseline) {
        $baseline = $runs | Where-Object { $_.policy -eq "baseline" } | Select-Object -First 1
    }
    if ($null -eq $baseline) {
        $baseline = $runs | Select-Object -First 1
    }
    [pscustomobject]@{
        run_name = $row.run_name
        run_dir = $row.run_dir
        policy = $row.policy
        prompt_mode = $row.prompt_mode
        guard_mode = $row.guard_mode
        exit_code = $row.exit_code
        hard_gate_status = $row.hard_gate_status
        holdout_value_acc = $row.holdout_value_acc
        holdout_capitulation_rate = $row.holdout_capitulation_rate
        holdout_responsiveness_rate = $row.holdout_responsiveness_rate
        holdout_suggestion_hijacking_goal_drift_rate = $row.holdout_suggestion_hijacking_goal_drift_rate
        holdout_suggestion_hijacking_instruction_violation_rate = $row.holdout_suggestion_hijacking_instruction_violation_rate
        holdout_emotional_capitulation_rate = $row.holdout_emotional_capitulation_rate
        holdout_fatigue_degradation = $row.holdout_fatigue_degradation
        delta_value_acc = if ($null -ne $row.holdout_value_acc -and $null -ne $baseline.holdout_value_acc) { [double]$row.holdout_value_acc - [double]$baseline.holdout_value_acc } else { $null }
        delta_capitulation_rate = if ($null -ne $row.holdout_capitulation_rate -and $null -ne $baseline.holdout_capitulation_rate) { [double]$row.holdout_capitulation_rate - [double]$baseline.holdout_capitulation_rate } else { $null }
        delta_responsiveness_rate = if ($null -ne $row.holdout_responsiveness_rate -and $null -ne $baseline.holdout_responsiveness_rate) { [double]$row.holdout_responsiveness_rate - [double]$baseline.holdout_responsiveness_rate } else { $null }
        delta_suggestion_hijacking_goal_drift_rate = if ($null -ne $row.holdout_suggestion_hijacking_goal_drift_rate -and $null -ne $baseline.holdout_suggestion_hijacking_goal_drift_rate) { [double]$row.holdout_suggestion_hijacking_goal_drift_rate - [double]$baseline.holdout_suggestion_hijacking_goal_drift_rate } else { $null }
        delta_suggestion_hijacking_instruction_violation_rate = if ($null -ne $row.holdout_suggestion_hijacking_instruction_violation_rate -and $null -ne $baseline.holdout_suggestion_hijacking_instruction_violation_rate) { [double]$row.holdout_suggestion_hijacking_instruction_violation_rate - [double]$baseline.holdout_suggestion_hijacking_instruction_violation_rate } else { $null }
        delta_emotional_capitulation_rate = if ($null -ne $row.holdout_emotional_capitulation_rate -and $null -ne $baseline.holdout_emotional_capitulation_rate) { [double]$row.holdout_emotional_capitulation_rate - [double]$baseline.holdout_emotional_capitulation_rate } else { $null }
        delta_fatigue_degradation = if ($null -ne $row.holdout_fatigue_degradation -and $null -ne $baseline.holdout_fatigue_degradation) { [double]$row.holdout_fatigue_degradation - [double]$baseline.holdout_fatigue_degradation } else { $null }
    }
}

$sortedComparison = @($comparison | Sort-Object `
    prompt_mode, guard_mode, `
    @{ Expression = { To-MinMetric $_.holdout_suggestion_hijacking_goal_drift_rate }; Ascending = $true }, `
    @{ Expression = { To-MinMetric $_.holdout_suggestion_hijacking_instruction_violation_rate }; Ascending = $true }, `
    @{ Expression = { To-MinMetric $_.holdout_capitulation_rate }; Ascending = $true }, `
    @{ Expression = { -1.0 * (To-MaxMetric $_.holdout_responsiveness_rate) }; Ascending = $true }, `
    policy)

$paretoByKey = @{}
$grouped = $sortedComparison | Group-Object prompt_mode, guard_mode
foreach ($group in $grouped) {
    $rows = @($group.Group)
    for ($i = 0; $i -lt $rows.Count; $i++) {
        $candidate = $rows[$i]
        $dominated = $false
        for ($j = 0; $j -lt $rows.Count; $j++) {
            if ($i -eq $j) {
                continue
            }
            if (Test-Dominates -A $rows[$j] -B $candidate) {
                $dominated = $true
                break
            }
        }
        $paretoByKey[$candidate.run_name] = (-not $dominated)
    }
}

$comparisonWithPareto = foreach ($row in $sortedComparison) {
    [pscustomobject]@{
        run_name = $row.run_name
        run_dir = $row.run_dir
        policy = $row.policy
        prompt_mode = $row.prompt_mode
        guard_mode = $row.guard_mode
        exit_code = $row.exit_code
        hard_gate_status = $row.hard_gate_status
        holdout_value_acc = $row.holdout_value_acc
        holdout_capitulation_rate = $row.holdout_capitulation_rate
        holdout_responsiveness_rate = $row.holdout_responsiveness_rate
        holdout_suggestion_hijacking_goal_drift_rate = $row.holdout_suggestion_hijacking_goal_drift_rate
        holdout_suggestion_hijacking_instruction_violation_rate = $row.holdout_suggestion_hijacking_instruction_violation_rate
        holdout_emotional_capitulation_rate = $row.holdout_emotional_capitulation_rate
        holdout_fatigue_degradation = $row.holdout_fatigue_degradation
        delta_value_acc = $row.delta_value_acc
        delta_capitulation_rate = $row.delta_capitulation_rate
        delta_responsiveness_rate = $row.delta_responsiveness_rate
        delta_suggestion_hijacking_goal_drift_rate = $row.delta_suggestion_hijacking_goal_drift_rate
        delta_suggestion_hijacking_instruction_violation_rate = $row.delta_suggestion_hijacking_instruction_violation_rate
        delta_emotional_capitulation_rate = $row.delta_emotional_capitulation_rate
        delta_fatigue_degradation = $row.delta_fatigue_degradation
        pareto_frontier = [bool]$paretoByKey[$row.run_name]
    }
}

$baselineReference = $comparisonWithPareto | Where-Object {
    $_.policy -eq "baseline" -and $_.prompt_mode -eq "answer_only" -and $_.guard_mode -eq "off"
} | Select-Object -First 1
if ($null -eq $baselineReference) {
    $baselineReference = $comparisonWithPareto | Where-Object { $_.policy -eq "baseline" } | Select-Object -First 1
}
if ($null -eq $baselineReference) {
    $baselineReference = $comparisonWithPareto | Select-Object -First 1
}

$paretoFrontier = @($comparisonWithPareto | Where-Object { $_.pareto_frontier -eq $true })

$summary = [ordered]@{
    benchmark = "social_pressure_policy_bakeoff"
    generated_at = (Get-Date).ToString("o")
    out_root = (Resolve-Path $OutRoot).Path
    stage = $Stage
    adapter = $Adapter
    protocol = $Protocol
    guard_modes = $GuardModes
    ranking_rule = "sort by hijack_goal_drift asc, hijack_instruction_violation asc, capitulation asc, responsiveness desc"
    pareto_objectives = [ordered]@{
        minimize = @(
            "holdout_suggestion_hijacking_goal_drift_rate",
            "holdout_suggestion_hijacking_instruction_violation_rate",
            "holdout_capitulation_rate"
        )
        maximize = @("holdout_responsiveness_rate")
    }
    baseline_reference = [ordered]@{
        run_name = $baselineReference.run_name
        policy = $baselineReference.policy
        prompt_mode = $baselineReference.prompt_mode
        guard_mode = $baselineReference.guard_mode
    }
    comparisons = $comparisonWithPareto
    pareto_frontier = $paretoFrontier
}

$summaryPath = Join-Path $OutRoot "social_pressure_policy_bakeoff_summary.json"
$summary | ConvertTo-Json -Depth 8 | Set-Content -Path $summaryPath -Encoding UTF8
Write-Host "Wrote $summaryPath"

$mdLines = @(
    "# Social Pressure Policy Bakeoff",
    "",
    "- stage: $Stage",
    "- adapter: $Adapter",
    "- protocol: $Protocol",
    "- guard_modes: $($GuardModes -join ', ')",
    "- baseline reference: $($baselineReference.run_name)",
    "",
    "| policy | prompt_mode | guard_mode | pareto_frontier | hard_gate_status | value_acc | capitulation_rate | responsiveness_rate | hijack_goal_drift | hijack_instruction_violation | emotional_capitulation_rate | fatigue_degradation |",
    "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
)
foreach ($row in $comparisonWithPareto) {
    $mdLines += "| $($row.policy) | $($row.prompt_mode) | $($row.guard_mode) | $($row.pareto_frontier) | $($row.hard_gate_status) | $($row.holdout_value_acc) | $($row.holdout_capitulation_rate) | $($row.holdout_responsiveness_rate) | $($row.holdout_suggestion_hijacking_goal_drift_rate) | $($row.holdout_suggestion_hijacking_instruction_violation_rate) | $($row.holdout_emotional_capitulation_rate) | $($row.holdout_fatigue_degradation) |"
}

$mdLines += ""
$mdLines += "## Frontier By Prompt/Guard"
foreach ($group in ($comparisonWithPareto | Group-Object prompt_mode, guard_mode)) {
    $items = @($group.Group | Where-Object { $_.pareto_frontier -eq $true })
    $mdLines += ""
    $mdLines += "### $($group.Name)"
    if ($items.Count -eq 0) {
        $mdLines += "- none"
        continue
    }
    foreach ($item in $items) {
        $mdLines += "- $($item.policy): hijack_goal_drift=$($item.holdout_suggestion_hijacking_goal_drift_rate), hijack_instruction_violation=$($item.holdout_suggestion_hijacking_instruction_violation_rate), capitulation=$($item.holdout_capitulation_rate), responsiveness=$($item.holdout_responsiveness_rate)"
    }
}
$mdPath = Join-Path $OutRoot "social_pressure_policy_bakeoff_summary.md"
$mdLines -join "`n" | Set-Content -Path $mdPath -Encoding UTF8
Write-Host "Wrote $mdPath"

$failedRuns = @($runs | Where-Object { $_.exit_code -ne 0 })
if ($failedRuns.Count -gt 0) {
    Write-Warning "$($failedRuns.Count) bakeoff runs exited non-zero."
    exit 1
}

exit 0
