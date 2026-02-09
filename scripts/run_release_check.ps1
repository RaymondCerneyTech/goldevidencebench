<#
.SYNOPSIS
Runs GoldEvidenceBench release checks and gates.

.DESCRIPTION
Executes a suite of checks (retrieval, UI stubs, local-optimum variants), runs
the bad actor holdout gate, and optionally the drift holdout gate. The UI
local-optimum distillation holdout defaults to local_optimum_blocking_modal_unmentioned_blocked.

.PARAMETER VariantsHoldoutName
Holdout for UI local-optimum distillation (default:
local_optimum_blocking_modal_unmentioned_blocked).

.PARAMETER RunDriftHoldoutGate
Runs the drift holdout canary + fixes gate and fails the release on FAIL.

.PARAMETER SkipRequireControlFamilies
Diagnostic-only override: do not require rpa_mode_switch, intent_spec_layer,
and noise_escalation in the unified reliability gate.

#>
param(
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL,
    [string]$GateAdapter = "goldevidencebench.adapters.retrieval_llama_cpp_adapter:create_adapter",
    [switch]$RunSweeps,
    [switch]$SkipThresholds,
    [switch]$SkipReliabilitySignal,
    [switch]$SkipRequireControlFamilies,
    [switch]$RunDriftHoldoutGate,
    [int]$VariantsSeeds = 10,
    [string]$VariantsHoldoutName = "local_optimum_blocking_modal_unmentioned_blocked",
    [int]$VariantsFuzzVariants = 5,
    [int]$VariantsFuzzSeed = 0,
    [switch]$RotateHoldout,
    [switch]$AutoCurriculum,
    [double]$AutoCurriculumGapMin = 0.1,
    [double]$AutoCurriculumSolvedMin = 0.9,
    [string]$AutoCurriculumStatePath = "runs\\release_gates\\ui_holdout_autocurriculum.json",
    [string]$HoldoutList = "",
    [string]$HoldoutListPath = "configs\\ui_holdout_list.json",
    [ValidateSet("stale_tab_state", "focus_drift")]
    [string]$DriftHoldoutName = "stale_tab_state",
    [string]$BadActorHoldoutId = "",
    [string]$BadActorHoldoutListPath = "configs\\bad_actor_holdout_list.json",
    [switch]$SkipVariants
)

$gateUsesServerAdapter = $GateAdapter -like "*llama_server_adapter*"
if ($ModelPath -eq "<MODEL_PATH>") {
    if ($PSBoundParameters.ContainsKey("ModelPath")) {
        Write-Error "Replace placeholder <MODEL_PATH> with a real path, or omit -ModelPath when using llama_server_adapter."
        exit 1
    }
    if ($gateUsesServerAdapter) {
        # Ignore placeholder inherited from environment for server-adapter runs.
        $ModelPath = ""
    } else {
        Write-Error "Replace placeholder <MODEL_PATH> with a real path, or set GOLDEVIDENCEBENCH_MODEL."
        exit 1
    }
}

$RequiredVariantsHoldout = "local_optimum_blocking_modal_unmentioned_blocked"
$DefaultHoldoutList = "local_optimum_section_path,local_optimum_section_path_conflict,local_optimum_blocking_modal_detour,local_optimum_tab_detour,local_optimum_disabled_primary,local_optimum_toolbar_vs_menu,local_optimum_confirm_then_apply,local_optimum_tab_state_reset,local_optimum_context_switch,local_optimum_stale_tab_state,local_optimum_form_validation,local_optimum_window_focus,local_optimum_panel_toggle,local_optimum_accessibility_label,local_optimum_checkbox_gate,local_optimum_blocking_modal_required,local_optimum_blocking_modal_permission,local_optimum_blocking_modal_consent,local_optimum_blocking_modal_unmentioned,local_optimum_blocking_modal_unmentioned_blocked,local_optimum_blocking_modal,local_optimum_overlay,local_optimum_primary,local_optimum_delayed_solvable,local_optimum_role_mismatch,local_optimum_role_conflict,local_optimum_destructive_confirm,local_optimum_unsaved_changes,local_optimum_blocking_modal_unprompted_confirm"

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$ReleaseRunDir = "runs\\release_check_$stamp"
New-Item -ItemType Directory -Path $ReleaseRunDir -Force | Out-Null

if ($RunSweeps -and -not $ModelPath) {
    Write-Error "Set -ModelPath or GOLDEVIDENCEBENCH_MODEL before running sweeps."
    exit 1
}

