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
    [switch]$UseWall
)

if (-not $OutRoot) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutRoot = "runs\\ui_same_label_wall_$stamp"
}

Write-Host "Running UI same_label stub..."
.\scripts\run_ui_same_label_stub.ps1

Write-Host "Running UI popup_overlay stub..."
.\scripts\run_ui_popup_overlay_stub.ps1

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
        goldevidencebench ui-score --adapter $UiAdapter `
            --fixture .\data\ui_same_label_fixture.jsonl --out (Join-Path $runsDir "ui_same_label_llm_gate.json")
        goldevidencebench ui-score --adapter $UiAdapter `
            --fixture .\data\ui_popup_overlay_fixture.jsonl --out (Join-Path $runsDir "ui_popup_overlay_llm_gate.json")
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
