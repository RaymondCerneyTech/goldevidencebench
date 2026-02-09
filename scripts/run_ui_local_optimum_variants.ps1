param(
    [string]$OutRoot = "",
    [int]$Seeds = 10,
    [string]$HoldoutName = "local_optimum_blocking_modal_unmentioned_blocked",
    [int]$FuzzVariants = 0,
    [int]$FuzzSeed = 0,
    [switch]$VerboseJson
)

if (-not $OutRoot) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutRoot = "runs\\ui_local_optimum_variants_$stamp"
}

New-Item -ItemType Directory -Path $OutRoot -Force | Out-Null
$seedList = @()
if ($Seeds -gt 0) {
    $seedList = 0..($Seeds - 1)
}

$variants = @(
    @{
        Name = "local_optimum_base"
        Fixture = "data\\ui_minipilot_local_optimum_fixture.jsonl"
        Observed = "data\\ui_minipilot_local_optimum_observed_ok.jsonl"
    },
    @{
        Name = "local_optimum_role_mismatch"
        Fixture = "data\\ui_minipilot_local_optimum_role_mismatch_fixture.jsonl"
        Observed = "data\\ui_minipilot_local_optimum_role_mismatch_observed_ok.jsonl"
    },
    @{
        Name = "local_optimum_role_conflict"
        Fixture = "data\\ui_minipilot_local_optimum_role_conflict_fixture.jsonl"
        Observed = "data\\ui_minipilot_local_optimum_role_conflict_observed_ok.jsonl"
    },
    @{
        Name = "local_optimum_blocking_modal"
        Fixture = "data\\ui_minipilot_local_optimum_blocking_modal_fixture.jsonl"
        Observed = "data\\ui_minipilot_local_optimum_blocking_modal_observed_ok.jsonl"
    },
    @{
        Name = "local_optimum_blocking_modal_detour"
        Fixture = "data\\ui_minipilot_local_optimum_blocking_modal_detour_fixture.jsonl"
        Observed = "data\\ui_minipilot_local_optimum_blocking_modal_detour_observed_ok.jsonl"
    },
    @{
        Name = "local_optimum_tab_detour"
        Fixture = "data\\ui_minipilot_local_optimum_tab_detour_fixture.jsonl"
        Observed = "data\\ui_minipilot_local_optimum_tab_detour_observed_ok.jsonl"
    },
    @{
        Name = "local_optimum_disabled_primary"
        Fixture = "data\\ui_minipilot_local_optimum_disabled_primary_fixture.jsonl"
        Observed = "data\\ui_minipilot_local_optimum_disabled_primary_observed_ok.jsonl"
    },
    @{
        Name = "local_optimum_toolbar_vs_menu"
        Fixture = "data\\ui_minipilot_local_optimum_toolbar_vs_menu_fixture.jsonl"
        Observed = "data\\ui_minipilot_local_optimum_toolbar_vs_menu_observed_ok.jsonl"
    },
    @{
        Name = "local_optimum_confirm_then_apply"
        Fixture = "data\\ui_minipilot_local_optimum_confirm_then_apply_fixture.jsonl"
        Observed = "data\\ui_minipilot_local_optimum_confirm_then_apply_observed_ok.jsonl"
    },
    @{
        Name = "local_optimum_tab_state_reset"
        Fixture = "data\\ui_minipilot_local_optimum_tab_state_reset_fixture.jsonl"
        Observed = "data\\ui_minipilot_local_optimum_tab_state_reset_observed_ok.jsonl"
    },
    @{
        Name = "local_optimum_delayed"
        Fixture = "data\\ui_minipilot_local_optimum_delayed_fixture.jsonl"
        Observed = "data\\ui_minipilot_local_optimum_delayed_observed_ok.jsonl"
    },
    @{
        Name = "local_optimum_stale_tab_state"
        Fixture = "data\\ui_minipilot_local_optimum_stale_tab_state_fixture.jsonl"
        Observed = "data\\ui_minipilot_local_optimum_stale_tab_state_observed_ok.jsonl"
    },
    @{
        Name = "local_optimum_context_switch"
        Fixture = "data\\ui_minipilot_local_optimum_context_switch_fixture.jsonl"
        Observed = "data\\ui_minipilot_local_optimum_context_switch_observed_ok.jsonl"
    },
    @{
        Name = "local_optimum_form_validation"
        Fixture = "data\\ui_minipilot_local_optimum_form_validation_fixture.jsonl"
        Observed = "data\\ui_minipilot_local_optimum_form_validation_observed_ok.jsonl"
    },
    @{
        Name = "local_optimum_window_focus"
        Fixture = "data\\ui_minipilot_local_optimum_window_focus_fixture.jsonl"
        Observed = "data\\ui_minipilot_local_optimum_window_focus_observed_ok.jsonl"
    },
    @{
        Name = "local_optimum_panel_toggle"
        Fixture = "data\\ui_minipilot_local_optimum_panel_toggle_fixture.jsonl"
        Observed = "data\\ui_minipilot_local_optimum_panel_toggle_observed_ok.jsonl"
    },
    @{
        Name = "local_optimum_accessibility_label"
        Fixture = "data\\ui_minipilot_local_optimum_accessibility_label_fixture.jsonl"
        Observed = "data\\ui_minipilot_local_optimum_accessibility_label_observed_ok.jsonl"
    },
    @{
        Name = "local_optimum_checkbox_gate"
        Fixture = "data\\ui_minipilot_local_optimum_checkbox_gate_fixture.jsonl"
        Observed = "data\\ui_minipilot_local_optimum_checkbox_gate_observed_ok.jsonl"
    },
    @{
        Name = "local_optimum_section_path"
        Fixture = "data\\ui_minipilot_local_optimum_section_path_fixture.jsonl"
        Observed = "data\\ui_minipilot_local_optimum_section_path_observed_ok.jsonl"
    },
    @{
        Name = "local_optimum_section_path_conflict"
        Fixture = "data\\ui_minipilot_local_optimum_section_path_conflict_fixture.jsonl"
        Observed = "data\\ui_minipilot_local_optimum_section_path_conflict_observed_ok.jsonl"
    },
    @{
        Name = "local_optimum_blocking_modal_unmentioned"
        Fixture = "data\\ui_minipilot_local_optimum_blocking_modal_unmentioned_fixture.jsonl"
        Observed = "data\\ui_minipilot_local_optimum_blocking_modal_unmentioned_observed_ok.jsonl"
    },
    @{
        Name = "local_optimum_blocking_modal_unmentioned_blocked"
        Fixture = "data\\ui_minipilot_local_optimum_blocking_modal_unmentioned_blocked_fixture.jsonl"
        Observed = "data\\ui_minipilot_local_optimum_blocking_modal_unmentioned_blocked_observed_ok.jsonl"
    },
    @{
        Name = "local_optimum_blocking_modal_required"
        Fixture = "data\\ui_minipilot_local_optimum_blocking_modal_required_fixture.jsonl"
        Observed = "data\\ui_minipilot_local_optimum_blocking_modal_required_observed_ok.jsonl"
    },
    @{
        Name = "local_optimum_blocking_modal_permission"
        Fixture = "data\\ui_minipilot_local_optimum_blocking_modal_permission_fixture.jsonl"
        Observed = "data\\ui_minipilot_local_optimum_blocking_modal_permission_observed_ok.jsonl"
    },
    @{
        Name = "local_optimum_blocking_modal_consent"
        Fixture = "data\\ui_minipilot_local_optimum_blocking_modal_consent_fixture.jsonl"
        Observed = "data\\ui_minipilot_local_optimum_blocking_modal_consent_observed_ok.jsonl"
    },
    @{
        Name = "local_optimum_blocking_modal_unprompted_confirm"
        Fixture = "data\\ui_minipilot_local_optimum_blocking_modal_unprompted_confirm_fixture.jsonl"
        Observed = "data\\ui_minipilot_local_optimum_blocking_modal_unprompted_confirm_observed_ok.jsonl"
    },
    @{
        Name = "local_optimum_destructive_confirm"
        Fixture = "data\\ui_minipilot_local_optimum_destructive_confirm_fixture.jsonl"
        Observed = "data\\ui_minipilot_local_optimum_destructive_confirm_observed_ok.jsonl"
    },
    @{
        Name = "local_optimum_delayed_solvable"
        Fixture = "data\\ui_minipilot_local_optimum_delayed_solvable_fixture.jsonl"
        Observed = "data\\ui_minipilot_local_optimum_delayed_solvable_observed_ok.jsonl"
    },
    @{
        Name = "local_optimum_overlay"
        Fixture = "data\\ui_minipilot_local_optimum_overlay_fixture.jsonl"
        Observed = "data\\ui_minipilot_local_optimum_overlay_observed_ok.jsonl"
    },
    @{
        Name = "local_optimum_primary"
        Fixture = "data\\ui_minipilot_local_optimum_primary_fixture.jsonl"
        Observed = "data\\ui_minipilot_local_optimum_primary_observed_ok.jsonl"
    }
)

