param(
    [string]$OutRoot = "",
    [int]$Seeds = 10,
    [string[]]$HoldoutNames = @(),
    [string[]]$IncludeHoldoutNames = @(),
    [string[]]$ExcludeHoldoutNames = @(),
    [int]$FuzzVariants = 0,
    [int]$FuzzSeed = 0,
    [switch]$Strict,
    [string[]]$AllowMissing = @()
)

$ErrorActionPreference = "Stop"

function Get-DefaultHoldouts {
    $fixtures = Get-ChildItem .\data\ui_minipilot_local_optimum*fixture.jsonl |
        Where-Object { $_.Name -notmatch "_ambiguous" }
    $holdouts = @()
    foreach ($fixture in $fixtures) {
        if ($fixture.BaseName -eq "ui_minipilot_local_optimum_fixture") {
            $holdouts += "local_optimum_base"
            continue
        }
        $suffix = $fixture.BaseName -replace "^ui_minipilot_local_optimum_", "" -replace "_fixture$", ""
        if (-not $suffix) {
            continue
        }
        $holdouts += ("local_optimum_{0}" -f $suffix)
    }
    return $holdouts | Sort-Object -Unique
}

function Get-VariantHoldouts {
    param([string]$VariantsScriptPath)
    if (-not (Test-Path $VariantsScriptPath)) {
        throw "Missing variants script at $VariantsScriptPath"
    }
    $text = Get-Content -Raw -Path $VariantsScriptPath
    $matches = [regex]::Matches($text, 'Name\s*=\s*"([^"]+)"')
    $names = @()
    foreach ($match in $matches) {
        $names += $match.Groups[1].Value
    }
    return $names | Sort-Object -Unique
}

if (-not $OutRoot) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutRoot = "runs\\holdout_rotations_$stamp"
}

New-Item -ItemType Directory -Path $OutRoot -Force | Out-Null

$variantsScript = Join-Path $PSScriptRoot "run_ui_local_optimum_variants.ps1"
$fixtureHoldouts = Get-DefaultHoldouts
$variantHoldouts = Get-VariantHoldouts -VariantsScriptPath $variantsScript
$eligibleHoldouts = $fixtureHoldouts | Where-Object { $_ -in $variantHoldouts }
$fixtureOnly = $fixtureHoldouts | Where-Object { $_ -notin $variantHoldouts }
$variantOnly = $variantHoldouts | Where-Object { $_ -notin $fixtureHoldouts }

if ($fixtureOnly.Count -gt 0) {
    Write-Warning ("Fixtures missing variants: {0}" -f ($fixtureOnly -join ", "))
}
if ($variantOnly.Count -gt 0) {
    Write-Warning ("Variants missing fixtures: {0}" -f ($variantOnly -join ", "))
}

if (-not $HoldoutNames -or $HoldoutNames.Count -eq 0) {
    $HoldoutNames = $eligibleHoldouts
}

if ($IncludeHoldoutNames -and $IncludeHoldoutNames.Count -gt 0) {
    $HoldoutNames = $IncludeHoldoutNames
}

if (-not $HoldoutNames -or $HoldoutNames.Count -eq 0) {
    throw "No eligible holdouts found (fixtures ∩ variants is empty)."
}

$requestedHoldouts = $HoldoutNames
$requestedMissing = $requestedHoldouts | Where-Object { $_ -notin $eligibleHoldouts }
if ($requestedMissing.Count -gt 0) {
    Write-Warning ("Requested holdouts missing variants/fixtures: {0}" -f ($requestedMissing -join ", "))
}

$HoldoutNames = $requestedHoldouts | Where-Object { $_ -in $eligibleHoldouts }

if ($ExcludeHoldoutNames -and $ExcludeHoldoutNames.Count -gt 0) {
    $HoldoutNames = $HoldoutNames | Where-Object { $_ -notin $ExcludeHoldoutNames }
}

if (-not $HoldoutNames -or $HoldoutNames.Count -eq 0) {
    throw "No holdouts to run after filtering."
}

if ($AllowMissing -and $AllowMissing.Count -gt 0) {
    $fixtureOnly = $fixtureOnly | Where-Object { $_ -notin $AllowMissing }
    $variantOnly = $variantOnly | Where-Object { $_ -notin $AllowMissing }
    $requestedMissing = $requestedMissing | Where-Object { $_ -notin $AllowMissing }
}

