param(
    [string]$OutRoot = "",
    [int[]]$Duplicates = @(1, 2, 3, 4, 5),
    [int]$Steps = 6,
    [int]$Seed = 0,
    [string]$Labels = "Next,Continue,Save",
    [string]$Adapter = "goldevidencebench.adapters.ui_fixture_adapter:create_adapter",
    [string]$SelectionMode = "",
    [string]$SelectionSeed = "0",
    [string]$UiAdapter = "goldevidencebench.adapters.ui_llama_cpp_adapter:create_adapter",
    [string]$UiModelPath = "",
    [switch]$RunAdapterGate,
    [switch]$UpdateConfig,
    [string]$ConfigPath = "configs\\usecase_checks.json",
    [string]$CheckId = "ui_same_label_wall",
    [string]$Metric = "metrics.wrong_action_rate",
    [double]$Threshold = 0.10,
    [ValidateSet("gte", "lte")]
    [string]$Direction = "gte",
    [switch]$UseWall,
    [int]$VariantsSeeds = 10,
    [string]$VariantsHoldoutName = "local_optimum_blocking_modal_required",
    [int]$VariantsFuzzVariants = 5,
    [int]$VariantsFuzzSeed = 0,
    [switch]$RotateHoldout,
    [string]$HoldoutList = "local_optimum_section_path,local_optimum_section_path_conflict,local_optimum_blocking_modal_detour,local_optimum_tab_detour,local_optimum_disabled_primary,local_optimum_toolbar_vs_menu,local_optimum_confirm_then_apply,local_optimum_tab_state_reset,local_optimum_context_switch,local_optimum_stale_tab_state,local_optimum_form_validation,local_optimum_window_focus,local_optimum_panel_toggle,local_optimum_accessibility_label,local_optimum_blocking_modal_required,local_optimum_blocking_modal_permission,local_optimum_blocking_modal_consent,local_optimum_blocking_modal_unmentioned,local_optimum_blocking_modal_unmentioned_blocked,local_optimum_blocking_modal,local_optimum_overlay,local_optimum_primary,local_optimum_delayed_solvable,local_optimum_role_mismatch,local_optimum_role_conflict,local_optimum_destructive_confirm,local_optimum_blocking_modal_unprompted_confirm",
    [switch]$SkipVariants,
    [switch]$CheckThresholds,
    [switch]$DumpGateArtifactsOnFail
)

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
if (-not $OutRoot) {
    $OutRoot = "runs\\ui_same_label_wall_$stamp"
}

$resolvedHoldout = $VariantsHoldoutName
if ($RotateHoldout) {
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

Write-Host "Running UI same_label stub..."
.\scripts\run_ui_same_label_stub.ps1

Write-Host "Running UI popup_overlay stub..."
.\scripts\run_ui_popup_overlay_stub.ps1

Write-Host "Running UI popup_overlay policy stub..."
.\scripts\run_ui_popup_overlay_policy_stub.ps1

Write-Host "Running UI minipilot stub..."
.\scripts\run_ui_minipilot_stub.ps1

Write-Host "Running UI minipilot notepad stub..."
.\scripts\run_ui_minipilot_notepad_stub.ps1

Write-Host "Running UI minipilot notepad ambiguous baseline..."
python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_notepad_ambiguous_fixture.jsonl `
    --observed .\data\ui_minipilot_notepad_ambiguous_observed_ok.jsonl `
    --out .\runs\ui_minipilot_notepad_ambiguous_search.json

Write-Host "Running UI minipilot notepad wrong-directory detour baseline..."
python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_notepad_wrong_directory_detour_fixture.jsonl `
    --observed .\data\ui_minipilot_notepad_wrong_directory_detour_observed_ok.jsonl `
    --out .\runs\ui_minipilot_notepad_wrong_directory_detour_search.json

Write-Host "Running UI minipilot form stub..."
.\scripts\run_ui_minipilot_form_stub.ps1

Write-Host "Running UI minipilot table stub..."
.\scripts\run_ui_minipilot_table_stub.ps1

Write-Host "Running UI minipilot traps stub..."
.\scripts\run_ui_minipilot_traps_stub.ps1

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
python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_window_focus_ambiguous_fixture.jsonl `
    --observed .\data\ui_minipilot_local_optimum_window_focus_ambiguous_observed_ok.jsonl `
    --out .\runs\ui_minipilot_local_optimum_window_focus_ambiguous_search.json
python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_panel_toggle_ambiguous_fixture.jsonl `
    --observed .\data\ui_minipilot_local_optimum_panel_toggle_ambiguous_observed_ok.jsonl `
    --out .\runs\ui_minipilot_local_optimum_panel_toggle_ambiguous_search.json
python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_accessibility_label_ambiguous_fixture.jsonl `
    --observed .\data\ui_minipilot_local_optimum_accessibility_label_ambiguous_observed_ok.jsonl `
    --out .\runs\ui_minipilot_local_optimum_accessibility_label_ambiguous_search.json
python .\scripts\run_ui_search_baseline.py --fixture .\data\ui_minipilot_local_optimum_section_path_ambiguous_fixture.jsonl `
    --observed .\data\ui_minipilot_local_optimum_section_path_ambiguous_observed_ok.jsonl `
    --out .\runs\ui_minipilot_local_optimum_section_path_ambiguous_search.json
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
    }
}