$results = @()
foreach ($variant in $variants) {
    $name = $variant.Name
    $fixture = $variant.Fixture
    $observed = $variant.Observed
    $outPath = Join-Path $OutRoot ("{0}_search.json" -f $name)

    Write-Host ("Running {0}..." -f $name)
    $fuzzArgs = @()
    if ($FuzzVariants -gt 0) {
        $fuzzArgs = @("--fuzz-variants", "$FuzzVariants", "--fuzz-seed", "$FuzzSeed")
    }
    python .\scripts\run_ui_search_baseline.py --fixture $fixture --observed $observed --out $outPath --seeds $Seeds --quiet @fuzzArgs

    if (Test-Path $outPath) {
        $payload = Get-Content $outPath -Raw | ConvertFrom-Json
        $seedSummary = $payload.seed_summary
        $resolvedSeedList = $seedSummary.seed_list
        if (-not $resolvedSeedList) {
            $resolvedSeedList = $seedList
        }
        $results += [pscustomobject]@{
            name = $name
            fixture = $fixture
            out = $outPath
            seeds = $seedSummary.seeds
            seed_list = $resolvedSeedList
            sa_beats_greedy_rate = $seedSummary.sa_beats_greedy_rate
        }
    }
}

$distillationPath = Join-Path $OutRoot "distillation_report.json"
$summary = [pscustomobject]@{
    out_root = $OutRoot
    seeds = $Seeds
    seed_list = $seedList
    holdout_name = $HoldoutName
    fuzz_variants = $FuzzVariants
    fuzz_seed = $FuzzSeed
    generated_at = (Get-Date -Format "s")
    variants = $results
    distillation_report = $distillationPath
}

$summaryPath = Join-Path $OutRoot "summary.json"
$summary | ConvertTo-Json -Depth 6 | Set-Content -Path $summaryPath -Encoding UTF8

Write-Host ("Building distillation report (holdout: {0})..." -f $HoldoutName)
python .\scripts\build_ui_sa_distillation_report.py --variants-dir $OutRoot `
    --holdout-name $HoldoutName --out $distillationPath --quiet

Write-Host ("Summary: {0}" -f $summaryPath)
Write-Host ("Distillation report: {0}" -f $distillationPath)
Write-Host ("Variants complete: {0} (seeds={1}, holdout={2})" -f $results.Count, $Seeds, $HoldoutName)
if ($VerboseJson) {
    Write-Host ($summary | ConvertTo-Json -Depth 5)
}
