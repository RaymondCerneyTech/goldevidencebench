param(
    [string]$ModelPath = "",
    [string]$Text = "Hello from GoldEvidenceBench.",
    [string]$FilePath = "",
    [ValidateSet("prompt","rename","overwrite")]
    [string]$OnExistingFile = "prompt",
    [ValidateSet("greedy","policy","llm")]
    [string]$Planner = "greedy",
    [ValidateSet("paste","type")]
    [string]$InputMode = "paste",
    [ValidateRange(1,200)]
    [int]$TypeChunkSize = 40,
    [int]$TypeDelayMs = 15,
    [int]$MaxTextLength = 2000,
    [switch]$AllowNonAscii,
    [switch]$AllowEmptyText,
    [switch]$DisableKeystrokeGate,
    [string]$FixturePath = "data\\ui_minipilot_notepad_fixture.jsonl",
    [string]$TaskId = "task_ui_notepad_save",
    [string]$OutPlan = "runs\\notepad_demo_plan.json",
    [int]$DelayMs = 500,
    [switch]$CloseAfterSave,
    [switch]$VerifySaved,
    [ValidateRange(500,30000)]
    [int]$VerifyTimeoutMs = 5000,
    [ValidateRange(50,5000)]
    [int]$VerifyPollMs = 200,
    [switch]$DryRun
)

function Escape-SendKeys([string]$value) {
    if ($null -eq $value) {
        return ""
    }
    return ($value -replace '([+\^%~\(\)\{\}\[\]])', '{$1}')
}

