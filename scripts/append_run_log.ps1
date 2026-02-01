param(
    [string]$RunDir = "",
    [string]$ModelId = "",
    [string]$Notes = ""
)

if (-not $RunDir) {
    Write-Error "Pass -RunDir pointing to a case pack run directory."
    exit 1
}
if (-not (Test-Path $RunDir)) {
    Write-Error "RunDir not found: $RunDir"
    exit 1
}

$summaryPath = Join-Path $RunDir "case_pack_summary.json"
$reportPath = Join-Path $RunDir "case_pack_report.md"
if (-not (Test-Path $summaryPath)) {
    Write-Error "Missing case_pack_summary.json in $RunDir"
    exit 1
}

$summary = Get-Content -Raw -Path $summaryPath | ConvertFrom-Json
$generated = $summary.generated_at
$status = $summary.status

function Find-Step($name) {
    return $summary.steps | Where-Object { $_.name -eq $name } | Select-Object -First 1
}

$ragClosed = Find-Step "rag_closed_book_strict"
$ragOpen = Find-Step "rag_open_book"
$regCase = Find-Step "regression_case"
$badActor = Find-Step "bad_actor_demo"

$logPath = "docs\\RUN_LOG.md"
if (-not (Test-Path $logPath)) {
    Write-Error "Missing docs/RUN_LOG.md"
    exit 1
}

$lines = @()
$lines += ""
$lines += "## $generated - Case pack ($ModelId)"
$lines += ""
$lines += "Run dir: `"$RunDir`""
$lines += ""
$lines += "- Status: $status"
if ($ragClosed) {
    $lines += "- RAG closed-book strict: $($ragClosed.status) (value_acc $($ragClosed.details.value_acc), cite_f1 $($ragClosed.details.cite_f1))"
}
if ($ragOpen) {
    $lines += "- RAG open-book: $($ragOpen.status) (value_acc $($ragOpen.details.value_acc), cite_f1 $($ragOpen.details.cite_f1), tokens/q $($ragOpen.details.tokens_per_q))"
    if ($ragOpen.details.source_pdf) {
        $lines += "- Open-book source_pdf: $($ragOpen.details.source_pdf)"
    }
}
if ($regCase) { $lines += "- Internal tooling regression case: $($regCase.status)" }
if ($badActor) { $lines += "- Compliance bad-actor demo: $($badActor.status)" }
if ($Notes) { $lines += "- Notes: $Notes" }

Add-Content -Path $logPath -Value ($lines -join "`n")
Write-Host "Appended run log to $logPath"
Write-Host "Report: $reportPath"
