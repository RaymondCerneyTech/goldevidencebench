param(
    [string]$Adapter = "goldevidencebench.adapters.llama_server_adapter:create_adapter",
    [ValidateSet("fastlocal", "release")]
    [string]$Profile = "release",
    [string]$ContractPath = "configs\\release_gate_contract.json",
    [string]$ContractSchemaPath = "schemas\\release_gate_contract.schema.json",
    [int]$MaxRounds = 3,
    [switch]$UseExistingArtifactsOnly,
    [switch]$StopOnFirstFamilyFailure,
    [switch]$HonorFreshnessInIteration,
    [switch]$SkipReliabilitySignal,
    [switch]$FailOnArtifactAudit,
    [bool]$RunPersonaTrap = $true,
    [string]$PersonaProfiles = "persona_confident_expert,persona_creative_writer,persona_ultra_brief,persona_overly_helpful",
    [string[]]$FamilyFilter = @(),
    [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"

if ($MaxRounds -lt 1) {
    Write-Error "MaxRounds must be >= 1."
    exit 1
}
if (-not $OutDir) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutDir = "runs\\test_check_$stamp"
}
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null

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

function Read-SummaryStatus {
    param([string]$Path)
    $obj = Read-JsonObject -Path $Path
    if (-not $obj) {
        return "MISSING"
    }
    if ($obj.PSObject.Properties.Name -contains "status") {
        $status = "$($obj.status)".Trim()
        if ($status) {
            return $status
        }
    }
    if ($obj.PSObject.Properties.Name -contains "overall") {
        if ($obj.overall -and ($obj.overall.PSObject.Properties.Name -contains "status")) {
            $status = "$($obj.overall.status)".Trim()
            if ($status) {
                return $status
            }
        }
    }
    return "UNKNOWN"
}

function Resolve-CanaryPolicy {
    param(
        $Family,
        [string]$DefaultCanaryPolicy
    )
    $policy = $DefaultCanaryPolicy
    if ($Family -and ($Family.PSObject.Properties.Name -contains "canary_policy")) {
        $candidate = "$($Family.canary_policy)".Trim()
        if (-not [string]::IsNullOrWhiteSpace($candidate)) {
            $policy = $candidate
        }
    }
    if (($policy -ne "strict") -and ($policy -ne "triage")) {
        throw "Unsupported canary policy '$policy' for family '$($Family.id)'. Expected strict|triage."
    }
    return $policy
}

function Invoke-MatrixAssessment {
    param(
        [string]$ContractPathArg,
        [string]$OutPath,
        [switch]$UseExistingArtifacts
    )
    $args = @{
        ContractPath = $ContractPathArg
        ContractSchemaPath = $ContractSchemaPath
        Adapter = $Adapter
        Out = $OutPath
        RunPersonaTrap = $RunPersonaTrap
        PersonaProfiles = $PersonaProfiles
    }
    if ($UseExistingArtifacts) {
        $args.UseExistingArtifacts = $true
    }
    .\scripts\run_release_reliability_matrix.ps1 @args
    if ($LASTEXITCODE -ne 0) {
        throw "run_release_reliability_matrix.ps1 failed (exit=$LASTEXITCODE)."
    }
    $payload = Read-JsonObject -Path $OutPath
    if (-not $payload) {
        throw "Unable to parse matrix artifact: $OutPath"
    }
    return $payload
}

function Invoke-CompressionRerun {
    param(
        [string]$Stage,
        [string]$ArtifactPath,
        [string]$CanaryPolicy
    )
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $runDir = "runs\\compression_families_${stamp}_${Stage}_test_check"
    & .\scripts\run_compression_families.ps1 `
        -OutRoot $runDir `
        -Adapter $Adapter `
        -Stage $Stage `
        -CanaryPolicy $CanaryPolicy `
        -RunPersonaTrap:$RunPersonaTrap `
        -PersonaProfiles $PersonaProfiles
    $runExit = $LASTEXITCODE

    $parent = Split-Path -Parent $ArtifactPath
    if ($parent) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    python .\scripts\check_compression_reliability.py `
        --run-dirs $runDir `
        --min-runs 1 `
        --out $ArtifactPath | Out-Host
    $checkerExit = $LASTEXITCODE
    $status = Read-SummaryStatus -Path $ArtifactPath

    return [ordered]@{
        family = "compression"
        stage = $Stage
        artifact_path = $ArtifactPath
        run_dir = $runDir
        canary_policy = $CanaryPolicy
        run_exit = $runExit
        checker_exit = $checkerExit
        status = $status
        success = ($runExit -eq 0 -and $checkerExit -eq 0 -and $status -eq "PASS")
        reason = if ($runExit -ne 0 -or $checkerExit -ne 0) {
            "producer_nonzero_exit"
        } elseif ($status -ne "PASS") {
            "artifact_status_$status"
        } else {
            ""
        }
    }
}

function Invoke-TripletRerun {
    param(
        [string]$FamilyId,
        [string]$Stage,
        [string]$ArtifactPath
    )
    $parent = Split-Path -Parent $ArtifactPath
    if ($parent) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    & .\scripts\run_family_stage_triplet.ps1 `
        -Family $FamilyId `
        -Stage $Stage `
        -Adapter $Adapter `
        -RunCount 1 `
        -SleepSeconds 0 `
        -Out $ArtifactPath `
        -RunPersonaTrap:$RunPersonaTrap `
        -PersonaProfiles $PersonaProfiles `
        -CheckerExtraArgs @("--min-runs", "1") `
        -ContinueOnRunFailure
    $runExit = $LASTEXITCODE
    $status = Read-SummaryStatus -Path $ArtifactPath
    return [ordered]@{
        family = $FamilyId
        stage = $Stage
        artifact_path = $ArtifactPath
        run_exit = $runExit
        status = $status
        success = ($runExit -eq 0 -and $status -eq "PASS")
        reason = if ($runExit -ne 0) {
            "producer_nonzero_exit"
        } elseif ($status -ne "PASS") {
            "artifact_status_$status"
        } else {
            ""
        }
    }
}

function Get-ArtifactAuditRows {
    $items = @(
        @{ key = "release_gates_dir"; path = "runs\\release_gates"; kind = "dir"; status_enforced = $false },
        @{ key = "drift_holdout_gate"; path = "runs\\release_gates\\drift_holdout_gate.json"; kind = "json"; status_enforced = $false },
        @{ key = "drift_holdout_latest"; path = "runs\\drift_holdout_latest"; kind = "path_or_pointer"; status_enforced = $false },
        @{ key = "drift_holdout_compare_latest"; path = "runs\\drift_holdout_compare_latest.json"; kind = "json"; status_enforced = $false },
        @{ key = "bad_actor_holdout_latest"; path = "runs\\bad_actor_holdout_latest\\summary.json"; kind = "json"; status_enforced = $true },
        @{ key = "ui_same_label_gate"; path = "runs\\ui_same_label_gate.json"; kind = "json"; status_enforced = $true },
        @{ key = "ui_popup_overlay_gate"; path = "runs\\ui_popup_overlay_gate.json"; kind = "json"; status_enforced = $true },
        @{ key = "ui_minipilot_notepad_gate"; path = "runs\\ui_minipilot_notepad_gate.json"; kind = "json"; status_enforced = $true },
        @{ key = "instruction_override_gate"; path = "runs\\release_gates\\instruction_override_gate\\summary.json"; kind = "json"; status_enforced = $true },
        @{ key = "instruction_override_sweep_status"; path = "runs\\release_gates\\instruction_override_gate\\sweep_status.json"; kind = "json"; status_enforced = $true },
        @{ key = "memory_verify_gate"; path = "runs\\release_gates\\memory_verify.json"; kind = "json"; status_enforced = $true },
        @{ key = "memory_verify_sensitivity_gate"; path = "runs\\release_gates\\memory_verify_sensitivity.json"; kind = "json"; status_enforced = $true },
        @{ key = "persona_invariance_gate"; path = "runs\\release_gates\\persona_invariance\\summary.json"; kind = "json"; status_enforced = $true },
        @{ key = "cross_app_intent_preservation_pack_gate"; path = "runs\\release_gates\\cross_app_intent_preservation_pack\\summary.json"; kind = "json"; status_enforced = $true },
        @{ key = "update_burst_release_gate"; path = "runs\\release_gates\\update_burst_full_linear_k16_bucket5_rate0.12\\summary.json"; kind = "json"; status_enforced = $true },
        @{ key = "reliability_signal"; path = "runs\\reliability_signal_latest.json"; kind = "json"; status_enforced = $true },
        @{ key = "compression_reliability"; path = "runs\\compression_reliability_latest.json"; kind = "json"; status_enforced = $true },
        @{ key = "compression_roundtrip_generalization_reliability"; path = "runs\\compression_roundtrip_generalization_reliability_latest.json"; kind = "json"; status_enforced = $true },
        @{ key = "novel_continuity_reliability"; path = "runs\\novel_continuity_reliability_latest.json"; kind = "json"; status_enforced = $true },
        @{ key = "novel_continuity_long_horizon_reliability"; path = "runs\\novel_continuity_long_horizon_reliability_latest.json"; kind = "json"; status_enforced = $true },
        @{ key = "myopic_planning_traps_reliability"; path = "runs\\myopic_planning_traps_reliability_latest.json"; kind = "json"; status_enforced = $true },
        @{ key = "referential_indexing_suite_reliability"; path = "runs\\referential_indexing_suite_reliability_latest.json"; kind = "json"; status_enforced = $true },
        @{ key = "epistemic_calibration_suite_reliability"; path = "runs\\epistemic_calibration_suite_reliability_latest.json"; kind = "json"; status_enforced = $true },
        @{ key = "authority_under_interference_reliability"; path = "runs\\authority_under_interference_reliability_latest.json"; kind = "json"; status_enforced = $true },
        @{ key = "authority_under_interference_hardening_reliability"; path = "runs\\authority_under_interference_hardening_reliability_latest.json"; kind = "json"; status_enforced = $true },
        @{ key = "rpa_mode_switch_reliability"; path = "runs\\rpa_mode_switch_reliability_latest.json"; kind = "json"; status_enforced = $true },
        @{ key = "intent_spec_layer_reliability"; path = "runs\\intent_spec_layer_reliability_latest.json"; kind = "json"; status_enforced = $true },
        @{ key = "noise_escalation_reliability"; path = "runs\\noise_escalation_reliability_latest.json"; kind = "json"; status_enforced = $true },
        @{ key = "implication_coherence_reliability"; path = "runs\\implication_coherence_reliability_latest.json"; kind = "json"; status_enforced = $true },
        @{ key = "agency_preserving_substitution_reliability"; path = "runs\\agency_preserving_substitution_reliability_latest.json"; kind = "json"; status_enforced = $true },
        @{ key = "persona_amalgamation_reliability"; path = "runs\\persona_amalgamation_reliability_latest.json"; kind = "json"; status_enforced = $false },
        @{ key = "real_world_utility_eval"; path = "runs\\real_world_utility_eval_latest.json"; kind = "json"; status_enforced = $true },
        @{ key = "codex_compat_family_matrix"; path = "runs\\codex_compat\\family_matrix.json"; kind = "json"; status_enforced = $true },
        @{ key = "codex_compat_orthogonality_matrix"; path = "runs\\codex_compat\\orthogonality_matrix.json"; kind = "json"; status_enforced = $true },
        @{ key = "codex_compat_rpa_ablation_report"; path = "runs\\codex_compat\\rpa_ablation_report.json"; kind = "json"; status_enforced = $true },
        @{ key = "codex_compat_regression_frontier"; path = "runs\\codex_compat\\regression_frontier.json"; kind = "json"; status_enforced = $true },
        @{ key = "codex_compat_scaffold_backlog"; path = "runs\\codex_compat\\scaffold_backlog.json"; kind = "json"; status_enforced = $true },
        @{ key = "codex_compat_report"; path = "docs\\CODEX_COMPAT_REPORT.md"; kind = "file"; status_enforced = $false },
        @{ key = "codex_next_step_report"; path = "runs\\codex_next_step_report.json"; kind = "json"; status_enforced = $true },
        @{ key = "capability_delta_report"; path = "runs\\capability_delta_report_latest.json"; kind = "json"; status_enforced = $false },
        @{ key = "capability_delta_report_markdown"; path = "runs\\capability_delta_report_latest.md"; kind = "file"; status_enforced = $false },
        @{ key = "optional_metric_inventory"; path = "runs\\latest_optional_metric_inventory"; kind = "pointer"; status_enforced = $false },
        @{ key = "release_quality_snapshot"; path = "runs\\latest_release_quality_snapshot"; kind = "pointer"; status_enforced = $false },
        @{ key = "release_trend_guard"; path = "runs\\latest_release_trend_guard"; kind = "pointer"; status_enforced = $false }
    )

    $rows = @()
    foreach ($item in $items) {
        $exists = Test-Path $item.path
        $status = "missing"
        $target = ""
        if ($exists) {
            if ($item.kind -eq "json") {
                $jsonObj = Read-JsonObject -Path $item.path
                if (-not $jsonObj) {
                    $status = "invalid_json"
                } elseif ($jsonObj.PSObject.Properties.Name -contains "status") {
                    $status = "$($jsonObj.status)"
                } elseif ($jsonObj.PSObject.Properties.Name -contains "overall" -and $jsonObj.overall -and ($jsonObj.overall.PSObject.Properties.Name -contains "status")) {
                    $status = "$($jsonObj.overall.status)"
                } elseif ($jsonObj.PSObject.Properties.Name -contains "result") {
                    $status = "$($jsonObj.result)"
                } else {
                    $status = "n/a"
                }
            } elseif ($item.kind -eq "pointer") {
                try {
                    $target = (Get-Content -Raw -Path $item.path).Trim()
                    if ([string]::IsNullOrWhiteSpace($target)) {
                        $status = "empty_pointer"
                    } elseif (Test-Path $target) {
                        $status = "target_exists"
                    } else {
                        $status = "target_missing"
                    }
                } catch {
                    $status = "unreadable_pointer"
                }
            } elseif ($item.kind -eq "path_or_pointer") {
                $obj = Get-Item $item.path
                if ($obj.PSIsContainer) {
                    $status = "exists"
                } else {
                    try {
                        $target = (Get-Content -Raw -Path $item.path).Trim()
                        if ([string]::IsNullOrWhiteSpace($target)) {
                            $status = "empty_pointer"
                        } elseif (Test-Path $target) {
                            $status = "target_exists"
                        } else {
                            $status = "target_missing"
                        }
                    } catch {
                        $status = "unreadable_pointer"
                    }
                }
            } else {
                $status = "exists"
            }
        }
        $rows += [ordered]@{
            key = $item.key
            path = $item.path
            exists = $exists
            status = $status
            pointer_target = $target
            status_enforced = [bool]$item.status_enforced
        }
    }
    return $rows
}

if (-not (Test-Path $ContractPath)) {
    Write-Error "ContractPath does not exist: $ContractPath"
    exit 1
}
if (-not (Test-Path $ContractSchemaPath)) {
    Write-Error "ContractSchemaPath does not exist: $ContractSchemaPath"
    exit 1
}
python .\scripts\validate_artifact.py --schema $ContractSchemaPath --path $ContractPath | Out-Host
if ($LASTEXITCODE -ne 0) {
    Write-Error "Contract validation failed."
    exit 1
}

$contract = Read-JsonObject -Path $ContractPath
if (-not $contract -or -not $contract.strict_release) {
    Write-Error "Unable to parse strict_release contract: $ContractPath"
    exit 1
}
$strictContract = $contract.strict_release
$requiredFamilies = @($strictContract.required_reliability_families)
$defaultCanaryPolicy = "$($strictContract.canary_policy)"
$iterationContractPath = $ContractPath
if (-not $HonorFreshnessInIteration -and "$($strictContract.freshness_policy)" -eq "must_regenerate_this_run") {
    $iterationContractPath = Join-Path $OutDir "release_gate_contract_iteration.json"
    $iterationContract = $contract | ConvertTo-Json -Depth 20 | ConvertFrom-Json
    $iterationContract.strict_release.freshness_policy = "allow_latest"
    $iterationContract | ConvertTo-Json -Depth 20 | Set-Content -Path $iterationContractPath -Encoding UTF8
    python .\scripts\validate_artifact.py --schema $ContractSchemaPath --path $iterationContractPath | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Iteration contract validation failed: $iterationContractPath"
        exit 1
    }
}

$familySpecById = @{}
foreach ($row in $requiredFamilies) {
    $familySpecById["$($row.id)"] = $row
}

$familyFilterSet = New-Object System.Collections.Generic.HashSet[string]([System.StringComparer]::OrdinalIgnoreCase)
foreach ($id in @($FamilyFilter)) {
    if (-not [string]::IsNullOrWhiteSpace($id)) {
        [void]$familyFilterSet.Add($id.Trim())
    }
}

$rounds = @()
$stopRequested = $false

for ($round = 1; $round -le $MaxRounds; $round++) {
    $matrixRoundPath = Join-Path $OutDir ("release_reliability_matrix_round{0}.json" -f $round)
    $matrixPayload = Invoke-MatrixAssessment -ContractPathArg $iterationContractPath -OutPath $matrixRoundPath -UseExistingArtifacts

    $missingFamilies = @()
    if ($matrixPayload.coverage -and $matrixPayload.coverage.missing_families) {
        $missingFamilies = @($matrixPayload.coverage.missing_families | ForEach-Object { "$_" })
    }
    $failingRows = @()
    if ($matrixPayload.failing_families) {
        $failingRows = @($matrixPayload.failing_families)
    }
    $failingFamilyIds = @($failingRows | ForEach-Object { "$($_.id)" })

    $targetSet = New-Object System.Collections.Generic.HashSet[string]([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($id in $missingFamilies + $failingFamilyIds) {
        if ([string]::IsNullOrWhiteSpace($id)) { continue }
        if ($familyFilterSet.Count -gt 0 -and -not $familyFilterSet.Contains($id)) { continue }
        [void]$targetSet.Add($id)
    }
    $targetFamilies = @($targetSet)
    $rerunResults = @()

    if ($targetFamilies.Count -eq 0 -and "$($matrixPayload.status)" -eq "PASS") {
        $rounds += [ordered]@{
            round = $round
            matrix_path = $matrixRoundPath
            matrix_status = "$($matrixPayload.status)"
            failing_families = $failingFamilyIds
            missing_families = $missingFamilies
            reruns = @()
        }
        break
    }

    if (-not $UseExistingArtifactsOnly) {
        foreach ($familyId in $targetFamilies) {
            if (-not $familySpecById.ContainsKey($familyId)) {
                $rerunResults += [ordered]@{
                    family = $familyId
                    success = $false
                    reason = "family_not_in_contract"
                }
                if ($StopOnFirstFamilyFailure) {
                    $stopRequested = $true
                    break
                }
                continue
            }
            $spec = $familySpecById[$familyId]
            $stage = if ($spec.PSObject.Properties.Name -contains "stage") { "$($spec.stage)" } else { "target" }
            $artifactPath = "$($spec.artifact_path)"
            if ($familyId -eq "compression") {
                $familyCanaryPolicy = Resolve-CanaryPolicy -Family $spec -DefaultCanaryPolicy $defaultCanaryPolicy
                $result = Invoke-CompressionRerun -Stage $stage -ArtifactPath $artifactPath -CanaryPolicy $familyCanaryPolicy
                $rerunResults += $result
                if ($StopOnFirstFamilyFailure -and -not $result.success) {
                    $stopRequested = $true
                    break
                }
                continue
            }
            $result = Invoke-TripletRerun -FamilyId $familyId -Stage $stage -ArtifactPath $artifactPath
            $rerunResults += $result
            if ($StopOnFirstFamilyFailure -and -not $result.success) {
                $stopRequested = $true
                break
            }
        }
    }

    $rounds += [ordered]@{
        round = $round
        matrix_path = $matrixRoundPath
        matrix_status = "$($matrixPayload.status)"
        failing_families = $failingFamilyIds
        missing_families = $missingFamilies
        reruns = $rerunResults
    }

    if ($stopRequested -or $UseExistingArtifactsOnly) {
        break
    }
}

$finalMatrixPath = Join-Path $OutDir "release_reliability_matrix_final.json"
$finalMatrixPayload = Invoke-MatrixAssessment -ContractPathArg $iterationContractPath -OutPath $finalMatrixPath -UseExistingArtifacts

$reliabilityInfo = [ordered]@{
    ran = $false
    path = "runs\\reliability_signal_latest.json"
    status = "SKIP"
    exit_code = $null
}
if (-not $SkipReliabilitySignal -and "$($finalMatrixPayload.status)" -eq "PASS") {
    $reliabilityParams = @{
        Profile = $Profile
    }
    $matrixFamilyById = @{}
    if ($finalMatrixPayload.families) {
        foreach ($row in @($finalMatrixPayload.families)) {
            $matrixFamilyById["$($row.id)"] = $row
        }
    }
    if ($matrixFamilyById.ContainsKey("compression")) {
        $reliabilityParams.CompressionReliability = "$($matrixFamilyById["compression"].artifact_path)"
    }
    if ($matrixFamilyById.ContainsKey("novel_continuity")) {
        $reliabilityParams.NovelReliability = "$($matrixFamilyById["novel_continuity"].artifact_path)"
    }
    if ($matrixFamilyById.ContainsKey("authority_under_interference")) {
        $reliabilityParams.AuthorityInterferenceReliability = "$($matrixFamilyById["authority_under_interference"].artifact_path)"
    }
    if ($matrixFamilyById.ContainsKey("compression_roundtrip_generalization")) {
        $reliabilityParams.CompressionRoundtripReliability = "$($matrixFamilyById["compression_roundtrip_generalization"].artifact_path)"
        $reliabilityParams.RequireCompressionRoundtrip = $true
    }
    if ($matrixFamilyById.ContainsKey("novel_continuity_long_horizon")) {
        $reliabilityParams.NovelLongHorizonReliability = "$($matrixFamilyById["novel_continuity_long_horizon"].artifact_path)"
        $reliabilityParams.RequireNovelLongHorizon = $true
    }
    if ($matrixFamilyById.ContainsKey("myopic_planning_traps")) {
        $reliabilityParams.MyopicPlanningReliability = "$($matrixFamilyById["myopic_planning_traps"].artifact_path)"
        $reliabilityParams.RequireMyopicPlanning = $true
    }
    if ($matrixFamilyById.ContainsKey("referential_indexing_suite")) {
        $reliabilityParams.ReferentialIndexingReliability = "$($matrixFamilyById["referential_indexing_suite"].artifact_path)"
        $reliabilityParams.RequireReferentialIndexing = $true
    }
    if ($matrixFamilyById.ContainsKey("epistemic_calibration_suite")) {
        $reliabilityParams.EpistemicReliability = "$($matrixFamilyById["epistemic_calibration_suite"].artifact_path)"
        $reliabilityParams.RequireEpistemic = $true
    }
    if ($matrixFamilyById.ContainsKey("authority_under_interference_hardening")) {
        $reliabilityParams.AuthorityHardeningReliability = "$($matrixFamilyById["authority_under_interference_hardening"].artifact_path)"
        $reliabilityParams.RequireAuthorityHardening = $true
    }
    if ($matrixFamilyById.ContainsKey("rpa_mode_switch")) {
        $reliabilityParams.RPAModeSwitchReliability = "$($matrixFamilyById["rpa_mode_switch"].artifact_path)"
        $reliabilityParams.RequireRPAModeSwitch = $true
    }
    if ($matrixFamilyById.ContainsKey("intent_spec_layer")) {
        $reliabilityParams.IntentSpecReliability = "$($matrixFamilyById["intent_spec_layer"].artifact_path)"
        $reliabilityParams.RequireIntentSpec = $true
    }
    if ($matrixFamilyById.ContainsKey("noise_escalation")) {
        $reliabilityParams.NoiseEscalationReliability = "$($matrixFamilyById["noise_escalation"].artifact_path)"
        $reliabilityParams.RequireNoiseEscalation = $true
    }
    if ($matrixFamilyById.ContainsKey("implication_coherence")) {
        $reliabilityParams.ImplicationCoherenceReliability = "$($matrixFamilyById["implication_coherence"].artifact_path)"
        $reliabilityParams.RequireImplicationCoherence = $true
    }
    if ($matrixFamilyById.ContainsKey("agency_preserving_substitution")) {
        $reliabilityParams.AgencyPreservingSubstitutionReliability = "$($matrixFamilyById["agency_preserving_substitution"].artifact_path)"
        $reliabilityParams.RequireAgencyPreservingSubstitution = $true
    }

    .\scripts\check_reliability_signal.ps1 @reliabilityParams
    $reliabilityInfo.ran = $true
    $reliabilityInfo.exit_code = $LASTEXITCODE
    if ($LASTEXITCODE -eq 0) {
        $reliabilityInfo.status = "PASS"
    } else {
        $reliabilityInfo.status = "FAIL"
    }
}

$artifactAuditRows = Get-ArtifactAuditRows
$artifactAuditPath = Join-Path $OutDir "artifact_audit.json"
$artifactAuditRows | ConvertTo-Json -Depth 6 | Set-Content -Path $artifactAuditPath -Encoding UTF8

$artifactFailures = @()
$artifactWarnings = @()
foreach ($row in @($artifactAuditRows)) {
    $status = "$($row.status)".ToUpperInvariant()
    if ($status -eq "MISSING" -or $status -eq "INVALID_JSON" -or `
        $status -eq "TARGET_MISSING" -or $status -eq "EMPTY_POINTER" -or $status -eq "UNREADABLE_POINTER") {
        $artifactFailures += $row
        continue
    }
    if ($status -eq "FAIL") {
        if ($row.status_enforced) {
            $artifactFailures += $row
        } else {
            $artifactWarnings += $row
        }
    }
}