function Send-TextAsKeys([string]$value, [int]$chunkSize, [int]$delayMs) {
    if ([string]::IsNullOrEmpty($value)) {
        return
    }
    $normalized = $value -replace "`r`n", "`n" -replace "`r", "`n"
    $lines = $normalized -split "`n", -1
    for ($lineIndex = 0; $lineIndex -lt $lines.Length; $lineIndex++) {
        $line = $lines[$lineIndex]
        $offset = 0
        while ($offset -lt $line.Length) {
            $take = [Math]::Min($chunkSize, $line.Length - $offset)
            $chunk = $line.Substring($offset, $take)
            $escaped = Escape-SendKeys $chunk
            [System.Windows.Forms.SendKeys]::SendWait($escaped)
            if ($delayMs -gt 0) {
                Start-Sleep -Milliseconds $delayMs
            }
            $offset += $take
        }
        if ($lineIndex -lt ($lines.Length - 1)) {
            [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
            if ($delayMs -gt 0) {
                Start-Sleep -Milliseconds $delayMs
            }
        }
    }
}

function New-UniqueFilePath([string]$path) {
    $dir = Split-Path $path -Parent
    $base = [System.IO.Path]::GetFileNameWithoutExtension($path)
    $ext = [System.IO.Path]::GetExtension($path)
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $candidate = Join-Path $dir "${base}_${stamp}${ext}"
    $counter = 1
    while (Test-Path $candidate) {
        $candidate = Join-Path $dir "${base}_${stamp}_$counter${ext}"
        $counter += 1
    }
    return $candidate
}

function Normalize-Text([string]$value) {
    if ($null -eq $value) {
        return ""
    }
    return ($value -replace "`r`n", "`n" -replace "`r", "`n")
}

function Wait-ForFile([string]$path, [int]$timeoutMs, [int]$pollMs) {
    $deadline = (Get-Date).AddMilliseconds($timeoutMs)
    while ((Get-Date) -lt $deadline) {
        if (Test-Path $path) {
            return $true
        }
        Start-Sleep -Milliseconds $pollMs
    }
    return (Test-Path $path)
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

if ($Planner -eq "llm") {
    if ([string]::IsNullOrWhiteSpace($ModelPath)) {
        Write-Error "ModelPath is required when Planner is set to llm."
        exit 1
    }
    if (-not (Test-Path $ModelPath)) {
        Write-Error "Model not found: $ModelPath"
        exit 1
    }
}

if ([string]::IsNullOrWhiteSpace($FilePath)) {
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $FilePath = Join-Path $env:TEMP "notes_$timestamp.txt"
}

$confirmOverwrite = $false
if (Test-Path $FilePath) {
    switch ($OnExistingFile.ToLowerInvariant()) {
        "rename" {
            $FilePath = New-UniqueFilePath $FilePath
            Write-Host "Target exists; using new path $FilePath"
        }
        "overwrite" {
            $confirmOverwrite = $true
            Write-Host "Target exists; will overwrite after prompt."
        }
        default {
            while ($true) {
                $choice = Read-Host "File exists at $FilePath. [R]ename, [O]verwrite, [C]ancel"
                if ([string]::IsNullOrWhiteSpace($choice)) {
                    $choice = "R"
                }
                switch ($choice.Trim().ToUpperInvariant()) {
                    "R" {
                        $FilePath = New-UniqueFilePath $FilePath
                        Write-Host "Using new path $FilePath"
                        break
                    }
                    "O" {
                        $confirmOverwrite = $true
                        Write-Host "Will overwrite after prompt."
                        break
                    }
                    "C" {
                        Write-Host "Canceled."
                        exit 1
                    }
                    default {
                        Write-Host "Please enter R, O, or C."
                        continue
                    }
                }
                break
            }
        }
    }
}

$outDir = Split-Path $OutPlan -Parent
if ($outDir -and -not (Test-Path $outDir)) {
    New-Item -ItemType Directory -Path $outDir -Force | Out-Null
}

Write-Host "Selecting UI plan..."
$planArgs = @("--fixture", $FixturePath, "--task-id", $TaskId, "--planner", $Planner, "--out", $OutPlan)
if ($Planner -eq "llm") {
    $planArgs += @("--model", $ModelPath)
}
python .\scripts\select_ui_plan.py @planArgs
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$plan = Get-Content $OutPlan | ConvertFrom-Json
Write-Host "Plan saved to $OutPlan"

if ($DryRun) {
    Write-Host "DryRun enabled; no UI actions will be executed."
    exit 0
}

if (-not $DisableKeystrokeGate) {
    $gateScript = Join-Path $PSScriptRoot "keystroke_gate.py"
    if (-not (Test-Path $gateScript)) {
        Write-Error "Missing keystroke gate script: $gateScript"
        exit 1
    }
    $gateArgs = @("--mode", "text", "--text", $Text, "--max-len", $MaxTextLength)
    if ($AllowNonAscii) {
        $gateArgs += "--allow-non-ascii"
    }
    if ($AllowEmptyText) {
        $gateArgs += "--allow-empty"
    }
    $gateJson = & python $gateScript @gateArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Keystroke gate failed to run."
        exit 1
    }
    $gate = ($gateJson | Out-String).Trim() | ConvertFrom-Json
    if (-not $gate.ok) {
        Write-Warning ("Keystroke gate blocked: {0}" -f $gate.reason)
        exit 1
    }
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

if ($InputMode -eq "type") {
    Write-Host "Typing text (InputMode=type, chunk=$TypeChunkSize delay=${TypeDelayMs}ms)"
} else {
    Set-Clipboard -Value $Text
}

$sawInput = $false
$sawSave = $false
$planActions = @()
foreach ($step in $plan.steps) {
    $planActions += $step.selected_id
}
$forceSaveAfterInput = ($planActions -contains "input_filename") -and -not ($planActions -contains "btn_save")

function Confirm-OverwriteIfNeeded {
    if ($confirmOverwrite) {
        Start-Sleep -Milliseconds $DelayMs
        [System.Windows.Forms.SendKeys]::SendWait("%y")
    }
}

foreach ($step in $plan.steps) {
    $action = $step.selected_id
    if ([string]::IsNullOrWhiteSpace($action)) {
        Write-Warning "Plan abstained on a step; skipping."
        Start-Sleep -Milliseconds $DelayMs
        continue
    }
    switch ($action) {
        "doc_textarea" {
            if ($InputMode -eq "type") {
                Send-TextAsKeys $Text $TypeChunkSize $TypeDelayMs
            } else {
                [System.Windows.Forms.SendKeys]::SendWait("^{v}")
            }
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
            if ($forceSaveAfterInput) {
                Write-Warning "Plan omitted btn_save; sending Alt+S after filename entry."
                $sawSave = $true
                [System.Windows.Forms.SendKeys]::SendWait("%s")
                Confirm-OverwriteIfNeeded
            }
        }
        "btn_save" {
            $sawSave = $true
            [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
            Confirm-OverwriteIfNeeded
        }
        default {
            Write-Warning "Unknown action_id: $action"
        }
    }
    Start-Sleep -Milliseconds $DelayMs
}

if ($sawInput -and -not $sawSave) {
    Write-Warning "Plan omitted btn_save; sending Alt+S as a fallback."
    [System.Windows.Forms.SendKeys]::SendWait("%s")
    Confirm-OverwriteIfNeeded
    Start-Sleep -Milliseconds $DelayMs
}

Write-Host "Done. Saved to $FilePath"

if ($VerifySaved) {
    if (-not $sawSave) {
        Write-Warning "VerifySaved requested but no save action was taken."
    } else {
        if (-not (Wait-ForFile $FilePath $VerifyTimeoutMs $VerifyPollMs)) {
            Write-Warning "VerifySaved failed: file not found after ${VerifyTimeoutMs}ms."
        } else {
            try {
                $actual = Normalize-Text (Get-Content -Path $FilePath -Raw)
                $expected = Normalize-Text $Text
                if (-not $actual.Contains($expected)) {
                    Write-Warning "VerifySaved failed: file content does not include expected text."
                } else {
                    Write-Host "VerifySaved OK: file exists and contains expected text."
                }
            } catch {
                Write-Warning "VerifySaved failed: unable to read file content."
            }
        }
    }
}

if ($CloseAfterSave) {
    if (-not $sawSave) {
        Write-Warning "CloseAfterSave requested but no save action was taken; leaving Notepad open."
        exit 0
    }
    try {
        [Microsoft.VisualBasic.Interaction]::AppActivate($process.Id) | Out-Null
    } catch {
        Write-Warning "Unable to re-activate Notepad window before closing."
    }
    Write-Host "Closing Notepad..."
    $process.CloseMainWindow() | Out-Null
    Start-Sleep -Milliseconds $DelayMs
    if (-not $process.HasExited) {
        [System.Windows.Forms.SendKeys]::SendWait("%{F4}")
        Start-Sleep -Milliseconds $DelayMs
    }
    if (-not $process.HasExited) {
        Write-Warning "Notepad is still open; check for a save prompt."
    }
}