$manifestPath = Join-Path $ReleaseRunDir "release_manifest.json"
$releaseLogsDir = Join-Path $ReleaseRunDir "logs"
New-Item -ItemType Directory -Path $releaseLogsDir -Force | Out-Null
$manifest = [ordered]@{
    created_at = (Get-Date -Format "s")
    model_path = $ModelPath
    gate_adapter = $GateAdapter
    selected_holdouts = [ordered]@{
        drift = $DriftHoldoutName
        bad_actor = $BadActorHoldoutId
    }
    artifacts = [ordered]@{
        release_gates_dir = "runs\\release_gates"
        drift_holdout_gate = "runs\\release_gates\\drift_holdout_gate.json"
        drift_holdout_latest = "runs\\drift_holdout_latest"
        bad_actor_holdout_latest = "runs\\bad_actor_holdout_latest\\summary.json"
        ui_same_label_gate = "runs\\ui_same_label_gate.json"
        ui_popup_overlay_gate = "runs\\ui_popup_overlay_gate.json"
        ui_minipilot_notepad_gate = "runs\\ui_minipilot_notepad_gate.json"
        instruction_override_gate = "runs\\release_gates\\instruction_override_gate\\summary.json"
        memory_verify_gate = "runs\\release_gates\\memory_verify.json"
        update_burst_release_gate = "runs\\release_gates\\update_burst_full_linear_k16_bucket5_rate0.12\\summary.json"
        reliability_signal = "runs\\reliability_signal_latest.json"
        compression_reliability = "runs\\compression_reliability_latest.json"
        novel_continuity_reliability = "runs\\novel_continuity_reliability_latest.json"
        authority_under_interference_reliability = "runs\\authority_under_interference_reliability_latest.json"
        rpa_mode_switch_reliability = "runs\\rpa_mode_switch_reliability_latest.json"
        intent_spec_layer_reliability = "runs\\intent_spec_layer_reliability_latest.json"
        noise_escalation_reliability = "runs\\noise_escalation_reliability_latest.json"
    }
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -Path $manifestPath -Encoding UTF8

.\scripts\set_latest_pointer.ps1 -RunDir $ReleaseRunDir -PointerPath "runs\\latest_release" | Out-Host
Write-Host "Release manifest: $manifestPath"

if ($RunSweeps) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $stressRoot = "runs\\wall_update_burst_full_linear_bucket10_$stamp"
    $pinRoot = "runs\\wall_update_burst_full_linear_bucket10_pin_$stamp"

    Write-Host "Running stress sweep..."
    .\scripts\run_update_burst_full_linear_bucket10.ps1 `
        -ModelPath $ModelPath `
        -OutRoot $stressRoot `
        -Rates 0.205,0.209,0.22,0.24

    Write-Host "Running pin sweep..."
    .\scripts\run_update_burst_full_linear_bucket10.ps1 `
        -ModelPath $ModelPath `
        -OutRoot $pinRoot `
        -Rates 0.18,0.19,0.195,0.20 `
        -FindWall:$true

    Write-Host "Sweeps complete: $stressRoot, $pinRoot"
}

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

if (-not $SkipThresholds) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $resolvedHoldout = $VariantsHoldoutName
    if ($AutoCurriculum) {
        $prevReportPath = "runs\\release_gates\\ui_local_optimum_distillation.json"
        if (Test-Path $prevReportPath) {
            try {
                $report = Get-Content $prevReportPath -Raw | ConvertFrom-Json
                $choice = Get-NextHoldoutFromReport -Report $report -GapMin $AutoCurriculumGapMin -SolvedMin $AutoCurriculumSolvedMin -FallbackHoldout $resolvedHoldout
                if ($choice.holdout) {
                    $resolvedHoldout = $choice.holdout
                    New-Item -ItemType Directory -Path (Split-Path $AutoCurriculumStatePath) -Force | Out-Null
                    [pscustomobject]@{
                        used_holdout = $resolvedHoldout
                        reason = $choice.reason
                        exhausted = $choice.exhausted
                        gap_min = $AutoCurriculumGapMin
                        solved_min = $AutoCurriculumSolvedMin
                        source_report = $prevReportPath
                        updated_at = (Get-Date -Format "s")
                    } | ConvertTo-Json -Depth 4 | Set-Content -Path $AutoCurriculumStatePath -Encoding UTF8
                    if ($choice.exhausted) {
                        Write-Host "AutoCurriculum: no oracle gap found in previous report (curriculum exhausted)."
                    } else {
                        Write-Host ("AutoCurriculum holdout: {0} ({1})" -f $resolvedHoldout, $choice.reason)
                    }
                }
            } catch {
                Write-Host "AutoCurriculum: failed to parse prior distillation report."
            }
        } else {
            Write-Host "AutoCurriculum: no prior distillation report found; using configured holdout."
        }
    } elseif ($RotateHoldout) {
    $resolvedList = $HoldoutList
    if (-not $resolvedList) {
        if (Test-Path $HoldoutListPath) {
            try {
                $holdoutConfig = Get-Content $HoldoutListPath -Raw | ConvertFrom-Json
                if ($holdoutConfig -and $holdoutConfig.holdouts) {
                    $holdoutNames = @(
                        $holdoutConfig.holdouts | ForEach-Object { $_.ToString().Trim() } | Where-Object { $_ }
                    )
                }
            } catch {
                $holdoutNames = @()
            }
        }
    }
    if (-not $holdoutNames -or $holdoutNames.Count -eq 0) {
        if (-not $resolvedList) {
            $resolvedList = $DefaultHoldoutList
        }
        $holdoutNames = @(
            $resolvedList -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ }
        )
    }
        if (-not $holdoutNames -or $holdoutNames.Count -eq 0) {
            Write-Host "RotateHoldout ignored: HoldoutList is empty."
        } else {
            $statePath = "runs\\release_gates\\ui_holdout_rotation.json"
            $state = $null
            if (Test-Path $statePath) {
                try {
                    $state = Get-Content $statePath -Raw | ConvertFrom-Json
                } catch {
                    $state = $null
                }
            }
            $index = 0
            if ($state -and $state.index -is [int]) {
                $index = [int]$state.index
            }
            $resolvedHoldout = $holdoutNames[$index % $holdoutNames.Count]
            $nextIndex = ($index + 1) % $holdoutNames.Count
            New-Item -ItemType Directory -Path (Split-Path $statePath) -Force | Out-Null
            [pscustomobject]@{
                index = $nextIndex
                holdout = $resolvedHoldout
                updated_at = (Get-Date -Format "s")
                list = $holdoutNames
            } | ConvertTo-Json -Depth 4 | Set-Content -Path $statePath -Encoding UTF8
            Write-Host ("RotateHoldout: {0}" -f $resolvedHoldout)
        }
    }

    Write-Host "Running instruction override gate..."
    .\scripts\run_instruction_override_gate.ps1 -ModelPath $ModelPath -Adapter $GateAdapter
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Instruction override gate failed."
        exit 1
    }
    $instructionOverrideSummary = "runs\\release_gates\\instruction_override_gate\\summary.json"
    if (-not (Test-Path $instructionOverrideSummary)) {
        Write-Error "Instruction override gate did not produce summary.json."
        exit 1
    }
    if (Test-Path $instructionOverrideSummary) {
        .\scripts\set_latest_pointer.ps1 -RunDir $instructionOverrideSummary -PointerPath "runs\\latest_instruction_override_gate" | Out-Host
    }
    Write-Host "Running memory verification gate..."
    python .\scripts\verify_memories.py --in .\data\memories\memory_demo.jsonl `
        --out .\runs\release_gates\memory_verify.json `
        --out-details .\runs\release_gates\memory_verify_details.json
    $memoryVerify = "runs\\release_gates\\memory_verify.json"
    if (Test-Path $memoryVerify) {
        .\scripts\set_latest_pointer.ps1 -RunDir $memoryVerify -PointerPath "runs\\latest_memory_verify_gate" | Out-Host
    }
    Write-Host "Running UI same_label stub..."
    $uiSameLog = Join-Path $releaseLogsDir "ui_same_label_stub.log"
    .\scripts\run_ui_same_label_stub.ps1 *> $uiSameLog
    if ($LASTEXITCODE -ne 0) {
        Write-Error "UI same_label stub failed. See $uiSameLog"
        if (Test-Path $uiSameLog) { Get-Content $uiSameLog -Tail 40 | Out-Host }
        exit $LASTEXITCODE
    }
    Write-Host "UI same_label stub complete (log: $uiSameLog)"
    if (Test-Path "runs\\ui_same_label_gate.json") {
        .\scripts\set_latest_pointer.ps1 -RunDir "runs\\ui_same_label_gate.json" -PointerPath "runs\\latest_ui_same_label_gate" | Out-Host
    }
    Write-Host "Running UI popup_overlay stub..."
    $uiPopupLog = Join-Path $releaseLogsDir "ui_popup_overlay_stub.log"
    .\scripts\run_ui_popup_overlay_stub.ps1 *> $uiPopupLog
    if ($LASTEXITCODE -ne 0) {
        Write-Error "UI popup_overlay stub failed. See $uiPopupLog"
        if (Test-Path $uiPopupLog) { Get-Content $uiPopupLog -Tail 40 | Out-Host }
        exit $LASTEXITCODE
    }
    Write-Host "UI popup_overlay stub complete (log: $uiPopupLog)"
    if (Test-Path "runs\\ui_popup_overlay_gate.json") {
        .\scripts\set_latest_pointer.ps1 -RunDir "runs\\ui_popup_overlay_gate.json" -PointerPath "runs\\latest_ui_popup_overlay_gate" | Out-Host
    }
    Write-Host "Running UI minipilot notepad stub..."
    $uiNotepadLog = Join-Path $releaseLogsDir "ui_minipilot_notepad_stub.log"
    .\scripts\run_ui_minipilot_notepad_stub.ps1 *> $uiNotepadLog
    if ($LASTEXITCODE -ne 0) {
        Write-Error "UI minipilot notepad stub failed. See $uiNotepadLog"
        if (Test-Path $uiNotepadLog) { Get-Content $uiNotepadLog -Tail 40 | Out-Host }
        exit $LASTEXITCODE
    }
    Write-Host "UI minipilot notepad stub complete (log: $uiNotepadLog)"
    if (Test-Path "runs\\ui_minipilot_notepad_gate.json") {
        .\scripts\set_latest_pointer.ps1 -RunDir "runs\\ui_minipilot_notepad_gate.json" -PointerPath "runs\\latest_ui_minipilot_notepad_gate" | Out-Host
    }
    Write-Host "Validating demo presets..."
    $demoConfigPath = "configs\\demo_presets.json"
    if (Test-Path $demoConfigPath) {
        $demoConfig = Get-Content $demoConfigPath -Raw | ConvertFrom-Json
        $presetMap = @{}
        foreach ($preset in $demoConfig.presets) {
            if ($preset.name) {
                $presetMap[$preset.name.ToLowerInvariant()] = $preset
            }
        }
        function Test-PresetArgs {
            param(
                [string]$Name,
                [string[]]$Required
            )
            if (-not $presetMap.ContainsKey($Name.ToLowerInvariant())) {
                Write-Error "Missing preset: $Name"
                return $false
            }
            $argsLower = @()
            foreach ($arg in $presetMap[$Name.ToLowerInvariant()].args) {
                $argsLower += $arg.ToString().ToLowerInvariant()
            }
            foreach ($req in $Required) {
                if (-not ($argsLower -contains $req.ToLowerInvariant())) {
                    Write-Error "Preset '$Name' missing required arg: $req"
                    return $false
                }
            }
            return $true
        }
        $demoOk = $true
        $demoOk = (Test-PresetArgs -Name "notepad" -Required @("-Text","-FilePath","-OnExistingFile","-InputMode","-VerifySaved","-CloseAfterSave")) -and $demoOk
        $demoOk = (Test-PresetArgs -Name "form" -Required @("-Username","-Password","-OutputPath","-VerifySaved","-CloseAfterSave")) -and $demoOk
        $demoOk = (Test-PresetArgs -Name "calculator" -Required @("-Expression","-Expected","-VerifyResult","-CloseAfter")) -and $demoOk
        $demoOk = (Test-PresetArgs -Name "notepad_calc" -Required @("-Text","-FilePath","-Expression","-Expected")) -and $demoOk
        if (-not $demoOk) {
            Write-Error "Demo preset validation failed."
            exit 1
        }
    } else {
        Write-Warning "Demo presets config not found; skipping demo preset validation."
    }
    if ($ModelPath) {
        Write-Host "Running demo dry-runs (live presets)..."
        .\scripts\run_demo.ps1 -ModelPath $ModelPath -Preset notepad -DryRun
        if ($LASTEXITCODE -ne 0) { Write-Error "Demo dry-run failed: notepad"; exit 1 }
        .\scripts\run_demo.ps1 -ModelPath $ModelPath -Preset form -DryRun
        if ($LASTEXITCODE -ne 0) { Write-Error "Demo dry-run failed: form"; exit 1 }
        .\scripts\run_demo.ps1 -ModelPath $ModelPath -Preset calculator -DryRun
        if ($LASTEXITCODE -ne 0) { Write-Error "Demo dry-run failed: calculator"; exit 1 }
    } else {
        Write-Host "Skipping demo dry-runs: ModelPath not set."
    }
    Write-Host "Running UI minipilot notepad baseline (step overhead)..."
    python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_notepad_fixture.jsonl `
        --observed .\data\ui_minipilot_notepad_observed_ok.jsonl `
        --out .\runs\ui_minipilot_notepad_search.json
    Write-Host "Running UI minipilot form baseline (step overhead)..."
    python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_form_fixture.jsonl `
        --observed .\data\ui_minipilot_form_observed_ok.jsonl `
        --out .\runs\ui_minipilot_form_search.json
    Write-Host "Running UI minipilot table baseline (step overhead)..."
    python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_table_fixture.jsonl `
        --observed .\data\ui_minipilot_table_observed_ok.jsonl `
        --out .\runs\ui_minipilot_table_search.json
    Write-Host "Running UI minipilot notepad ambiguous baseline..."
    python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_notepad_ambiguous_fixture.jsonl `
        --observed .\data\ui_minipilot_notepad_ambiguous_observed_ok.jsonl `
        --out .\runs\ui_minipilot_notepad_ambiguous_search.json
    Write-Host "Running UI minipilot notepad wrong-directory detour baseline..."
    python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_notepad_wrong_directory_detour_fixture.jsonl `
        --observed .\data\ui_minipilot_notepad_wrong_directory_detour_observed_ok.jsonl `
        --out .\runs\ui_minipilot_notepad_wrong_directory_detour_search.json
    Write-Host "Running UI local-optimum baseline (SA discriminator)..."
    python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_fixture.jsonl `
        --observed .\data\ui_minipilot_local_optimum_observed_ok.jsonl --out .\runs\ui_minipilot_local_optimum_search.json --seeds 10

    Write-Host "Running UI local-optimum delayed ambiguous baseline..."
    python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_delayed_ambiguous_fixture.jsonl `
        --observed .\data\ui_minipilot_local_optimum_delayed_ambiguous_observed_ok.jsonl `
        --out .\runs\ui_minipilot_local_optimum_delayed_ambiguous_search.json
    Write-Host "Running UI local-optimum blocking modal unmentioned ambiguous baseline..."
    python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_blocking_modal_unmentioned_ambiguous_fixture.jsonl `
        --observed .\data\ui_minipilot_local_optimum_blocking_modal_unmentioned_ambiguous_observed_ok.jsonl `
        --out .\runs\ui_minipilot_local_optimum_blocking_modal_unmentioned_ambiguous_search.json
    Write-Host "Running UI local-optimum blocking modal unmentioned blocked ambiguous baseline..."
    python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_blocking_modal_unmentioned_blocked_ambiguous_fixture.jsonl `
        --observed .\data\ui_minipilot_local_optimum_blocking_modal_unmentioned_blocked_ambiguous_observed_ok.jsonl `
        --out .\runs\ui_minipilot_local_optimum_blocking_modal_unmentioned_blocked_ambiguous_search.json
    Write-Host "Running UI local-optimum blocking modal required ambiguous baseline..."
    python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_blocking_modal_required_ambiguous_fixture.jsonl `
        --observed .\data\ui_minipilot_local_optimum_blocking_modal_required_ambiguous_observed_ok.jsonl `
        --out .\runs\ui_minipilot_local_optimum_blocking_modal_required_ambiguous_search.json
    Write-Host "Running UI local-optimum blocking modal permission ambiguous baseline..."
    python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_blocking_modal_permission_ambiguous_fixture.jsonl `
        --observed .\data\ui_minipilot_local_optimum_blocking_modal_permission_ambiguous_observed_ok.jsonl `
        --out .\runs\ui_minipilot_local_optimum_blocking_modal_permission_ambiguous_search.json
    Write-Host "Running UI local-optimum blocking modal consent ambiguous baseline..."
    python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_blocking_modal_consent_ambiguous_fixture.jsonl `
        --observed .\data\ui_minipilot_local_optimum_blocking_modal_consent_ambiguous_observed_ok.jsonl `
        --out .\runs\ui_minipilot_local_optimum_blocking_modal_consent_ambiguous_search.json
    Write-Host "Running UI local-optimum disabled primary ambiguous baseline..."
    python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_disabled_primary_ambiguous_fixture.jsonl `
        --observed .\data\ui_minipilot_local_optimum_disabled_primary_ambiguous_observed_ok.jsonl `
        --out .\runs\ui_minipilot_local_optimum_disabled_primary_ambiguous_search.json
    Write-Host "Running UI local-optimum toolbar vs menu ambiguous baseline..."
    python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_toolbar_vs_menu_ambiguous_fixture.jsonl `
        --observed .\data\ui_minipilot_local_optimum_toolbar_vs_menu_ambiguous_observed_ok.jsonl `
        --out .\runs\ui_minipilot_local_optimum_toolbar_vs_menu_ambiguous_search.json
    Write-Host "Running UI local-optimum confirm then apply ambiguous baseline..."
    python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_confirm_then_apply_ambiguous_fixture.jsonl `
        --observed .\data\ui_minipilot_local_optimum_confirm_then_apply_ambiguous_observed_ok.jsonl `
        --out .\runs\ui_minipilot_local_optimum_confirm_then_apply_ambiguous_search.json
    Write-Host "Running UI local-optimum tab state reset ambiguous baseline..."
    python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_tab_state_reset_ambiguous_fixture.jsonl `
        --observed .\data\ui_minipilot_local_optimum_tab_state_reset_ambiguous_observed_ok.jsonl `
        --out .\runs\ui_minipilot_local_optimum_tab_state_reset_ambiguous_search.json
    Write-Host "Running UI local-optimum context switch ambiguous baseline..."
    python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_context_switch_ambiguous_fixture.jsonl `
        --observed .\data\ui_minipilot_local_optimum_context_switch_ambiguous_observed_ok.jsonl `
        --out .\runs\ui_minipilot_local_optimum_context_switch_ambiguous_search.json
    Write-Host "Running UI local-optimum stale tab state ambiguous baseline..."
    python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_stale_tab_state_ambiguous_fixture.jsonl `
        --observed .\data\ui_minipilot_local_optimum_stale_tab_state_ambiguous_observed_ok.jsonl `
        --out .\runs\ui_minipilot_local_optimum_stale_tab_state_ambiguous_search.json
    Write-Host "Running UI local-optimum form validation ambiguous baseline..."
    python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_form_validation_ambiguous_fixture.jsonl `
        --observed .\data\ui_minipilot_local_optimum_form_validation_ambiguous_observed_ok.jsonl `
        --out .\runs\ui_minipilot_local_optimum_form_validation_ambiguous_search.json
    Write-Host "Running UI local-optimum window focus ambiguous baseline..."
    python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_window_focus_ambiguous_fixture.jsonl `
        --observed .\data\ui_minipilot_local_optimum_window_focus_ambiguous_observed_ok.jsonl `
        --out .\runs\ui_minipilot_local_optimum_window_focus_ambiguous_search.json
    Write-Host "Running UI local-optimum checkbox gate ambiguous baseline..."
    python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_checkbox_gate_ambiguous_fixture.jsonl `
        --observed .\data\ui_minipilot_local_optimum_checkbox_gate_ambiguous_observed_ok.jsonl `
        --out .\runs\ui_minipilot_local_optimum_checkbox_gate_ambiguous_search.json
    Write-Host "Running UI local-optimum panel toggle ambiguous baseline..."
    python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_panel_toggle_ambiguous_fixture.jsonl `
        --observed .\data\ui_minipilot_local_optimum_panel_toggle_ambiguous_observed_ok.jsonl `
        --out .\runs\ui_minipilot_local_optimum_panel_toggle_ambiguous_search.json
    Write-Host "Running UI local-optimum accessibility label ambiguous baseline..."
    python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_accessibility_label_ambiguous_fixture.jsonl `
        --observed .\data\ui_minipilot_local_optimum_accessibility_label_ambiguous_observed_ok.jsonl `
        --out .\runs\ui_minipilot_local_optimum_accessibility_label_ambiguous_search.json
    Write-Host "Running UI local-optimum section path ambiguous baseline..."
    python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_section_path_ambiguous_fixture.jsonl `
        --observed .\data\ui_minipilot_local_optimum_section_path_ambiguous_observed_ok.jsonl `
        --out .\runs\ui_minipilot_local_optimum_section_path_ambiguous_search.json
    Write-Host "Running UI local-optimum section path conflict ambiguous baseline..."
    python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_section_path_conflict_ambiguous_fixture.jsonl `
        --observed .\data\ui_minipilot_local_optimum_section_path_conflict_ambiguous_observed_ok.jsonl `
        --out .\runs\ui_minipilot_local_optimum_section_path_conflict_ambiguous_search.json
    python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_blocking_modal_unprompted_confirm_ambiguous_fixture.jsonl `
        --observed .\data\ui_minipilot_local_optimum_blocking_modal_unprompted_confirm_ambiguous_observed_ok.jsonl `
        --out .\runs\ui_minipilot_local_optimum_blocking_modal_unprompted_confirm_ambiguous_search.json
    python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_destructive_confirm_ambiguous_fixture.jsonl `
        --observed .\data\ui_minipilot_local_optimum_destructive_confirm_ambiguous_observed_ok.jsonl `
        --out .\runs\ui_minipilot_local_optimum_destructive_confirm_ambiguous_search.json
    python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_role_conflict_ambiguous_fixture.jsonl `
        --observed .\data\ui_minipilot_local_optimum_role_conflict_ambiguous_observed_ok.jsonl `
        --out .\runs\ui_minipilot_local_optimum_role_conflict_ambiguous_search.json
    if (-not $SkipVariants) {
        $variantsOutRoot = "runs\\ui_local_optimum_variants_$stamp"
        Write-Host "Running UI local-optimum variants + distillation report..."
        $variantsLog = Join-Path $releaseLogsDir "ui_local_optimum_variants.log"
        .\scripts\run_ui_local_optimum_variants.ps1 `
            -OutRoot $variantsOutRoot `
            -Seeds $VariantsSeeds `
            -HoldoutName $resolvedHoldout `
            -FuzzVariants $VariantsFuzzVariants `
            -FuzzSeed $VariantsFuzzSeed *> $variantsLog
        if ($LASTEXITCODE -ne 0) {
            Write-Error "UI local-optimum variants failed. See $variantsLog"
            if (Test-Path $variantsLog) { Get-Content $variantsLog -Tail 60 | Out-Host }
            exit $LASTEXITCODE
        }
        Write-Host "UI local-optimum variants complete (log: $variantsLog)"
        $distillationPath = Join-Path $variantsOutRoot "distillation_report.json"
        if (Test-Path $distillationPath) {
            $releaseDir = "runs\\release_gates"
            $releaseDistillation = Join-Path $releaseDir "ui_local_optimum_distillation.json"
            New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
            Copy-Item -Path $distillationPath -Destination $releaseDistillation -Force
            $report = $null
            try {
                $report = Get-Content $releaseDistillation -Raw | ConvertFrom-Json
            } catch {
                Write-Error "Failed to parse ui_local_optimum_distillation.json after copy."
                exit 1
            }
            if (-not $report -or -not $report.holdout_name) {
                Write-Error "ui_local_optimum_distillation.json missing holdout_name."
                exit 1
            }
            if ($report.holdout_name -ne $RequiredVariantsHoldout) {
                Write-Error ("ui_local_optimum_distillation.json holdout_name '{0}' does not match required '{1}'." -f $report.holdout_name, $RequiredVariantsHoldout)
                exit 1
            }
            if ($AutoCurriculum) {
                try {
                    $choice = Get-NextHoldoutFromReport -Report $report -GapMin $AutoCurriculumGapMin -SolvedMin $AutoCurriculumSolvedMin -FallbackHoldout $resolvedHoldout
                    New-Item -ItemType Directory -Path (Split-Path $AutoCurriculumStatePath) -Force | Out-Null
                    [pscustomobject]@{
                        used_holdout = $resolvedHoldout
                        next_holdout = $choice.holdout
                        reason = $choice.reason
                        exhausted = $choice.exhausted
                        gap_min = $AutoCurriculumGapMin
                        solved_min = $AutoCurriculumSolvedMin
                        source_report = $distillationPath
                        updated_at = (Get-Date -Format "s")
                    } | ConvertTo-Json -Depth 5 | Set-Content -Path $AutoCurriculumStatePath -Encoding UTF8
                    if ($choice.exhausted) {
                        Write-Host "AutoCurriculum: no oracle gap found in current report (curriculum exhausted)."
                    } else {
                        Write-Host ("AutoCurriculum next holdout: {0} ({1})" -f $choice.holdout, $choice.reason)
                    }
                } catch {
                    Write-Host "AutoCurriculum: failed to parse distillation report for next holdout."
                }
            }
        }
    }
    if ($RunDriftHoldoutGate) {
        if (-not $ModelPath) {
            Write-Error "Set -ModelPath or GOLDEVIDENCEBENCH_MODEL before running the drift holdout gate."
            exit 1
        }
        Write-Host ("Running drift holdout gate (holdout={0})..." -f $DriftHoldoutName)
        .\scripts\run_drift_holdout_gate.ps1 -ModelPath $ModelPath -HoldoutName $DriftHoldoutName
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Drift holdout gate failed."
            exit 1
        }
    }
    $gateRequiresModelPath = -not ($GateAdapter -like "*llama_server_adapter*")
    if ($gateRequiresModelPath -and -not $ModelPath) {
        Write-Error ("Set -ModelPath or GOLDEVIDENCEBENCH_MODEL before running the bad actor holdout gate with adapter '{0}'." -f $GateAdapter)
        exit 1
    }
    if ($BadActorHoldoutId) {
        Write-Host ("Running bad actor holdout gate (holdout={0})..." -f $BadActorHoldoutId)
    } else {
        Write-Host "Running bad actor holdout gate..."
    }
    .\scripts\run_bad_actor_holdout_gate.ps1 `
        -ModelPath $ModelPath `
        -Adapter $GateAdapter `
        -HoldoutListPath $BadActorHoldoutListPath `
        -HoldoutId $BadActorHoldoutId
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Bad actor holdout gate failed."
        exit 1
    }
    python .\scripts\check_thresholds.py --config .\configs\usecase_checks.json --quiet-passes
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $artifactRoot = "runs\\ui_gate_artifacts_$stamp"
        New-Item -ItemType Directory -Path $artifactRoot -Force | Out-Null
        $pairs = @(
            @{
                Name = "local_optimum"
                Fixture = "data\\ui_minipilot_local_optimum_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_search.json"
            },
            @{
                Name = "local_optimum_delayed_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_delayed_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_delayed_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_blocking_modal_unmentioned_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_blocking_modal_unmentioned_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_blocking_modal_unmentioned_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_blocking_modal_unmentioned_blocked_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_blocking_modal_unmentioned_blocked_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_blocking_modal_unmentioned_blocked_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_blocking_modal_required_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_blocking_modal_required_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_blocking_modal_required_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_blocking_modal_permission_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_blocking_modal_permission_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_blocking_modal_permission_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_blocking_modal_consent_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_blocking_modal_consent_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_blocking_modal_consent_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_disabled_primary_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_disabled_primary_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_disabled_primary_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_toolbar_vs_menu_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_toolbar_vs_menu_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_toolbar_vs_menu_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_confirm_then_apply_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_confirm_then_apply_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_confirm_then_apply_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_tab_state_reset_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_tab_state_reset_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_tab_state_reset_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_context_switch_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_context_switch_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_context_switch_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_stale_tab_state_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_stale_tab_state_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_stale_tab_state_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_form_validation_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_form_validation_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_form_validation_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_window_focus_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_window_focus_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_window_focus_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_checkbox_gate_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_checkbox_gate_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_checkbox_gate_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_panel_toggle_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_panel_toggle_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_panel_toggle_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_accessibility_label_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_accessibility_label_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_accessibility_label_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_section_path_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_section_path_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_section_path_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_section_path_conflict_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_section_path_conflict_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_section_path_conflict_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_blocking_modal_unprompted_confirm_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_blocking_modal_unprompted_confirm_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_blocking_modal_unprompted_confirm_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_destructive_confirm_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_destructive_confirm_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_destructive_confirm_ambiguous_search.json"
            }
            @{
                Name = "local_optimum_role_conflict_ambiguous"
                Fixture = "data\\ui_minipilot_local_optimum_role_conflict_ambiguous_fixture.jsonl"
                Baseline = "runs\\ui_minipilot_local_optimum_role_conflict_ambiguous_search.json"
            }
        )
        foreach ($pair in $pairs) {
            if (-not (Test-Path $pair.Baseline)) {
                Write-Host "Skip artifact dump (missing baseline): $($pair.Baseline)"
                continue
            }
            $outDir = Join-Path $artifactRoot $pair.Name
            python .\scripts\dump_ui_baseline_artifacts.py `
                --fixture $pair.Fixture `
                --baseline $pair.Baseline `
                --out-dir $outDir
        }
    }
    if ($exitCode -ne 0) {
        Write-Error "Release threshold checks failed."
        exit 1
    }
    if (-not $SkipReliabilitySignal) {
        Write-Host "Running unified reliability signal gate..."
        $reliabilityArgs = @()
        if (-not $SkipRequireControlFamilies) {
            $reliabilityArgs += @(
                "-RequireRPAModeSwitch",
                "-RequireIntentSpec",
                "-RequireNoiseEscalation"
            )
        } else {
            Write-Warning "SkipRequireControlFamilies enabled: unified reliability gate will not require RPA/intent/noise families."
        }
        .\scripts\check_reliability_signal.ps1 @reliabilityArgs
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Unified reliability signal gate failed."
            exit 1
        }
        if (Test-Path "runs\\reliability_signal_latest.json") {
            .\scripts\set_latest_pointer.ps1 -RunDir "runs\\reliability_signal_latest.json" -PointerPath "runs\\latest_reliability_signal" | Out-Host
        }
    } else {
        Write-Host "Skipping unified reliability signal gate (-SkipReliabilitySignal)."
    }
}
