param(
    [int]$MaxRounds = 10,
    [int]$Seeds = 10,
    [string]$StartHoldout = "local_optimum_blocking_modal_required",
    [int]$FuzzVariants = 5,
    [int]$FuzzSeed = 0,
    [double]$GapMin = 0.1,
    [double]$SolvedMin = 0.9,
    [string]$OutRootBase = "runs",
    [string]$StatePath = "runs\\release_gates\\ui_holdout_autocurriculum.json",
    [int]$SleepSeconds = 0
)

function Get-NextHoldoutFromReport {
    param(
        [object]$Report,
        [double]$GapMin,
        [double]$SolvedMin,
        [string]$FallbackHoldout
    )
    $result = [ordered]@{
        holdout = $FallbackHoldout
        reason = "fallback"
        exhausted = $false
    }
    if (-not $Report) {
        return $result
    }
    $holdout = $Report.holdout
    $holdoutName = $holdout.name
    $holdoutSolved = $false
    $holdoutGap = 0.0
    if ($holdout) {
        $holdoutGap = [double]($holdout.sa_beats_greedy_rate)
        $holdoutSolved = (
            [double]($holdout.policy_task_pass_rate_min) -ge $SolvedMin -and
            [double]($holdout.greedy_task_pass_rate_min) -ge $SolvedMin
        )
    }
    if (-not $holdoutSolved -or $holdoutGap -ge $GapMin) {
        $result.holdout = $holdoutName
        $result.reason = "holdout_unsolved"
        return $result
    }
    $candidates = @()
    $variantBreakdown = $Report.variant_breakdown
    if ($variantBreakdown) {
        foreach ($prop in $variantBreakdown.PSObject.Properties) {
            $name = $prop.Name
            $data = $prop.Value
            if ($data.excluded_from_distillation -eq $true) {
                continue
            }
            $gap = [double]($data.sa_beats_greedy_rate)
            if ($gap -lt $GapMin) {
                continue
            }
            $candidates += [pscustomobject]@{
                name = $name
                gap = $gap
                greedy_min = [double]($data.greedy_task_pass_rate_min)
                policy_min = [double]($data.policy_task_pass_rate_min)
            }
        }
    }
    if ($candidates.Count -gt 0) {
        $pick = $candidates | Sort-Object `
            @{ Expression = "gap"; Descending = $true }, `
            @{ Expression = "greedy_min"; Descending = $false }, `
            @{ Expression = "policy_min"; Descending = $false } | Select-Object -First 1
        $result.holdout = $pick.name
        $result.reason = "gap_candidate"
        return $result
    }
    $result.holdout = $holdoutName
    $result.reason = "curriculum_exhausted"
    $result.exhausted = $true
    return $result
}

if ($MaxRounds -lt 1) {
    Write-Error "MaxRounds must be >= 1."
    exit 1
}

$resolvedHoldout = $StartHoldout
for ($round = 1; $round -le $MaxRounds; $round++) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $outRoot = Join-Path $OutRootBase ("ui_local_optimum_variants_{0}" -f $stamp)
    Write-Host ("Round {0}/{1}: holdout {2}" -f $round, $MaxRounds, $resolvedHoldout)

    .\scripts\run_ui_local_optimum_variants.ps1 `
        -OutRoot $outRoot `
        -Seeds $Seeds `
        -HoldoutName $resolvedHoldout `
        -FuzzVariants $FuzzVariants `
        -FuzzSeed $FuzzSeed

    $distillationPath = Join-Path $outRoot "distillation_report.json"
    if (-not (Test-Path $distillationPath)) {
        Write-Error "Missing distillation report at $distillationPath"
        exit 1
    }
    $releaseDir = "runs\\release_gates"
    New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
    Copy-Item -Path $distillationPath -Destination (Join-Path $releaseDir "ui_local_optimum_distillation.json") -Force

    $report = Get-Content $distillationPath -Raw | ConvertFrom-Json
    $choice = Get-NextHoldoutFromReport -Report $report -GapMin $GapMin -SolvedMin $SolvedMin -FallbackHoldout $resolvedHoldout
    New-Item -ItemType Directory -Path (Split-Path $StatePath) -Force | Out-Null
    [pscustomobject]@{
        used_holdout = $resolvedHoldout
        next_holdout = $choice.holdout
        reason = $choice.reason
        exhausted = $choice.exhausted
        gap_min = $GapMin
        solved_min = $SolvedMin
        source_report = $distillationPath
        updated_at = (Get-Date -Format "s")
    } | ConvertTo-Json -Depth 5 | Set-Content -Path $StatePath -Encoding UTF8

    if ($choice.exhausted) {
        Write-Host "AutoCurriculum: no oracle gap found in current report (curriculum exhausted)."
        break
    }

    $resolvedHoldout = $choice.holdout
    Write-Host ("AutoCurriculum next holdout: {0} ({1})" -f $resolvedHoldout, $choice.reason)
    if ($SleepSeconds -gt 0) {
        Start-Sleep -Seconds $SleepSeconds
    }
}
