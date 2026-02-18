param(
    [string]$ContractPath = "configs\\release_gate_contract.json",
    [string]$ContractSchemaPath = "schemas\\release_gate_contract.schema.json",
    [string]$Adapter = "goldevidencebench.adapters.llama_server_adapter:create_adapter",
    [string]$Out = "runs\\release_reliability_matrix.json",
    [switch]$UseExistingArtifacts,
    [bool]$RunPersonaTrap = $true,
    [string]$PersonaProfiles = "persona_confident_expert,persona_creative_writer,persona_ultra_brief,persona_overly_helpful",
    [switch]$FailOnMatrixFail,
    [switch]$ContinueOnRunFailure
)

$ErrorActionPreference = "Stop"

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

function Invoke-TripletFamily {
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
        -ContinueOnRunFailure
    return $LASTEXITCODE
}

function Invoke-CompressionReliability {
    param(
        [string]$Stage,
        [string]$ArtifactPath,
        [ValidateSet("strict","triage")]
        [string]$CanaryPolicy
    )
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $runDir = "runs\\compression_families_${stamp}_${Stage}_release_matrix"
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

    $success = ($runExit -eq 0 -and $checkerExit -eq 0)
    if (-not $success -and -not $ContinueOnRunFailure) {
        throw "compression reliability production failed (run_exit=$runExit checker_exit=$checkerExit)"
    }
    if (-not $success) {
        Write-Warning "compression reliability production had non-zero exit (run_exit=$runExit checker_exit=$checkerExit)."
    }
    return [ordered]@{
        run_exit = $runExit
        checker_exit = $checkerExit
        success = $success
    }
}

function Parse-UtcTimestamp {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) {
        return $null
    }
    $dto = [datetimeoffset]::MinValue
    $ok = [datetimeoffset]::TryParse($Text, [ref]$dto)
    if (-not $ok) {
        return $null
    }
    return $dto.UtcDateTime
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

if (-not (Test-Path $ContractPath)) {
    Write-Error "Release gate contract not found: $ContractPath"
    exit 1
}
if (-not (Test-Path $ContractSchemaPath)) {
    Write-Error "Release gate contract schema not found: $ContractSchemaPath"
    exit 1
}
python .\scripts\validate_artifact.py --schema $ContractSchemaPath --path $ContractPath | Out-Host
if ($LASTEXITCODE -ne 0) {
    Write-Error "Release gate contract schema validation failed."
    exit 1
}
$contract = Read-JsonObject -Path $ContractPath
if (-not $contract) {
    Write-Error "Release gate contract is unreadable: $ContractPath"
    exit 1
}
if (-not $contract.strict_release) {
    Write-Error "Release gate contract missing strict_release block: $ContractPath"
    exit 1
}
$strictContract = $contract.strict_release
$requiredFamilies = @($strictContract.required_reliability_families)
if ($requiredFamilies.Count -eq 0) {
    Write-Error "Release gate contract has no required_reliability_families."
    exit 1
}

$freshnessPolicy = "$($strictContract.freshness_policy)"
$canaryPolicy = "$($strictContract.canary_policy)"
$matrixStartUtc = (Get-Date).ToUniversalTime()
$generatedAtUtc = $matrixStartUtc.ToString("o")

$familyRows = @()
$missingFamilies = New-Object System.Collections.Generic.List[string]
$failingFamilies = New-Object System.Collections.Generic.List[object]
$freshnessViolations = New-Object System.Collections.Generic.List[string]

