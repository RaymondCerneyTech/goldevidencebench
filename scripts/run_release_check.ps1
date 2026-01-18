param(
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL,
    [switch]$RunSweeps,
    [switch]$SkipThresholds,
    [int]$VariantsSeeds = 10,
    [string]$VariantsHoldoutName = "local_optimum_blocking_modal_required",
    [int]$VariantsFuzzVariants = 5,
    [int]$VariantsFuzzSeed = 0,
    [switch]$RotateHoldout,
    [switch]$AutoCurriculum,
    [double]$AutoCurriculumGapMin = 0.1,
    [double]$AutoCurriculumSolvedMin = 0.9,
    [string]$AutoCurriculumStatePath = "runs\\release_gates\\ui_holdout_autocurriculum.json",
    [string]$HoldoutList = "local_optimum_section_path,local_optimum_section_path_conflict,local_optimum_blocking_modal_detour,local_optimum_tab_detour,local_optimum_disabled_primary,local_optimum_toolbar_vs_menu,local_optimum_confirm_then_apply,local_optimum_tab_state_reset,local_optimum_form_validation,local_optimum_window_focus,local_optimum_panel_toggle,local_optimum_accessibility_label,local_optimum_checkbox_gate,local_optimum_blocking_modal_required,local_optimum_blocking_modal_permission,local_optimum_blocking_modal_consent,local_optimum_blocking_modal_unmentioned,local_optimum_blocking_modal,local_optimum_overlay,local_optimum_primary,local_optimum_delayed_solvable,local_optimum_role_mismatch,local_optimum_role_conflict,local_optimum_destructive_confirm,local_optimum_blocking_modal_unprompted_confirm",
    [switch]$SkipVariants
)

if ($RunSweeps -and -not $ModelPath) {
    Write-Error "Set -ModelPath or GOLDEVIDENCEBENCH_MODEL before running sweeps."
    exit 1
}

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
        $holdoutNames = @(
            $HoldoutList -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ }
        )
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
    .\scripts\run_instruction_override_gate.ps1 -ModelPath $ModelPath
    Write-Host "Running memory verification gate..."
    python .\scripts\verify_memories.py --in .\data\memories\memory_demo.jsonl `
        --out .\runs\release_gates\memory_verify.json `
        --out-details .\runs\release_gates\memory_verify_details.json
    Write-Host "Running UI same_label stub..."
    .\scripts\run_ui_same_label_stub.ps1
    Write-Host "Running UI popup_overlay stub..."
    .\scripts\run_ui_popup_overlay_stub.ps1
    Write-Host "Running UI minipilot notepad stub..."
    .\scripts\run_ui_minipilot_notepad_stub.ps1
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
        .\scripts\run_ui_local_optimum_variants.ps1 `
            -OutRoot $variantsOutRoot `
            -Seeds $VariantsSeeds `
            -HoldoutName $resolvedHoldout `
            -FuzzVariants $VariantsFuzzVariants `
            -FuzzSeed $VariantsFuzzSeed
        $distillationPath = Join-Path $variantsOutRoot "distillation_report.json"
        if (Test-Path $distillationPath) {
            $releaseDir = "runs\\release_gates"
            New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
            Copy-Item -Path $distillationPath -Destination (Join-Path $releaseDir "ui_local_optimum_distillation.json") -Force
            if ($AutoCurriculum) {
                try {
                    $report = Get-Content $distillationPath -Raw | ConvertFrom-Json
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
    python .\scripts\check_thresholds.py --config .\configs\usecase_checks.json
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
}
