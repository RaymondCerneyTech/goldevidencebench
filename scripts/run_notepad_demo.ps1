param(
    [Parameter(Mandatory = $true)]
    [string]$ModelPath,
    [string]$Text = "Hello from GoldEvidenceBench.",
    [string]$FilePath = "",
    [string]$FixturePath = "data\\ui_minipilot_notepad_fixture.jsonl",
    [string]$TaskId = "task_ui_notepad_save",
    [string]$OutPlan = "runs\\notepad_demo_plan.json",
    [int]$DelayMs = 500,
    [switch]$DryRun
)

function Escape-SendKeys([string]$value) {
    if ($null -eq $value) {
        return ""
    }
    return ($value -replace '([+\^%~\(\)\{\}\[\]])', '{$1}')
}

$scriptPath = "scripts\\select_ui_plan.py"
if (-not (Test-Path $scriptPath)) {
    Write-Error "Missing $scriptPath. Ensure scripts/select_ui_plan.py exists."
    exit 1
}

if (-not (Test-Path $FixturePath)) {
    Write-Error "Fixture not found: $FixturePath"
    exit 1
}

if (-not (Test-Path $ModelPath)) {
    Write-Error "Model not found: $ModelPath"
    exit 1
}

if ([string]::IsNullOrWhiteSpace($FilePath)) {
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $FilePath = Join-Path $env:TEMP "notes_$timestamp.txt"
}

$outDir = Split-Path $OutPlan -Parent
if ($outDir -and -not (Test-Path $outDir)) {
    New-Item -ItemType Directory -Path $outDir -Force | Out-Null
}

Write-Host "Selecting UI plan..."
python .\scripts\select_ui_plan.py --fixture $FixturePath --task-id $TaskId --model $ModelPath --out $OutPlan
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$plan = Get-Content $OutPlan | ConvertFrom-Json
Write-Host "Plan saved to $OutPlan"

if ($DryRun) {
    Write-Host "DryRun enabled; no UI actions will be executed."
    exit 0
}

Add-Type -AssemblyName System.Windows.Forms

Write-Host "Launching Notepad..."
$process = Start-Process notepad.exe -PassThru
Start-Sleep -Milliseconds $DelayMs
try {
    Add-Type -AssemblyName Microsoft.VisualBasic
    [Microsoft.VisualBasic.Interaction]::AppActivate($process.Id) | Out-Null
} catch {
    Write-Warning "Unable to activate Notepad window."
}

Set-Clipboard -Value $Text

$sawInput = $false
$sawSave = $false

foreach ($step in $plan.steps) {
    $action = $step.selected_id
    switch ($action) {
        "doc_textarea" {
            [System.Windows.Forms.SendKeys]::SendWait("^{v}")
        }
        "menu_file" {
            [System.Windows.Forms.SendKeys]::SendWait("%f")
        }
        "file_save_as" {
            [System.Windows.Forms.SendKeys]::SendWait("a")
        }
        "file_save" {
            [System.Windows.Forms.SendKeys]::SendWait("^s")
        }
        "input_filename" {
            $sawInput = $true
            $escapedPath = Escape-SendKeys $FilePath
            [System.Windows.Forms.SendKeys]::SendWait("^a")
            [System.Windows.Forms.SendKeys]::SendWait($escapedPath)
        }
        "btn_save" {
            $sawSave = $true
            [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
        }
        default {
            Write-Warning "Unknown action_id: $action"
        }
    }
    Start-Sleep -Milliseconds $DelayMs
}

if ($sawInput -and -not $sawSave) {
    Write-Warning "Plan omitted btn_save; sending Enter as a fallback."
    [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
    Start-Sleep -Milliseconds $DelayMs
}

Write-Host "Done. Saved to $FilePath"