foreach ($family in $requiredFamilies) {
    $id = "$($family.id)"
    $artifactPath = "$($family.artifact_path)"
    $stage = if ($family.PSObject.Properties.Name -contains "stage") { "$($family.stage)" } else { "target" }
    $familyCanaryPolicy = Resolve-CanaryPolicy -Family $family -DefaultCanaryPolicy $canaryPolicy
    $allowedStatuses = @($family.allowed_statuses | ForEach-Object { "$_" })
    if ($allowedStatuses.Count -eq 0) {
        $allowedStatuses = @("PASS")
    }
    $producedThisRun = $false
    $producerAttempted = $false
    $producerSucceeded = $false
    $artifactTimestampFresh = $false
    $producerExitCode = 0

    if (-not $UseExistingArtifacts) {
        $producerAttempted = $true
        try {
            if ($id -eq "compression") {
                $compressionResult = Invoke-CompressionReliability -Stage $stage -ArtifactPath $artifactPath -CanaryPolicy $familyCanaryPolicy
                if ($compressionResult) {
                    $producerSucceeded = [bool]$compressionResult.success
                    if ($compressionResult.checker_exit -ne $null) {
                        $producerExitCode = [int]$compressionResult.checker_exit
                    } elseif ($compressionResult.run_exit -ne $null) {
                        $producerExitCode = [int]$compressionResult.run_exit
                    }
                }
            } else {
                $producerExitCode = Invoke-TripletFamily -FamilyId $id -Stage $stage -ArtifactPath $artifactPath
                $producerSucceeded = ($producerExitCode -eq 0)
                if ($producerExitCode -ne 0 -and -not $ContinueOnRunFailure) {
                    throw "family producer failed for '$id' with exit code $producerExitCode"
                }
                if ($producerExitCode -ne 0) {
                    Write-Warning "$id family producer exited non-zero ($producerExitCode)."
                }
            }
        } catch {
            $producerSucceeded = $false
            if (-not $ContinueOnRunFailure) {
                throw
            }
            Write-Warning "family producer exception for '$id': $($_.Exception.Message)"
        }
        if ($producerSucceeded -and (Test-Path $artifactPath)) {
            try {
                $artifactTimestampFresh = ((Get-Item $artifactPath).LastWriteTimeUtc -ge $matrixStartUtc)
            } catch {
                $artifactTimestampFresh = $false
            }
        }
        if ($producerSucceeded -and $artifactTimestampFresh) {
            $producedThisRun = $true
        }
    }

    $status = "MISSING"
    $firstFailureReason = "artifact_missing"
    $artifactGeneratedAtUtc = $null
    $artifactGeneratedAtUtcValue = $null
    $freshnessOk = $true
    $freshnessReason = ""
    $summaryObj = Read-JsonObject -Path $artifactPath
    if ($summaryObj) {
        $statusRaw = "$($summaryObj.status)".Trim()
        if (-not [string]::IsNullOrWhiteSpace($statusRaw)) {
            $status = $statusRaw
        } else {
            $status = "UNKNOWN"
        }
        $failures = @($summaryObj.failures)
        if ($failures.Count -gt 0) {
            $firstFailureReason = "$($failures[0])"
        } elseif ($status -ne "PASS") {
            $firstFailureReason = "status=$status"
        } else {
            $firstFailureReason = ""
        }
        if ($summaryObj.generated_at_utc) {
            $artifactGeneratedAtUtc = "$($summaryObj.generated_at_utc)"
        } else {
            try {
                $artifactGeneratedAtUtc = (Get-Item $artifactPath).LastWriteTimeUtc.ToString("o")
            } catch {
                $artifactGeneratedAtUtc = $null
            }
        }
        $artifactGeneratedAtUtcValue = Parse-UtcTimestamp -Text $artifactGeneratedAtUtc
    }

    if ($status -eq "MISSING") {
        $missingFamilies.Add($id)
    }
    if ($allowedStatuses -notcontains $status) {
        $failingFamilies.Add([ordered]@{
            id = $id
            status = $status
            canary_policy = $familyCanaryPolicy
            first_failure_reason = $firstFailureReason
            allowed_statuses = $allowedStatuses
        })
    }
    if ($freshnessPolicy -eq "must_regenerate_this_run") {
        if (-not $producedThisRun) {
            $freshnessOk = $false
            if (-not $producerAttempted) {
                $freshnessReason = "not_regenerated_in_this_run"
            } elseif (-not $producerSucceeded) {
                $freshnessReason = "producer_failed_or_nonzero_exit"
            } elseif (-not (Test-Path $artifactPath)) {
                $freshnessReason = "artifact_missing_after_producer"
            } elseif (-not $artifactTimestampFresh) {
                $freshnessReason = "artifact_timestamp_before_matrix_start"
            } else {
                $freshnessReason = "artifact_not_marked_fresh"
            }
        } elseif ($null -eq $artifactGeneratedAtUtcValue -or $artifactGeneratedAtUtcValue -lt $matrixStartUtc) {
            $freshnessOk = $false
            if ($null -eq $artifactGeneratedAtUtcValue) {
                $freshnessReason = "generated_at_utc_missing_or_unparseable"
            } else {
                $freshnessReason = "generated_at_utc_before_matrix_start"
            }
        }
    }
    if (-not $freshnessOk) {
        if ([string]::IsNullOrWhiteSpace($freshnessReason)) {
            $freshnessReason = "freshness_check_failed"
        }
        $freshnessViolations.Add("${id}:$freshnessReason")
    }

    if ($status -eq "MISSING") {
        $firstFailureReason = "artifact_missing"
    } elseif ($allowedStatuses -notcontains $status -and [string]::IsNullOrWhiteSpace($firstFailureReason)) {
        $firstFailureReason = "status=$status"
    } elseif (-not $freshnessOk -and [string]::IsNullOrWhiteSpace($firstFailureReason)) {
        $firstFailureReason = "freshness:$freshnessReason"
    }

    $familyRows += [ordered]@{
        id = $id
        artifact_path = $artifactPath
        stage = $stage
        canary_policy = $familyCanaryPolicy
        allowed_statuses = $allowedStatuses
        status = $status
        first_failure_reason = $firstFailureReason
        produced_in_this_run = $producedThisRun
        producer_attempted = $producerAttempted
        producer_succeeded = $producerSucceeded
        artifact_timestamp_fresh = $artifactTimestampFresh
        freshness_ok = $freshnessOk
        freshness_reason = $freshnessReason
        generated_at_utc = $artifactGeneratedAtUtc
        producer_exit_code = $producerExitCode
    }
}