if ($RunAdapterGate -or $UiModelPath) {
    if (-not $UiModelPath) {
        $UiModelPath = $env:GOLDEVIDENCEBENCH_MODEL
    }
    if (-not $UiModelPath) {
        Write-Host "Skipping UI adapter gate: set -UiModelPath or GOLDEVIDENCEBENCH_MODEL."
    } else {
        Write-Host "Running UI adapter gate (llama-cpp)..."
        $runsDir = "runs"
        $prevModel = $env:GOLDEVIDENCEBENCH_MODEL
        $env:GOLDEVIDENCEBENCH_MODEL = $UiModelPath
        $env:GOLDEVIDENCEBENCH_UI_OVERLAY_FILTER = "1"
        $env:GOLDEVIDENCEBENCH_UI_PRESELECT_RULES = "1"
        New-Item -ItemType Directory -Path $runsDir -Force | Out-Null
        $traceStamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $env:GOLDEVIDENCEBENCH_UI_TRACE_PATH = (Join-Path $runsDir ("ui_same_label_llm_trace_{0}.jsonl" -f $traceStamp))
        goldevidencebench ui-score --adapter $UiAdapter `
            --fixture .\data\ui_same_label_fixture.jsonl --out (Join-Path $runsDir "ui_same_label_llm_gate.json")
        $env:GOLDEVIDENCEBENCH_UI_TRACE_PATH = (Join-Path $runsDir ("ui_popup_overlay_llm_trace_{0}.jsonl" -f $traceStamp))
        goldevidencebench ui-score --adapter $UiAdapter `
            --fixture .\data\ui_popup_overlay_fixture.jsonl --out (Join-Path $runsDir "ui_popup_overlay_llm_gate.json")
        $env:GOLDEVIDENCEBENCH_UI_TRACE_PATH = (Join-Path $runsDir ("ui_popup_overlay_policy_llm_trace_{0}.jsonl" -f $traceStamp))
        goldevidencebench ui-score --adapter $UiAdapter `
            --fixture .\data\ui_popup_overlay_policy_fixture.jsonl --out (Join-Path $runsDir "ui_popup_overlay_policy_llm_gate.json")
        $env:GOLDEVIDENCEBENCH_UI_TRACE_PATH = (Join-Path $runsDir ("ui_minipilot_llm_trace_{0}.jsonl" -f $traceStamp))
        goldevidencebench ui-score --adapter $UiAdapter `
            --fixture .\data\ui_minipilot_fixture.jsonl --out (Join-Path $runsDir "ui_minipilot_llm_gate.json")
        $env:GOLDEVIDENCEBENCH_UI_TRACE_PATH = (Join-Path $runsDir ("ui_minipilot_notepad_llm_trace_{0}.jsonl" -f $traceStamp))
        goldevidencebench ui-score --adapter $UiAdapter `
            --fixture .\data\ui_minipilot_notepad_fixture.jsonl --out (Join-Path $runsDir "ui_minipilot_notepad_llm_gate.json")
        $env:GOLDEVIDENCEBENCH_UI_TRACE_PATH = (Join-Path $runsDir ("ui_minipilot_form_llm_trace_{0}.jsonl" -f $traceStamp))
        goldevidencebench ui-score --adapter $UiAdapter `
            --fixture .\data\ui_minipilot_form_fixture.jsonl --out (Join-Path $runsDir "ui_minipilot_form_llm_gate.json")
        $env:GOLDEVIDENCEBENCH_UI_TRACE_PATH = (Join-Path $runsDir ("ui_minipilot_table_llm_trace_{0}.jsonl" -f $traceStamp))
        goldevidencebench ui-score --adapter $UiAdapter `
            --fixture .\data\ui_minipilot_table_fixture.jsonl --out (Join-Path $runsDir "ui_minipilot_table_llm_gate.json")
        $env:GOLDEVIDENCEBENCH_UI_TRACE_PATH = (Join-Path $runsDir ("ui_minipilot_traps_llm_trace_{0}.jsonl" -f $traceStamp))
        goldevidencebench ui-score --adapter $UiAdapter `
            --fixture .\data\ui_minipilot_traps_fixture.jsonl --out (Join-Path $runsDir "ui_minipilot_traps_llm_gate.json")
        Remove-Item Env:\GOLDEVIDENCEBENCH_UI_TRACE_PATH -ErrorAction SilentlyContinue
        Remove-Item Env:\GOLDEVIDENCEBENCH_UI_OVERLAY_FILTER -ErrorAction SilentlyContinue
        Remove-Item Env:\GOLDEVIDENCEBENCH_UI_PRESELECT_RULES -ErrorAction SilentlyContinue
        if ($prevModel) {
            $env:GOLDEVIDENCEBENCH_MODEL = $prevModel
        } else {
            Remove-Item Env:\GOLDEVIDENCEBENCH_MODEL -ErrorAction SilentlyContinue
        }
    }
}

Write-Host "Running UI same_label wall sweep..."
.\scripts\run_ui_same_label_wall.ps1 `
    -OutRoot $OutRoot `
    -Duplicates $Duplicates `
    -Steps $Steps `
    -Seed $Seed `
    -Labels $Labels `
    -Adapter $Adapter `
    -SelectionMode $SelectionMode `
    -SelectionSeed $SelectionSeed

if ($UpdateConfig) {
    $useWallFlag = $null
    if ($UseWall) {
        $useWallFlag = "--use-wall"
    }
    python .\scripts\find_ui_wall.py --runs-dir $OutRoot `
        --metric $Metric --threshold $Threshold --direction $Direction `
        --update-config $ConfigPath --check-id $CheckId $useWallFlag
}

if ($CheckThresholds) {
    python .\scripts\check_thresholds.py --config $ConfigPath
    $exitCode = $LASTEXITCODE
    if ($DumpGateArtifactsOnFail -and $exitCode -ne 0) {
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