$fixtureHoldouts = @($fixtureHoldouts)
$variantHoldouts = @($variantHoldouts)
$eligibleHoldouts = @($eligibleHoldouts)
$fixtureOnly = @($fixtureOnly)
$variantOnly = @($variantOnly)
$requestedMissing = @($requestedMissing)
$HoldoutNames = @($HoldoutNames)

if ($Strict -and (($fixtureOnly.Count -gt 0) -or ($variantOnly.Count -gt 0) -or ($requestedMissing.Count -gt 0))) {
    throw "Holdout coverage mismatch detected in strict mode."
}

$results = @()
foreach ($holdout in $HoldoutNames) {
    $runDir = Join-Path $OutRoot $holdout
    Write-Host ("Running holdout: {0}" -f $holdout)
    .\scripts\run_ui_local_optimum_variants.ps1 `
        -HoldoutName $holdout `
        -OutRoot $runDir `
        -Seeds $Seeds `
        -FuzzVariants $FuzzVariants `
        -FuzzSeed $FuzzSeed

    if ($LASTEXITCODE -ne 0) {
        throw ("Variants run failed for {0}" -f $holdout)
    }

    $reportPath = Join-Path $runDir "distillation_report.json"
    if (-not (Test-Path $reportPath)) {
        throw ("Missing distillation_report.json for {0}" -f $holdout)
    }

    $report = Get-Content $reportPath -Raw | ConvertFrom-Json
    $holdoutSummary = $report.holdout
    $nonHoldout = $report.non_holdout

    $results += [pscustomobject]@{
        holdout_name = $report.holdout_name
        report_path = $reportPath
        holdout_policy_task_pass_rate_min = $holdoutSummary.policy_task_pass_rate_min
        holdout_greedy_task_pass_rate_min = $holdoutSummary.greedy_task_pass_rate_min
        holdout_sa_task_pass_rate_min = $holdoutSummary.sa_task_pass_rate_min
        holdout_sa_beats_greedy_rate = $holdoutSummary.sa_beats_greedy_rate
        non_holdout_policy_task_pass_rate_min = $nonHoldout.policy_task_pass_rate_min
        non_holdout_greedy_task_pass_rate_min = $nonHoldout.greedy_task_pass_rate_min
        non_holdout_sa_task_pass_rate_min = $nonHoldout.sa_task_pass_rate_min
    }
}

$index = [pscustomobject]@{
    out_root = $OutRoot
    generated_at = (Get-Date -Format "s")
    seeds = $Seeds
    fuzz_variants = $FuzzVariants
    fuzz_seed = $FuzzSeed
    counts = [pscustomobject]@{
        fixtures = $fixtureHoldouts.Count
        variants = $variantHoldouts.Count
        eligible = $eligibleHoldouts.Count
        fixtures_only = $fixtureOnly.Count
        variants_only = $variantOnly.Count
        requested_missing = $requestedMissing.Count
    }
    warnings = @(
        if ($fixtureOnly.Count -gt 0) { "fixtures_missing_variants" }
        if ($variantOnly.Count -gt 0) { "variants_missing_fixtures" }
        if ($requestedMissing.Count -gt 0) { "requested_missing" }
    )
    holdouts = $HoldoutNames
    fixtures = $fixtureHoldouts
    variants = $variantHoldouts
    eligible_holdouts = $eligibleHoldouts
    fixtures_missing_variants = $fixtureOnly
    variants_missing_fixtures = $variantOnly
    requested_missing = $requestedMissing
    results = $results
}

$indexPath = Join-Path $OutRoot "rotation_index.json"
$csvPath = Join-Path $OutRoot "rotation_index.csv"
$coveragePath = Join-Path $OutRoot "coverage_report.json"

$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($indexPath, ($index | ConvertTo-Json -Depth 6), $utf8NoBom)
$results | Export-Csv -Path $csvPath -NoTypeInformation
$coverageJson = $index | Select-Object fixtures,variants,eligible_holdouts,fixtures_missing_variants,variants_missing_fixtures,requested_missing |
    ConvertTo-Json -Depth 6
[System.IO.File]::WriteAllText($coveragePath, $coverageJson, $utf8NoBom)

Write-Host ("Rotation index: {0}" -f $indexPath)
Write-Host ("Rotation CSV: {0}" -f $csvPath)
Write-Host ("Coverage report: {0}" -f $coveragePath)