$summary = [ordered]@{
    benchmark = "test_check"
    generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    out_dir = $OutDir
    adapter = $Adapter
    profile = $Profile
    contract_path = $ContractPath
    iteration_contract_path = $iterationContractPath
    contract_schema_path = $ContractSchemaPath
    max_rounds = $MaxRounds
    use_existing_artifacts_only = [bool]$UseExistingArtifactsOnly
    stop_on_first_family_failure = [bool]$StopOnFirstFamilyFailure
    honor_freshness_in_iteration = [bool]$HonorFreshnessInIteration
    family_filter = @($familyFilterSet)
    rounds = $rounds
    final_matrix_path = $finalMatrixPath
    final_matrix_status = "$($finalMatrixPayload.status)"
    final_missing_families = @($(if ($finalMatrixPayload.coverage -and $finalMatrixPayload.coverage.missing_families) { @($finalMatrixPayload.coverage.missing_families) } else { @() }))
    final_failing_families = @($(if ($finalMatrixPayload.failing_families) { @($finalMatrixPayload.failing_families) } else { @() }))
    reliability_signal = $reliabilityInfo
    artifact_audit_path = $artifactAuditPath
    artifact_failures = $artifactFailures
    artifact_warnings = $artifactWarnings
}

$overallPass = ("$($finalMatrixPayload.status)" -eq "PASS")
if (-not $SkipReliabilitySignal) {
    if (-not $reliabilityInfo.ran -or $reliabilityInfo.status -ne "PASS") {
        $overallPass = $false
    }
}
if ($FailOnArtifactAudit -and $artifactFailures.Count -gt 0) {
    $overallPass = $false
}
$summary.status = if ($overallPass) { "PASS" } else { "FAIL" }

$summaryPath = Join-Path $OutDir "test_check_summary.json"
$summary | ConvertTo-Json -Depth 8 | Set-Content -Path $summaryPath -Encoding UTF8

Write-Host ("test_check status={0} matrix={1} reliability={2} artifacts_failed={3} summary={4}" -f `
    $summary.status, $summary.final_matrix_status, $summary.reliability_signal.status, $artifactFailures.Count, $summaryPath)
if ($artifactWarnings.Count -gt 0) {
    $warnText = @($artifactWarnings | ForEach-Object { "{0}={1}" -f $_.key, $_.status })
    Write-Host ("artifact_warnings: {0}" -f ($warnText -join ", "))
}

if ($summary.status -ne "PASS") {
    if ($summary.final_failing_families.Count -gt 0) {
        $text = @($summary.final_failing_families | ForEach-Object { "{0}={1}" -f $_.id, $_.status })
        Write-Host ("failing_families: {0}" -f ($text -join ", "))
    }
    exit 1
}
exit 0
