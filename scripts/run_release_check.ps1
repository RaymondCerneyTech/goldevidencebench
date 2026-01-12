param(
    [string]$ModelPath = $env:GOLDEVIDENCEBENCH_MODEL,
    [switch]$RunSweeps,
    [switch]$SkipThresholds,
    [int]$VariantsSeeds = 10,
    [string]$VariantsHoldoutName = "local_optimum_blocking_modal_required",
    [int]$VariantsFuzzVariants = 5,
    [int]$VariantsFuzzSeed = 0,
    [switch]$RotateHoldout,
    [string]$HoldoutList = "local_optimum_blocking_modal_detour,local_optimum_tab_detour,local_optimum_blocking_modal_required,local_optimum_blocking_modal_permission,local_optimum_blocking_modal_consent,local_optimum_blocking_modal_unmentioned,local_optimum_blocking_modal,local_optimum_overlay,local_optimum_primary,local_optimum_delayed_solvable,local_optimum_role_mismatch",
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

if (-not $SkipThresholds) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
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

    Write-Host "Running instruction override gate..."
    .\scripts\run_instruction_override_gate.ps1 -ModelPath $ModelPath
    Write-Host "Running UI same_label stub..."
    .\scripts\run_ui_same_label_stub.ps1
    Write-Host "Running UI popup_overlay stub..."
    .\scripts\run_ui_popup_overlay_stub.ps1
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