$requiredTotal = $requiredFamilies.Count
$producedTotal = @($familyRows | Where-Object { "$($_.status)" -ne "MISSING" }).Count
$coverageRate = if ($requiredTotal -gt 0) { [double]$producedTotal / [double]$requiredTotal } else { 0.0 }

$matrixStatus = "PASS"
$matrixFailures = @()
if ($missingFamilies.Count -gt 0) {
    $matrixStatus = "FAIL"
    $matrixFailures += "missing_families: " + ($missingFamilies -join ", ")
}
if ($failingFamilies.Count -gt 0) {
    $matrixStatus = "FAIL"
    $matrixFailures += "failing_families: " + (($failingFamilies | ForEach-Object { "$($_.id)=$($_.status)" }) -join ", ")
}
if ($freshnessViolations.Count -gt 0) {
    $matrixStatus = "FAIL"
    $matrixFailures += "freshness_violations: " + ($freshnessViolations -join ", ")
}

$adapterFingerprint = [ordered]@{
    adapter = $Adapter
    model_path = $env:GOLDEVIDENCEBENCH_MODEL
    uses_llama_server_adapter = [bool]($Adapter -like "*llama_server_adapter*")
    uses_mock_adapter = [bool]($Adapter -like "*mock_adapter*")
}

$payload = [ordered]@{
    benchmark = "release_reliability_matrix"
    contract_id = "$($contract.contract_id)"
    contract_version = "$($contract.version)"
    contract_path = $ContractPath
    generated_at_utc = $generatedAtUtc
    matrix_start_utc = $generatedAtUtc
    adapter_fingerprint = $adapterFingerprint
    strict_release = [ordered]@{
        freshness_policy = $freshnessPolicy
        canary_policy = $canaryPolicy
        use_existing_artifacts = [bool]$UseExistingArtifacts
    }
    coverage = [ordered]@{
        required_total = $requiredTotal
        produced_total = $producedTotal
        coverage_rate = $coverageRate
        missing_families = @($missingFamilies)
    }
    families = $familyRows
    failing_families = $failingFamilies
    freshness_violations = @($freshnessViolations)
    status = $matrixStatus
    failures = $matrixFailures
}

$outDir = Split-Path -Parent $Out
if ($outDir) {
    New-Item -ItemType Directory -Path $outDir -Force | Out-Null
}
$payload | ConvertTo-Json -Depth 8 | Set-Content -Path $Out -Encoding UTF8

Write-Host "Release reliability matrix"
Write-Host "Contract: $ContractPath"
Write-Host "Adapter: $Adapter"
Write-Host "Required families: $requiredTotal"
Write-Host "Produced families: $producedTotal"
Write-Host ("Status: {0}" -f $matrixStatus)
if ($matrixFailures.Count -gt 0) {
    $matrixFailures | ForEach-Object { Write-Host ("- {0}" -f $_) }
}
Write-Host "Wrote $Out"
if ($FailOnMatrixFail -and $matrixStatus -ne "PASS") {
    exit 1
}
exit 0
