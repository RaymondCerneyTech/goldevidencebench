param(
    [string]$Expression = "12+34",
    [string]$Expected = "46",
    [int]$DelayMs = 200,
    [int]$ActivateTimeoutMs = 5000,
    [int]$ActivatePollMs = 100,
    [int]$FocusTimeoutMs = 15000,
    [string]$WindowTitle = "Calculator",
    [int]$MaxExpressionLength = 64,
    [switch]$DisableKeystrokeGate,
    [switch]$CloseAfter,
    [switch]$VerifyResult,
    [int]$VerifyTimeoutMs = 3000,
    [int]$VerifyPollMs = 100,
    [switch]$DryRun
)

function Escape-SendKeys([string]$value) {
    if ($null -eq $value) {
        return ""
    }
    return ($value -replace '([+\^%~\(\)\{\}\[\]])', '{$1}')
}

function Wait-ClipboardContains([string]$expected, [int]$timeoutMs, [int]$pollMs) {
    $deadline = (Get-Date).AddMilliseconds($timeoutMs)
    while ((Get-Date) -lt $deadline) {
        try {
            $clip = Get-Clipboard
            if ($clip -and ($clip.ToString().Trim() -eq $expected)) {
                return $true
            }
        } catch {
        }
        Start-Sleep -Milliseconds $pollMs
    }
    return $false
}

function Wait-ForMainWindow([System.Diagnostics.Process]$proc, [int]$timeoutMs, [int]$pollMs) {
    $deadline = (Get-Date).AddMilliseconds($timeoutMs)
    while ((Get-Date) -lt $deadline) {
        if ($proc.HasExited) {
            return $false
        }
        $proc.Refresh()
        if ($proc.MainWindowHandle -ne 0) {
            return $true
        }
        Start-Sleep -Milliseconds $pollMs
    }
    $proc.Refresh()
    return ($proc.MainWindowHandle -ne 0)
}

function Ensure-Win32 {
    if ("Win32" -as [type]) {
        return
    }
    Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Win32 {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder text, int maxLength);
    [DllImport("user32.dll")] public static extern int GetWindowTextLength(IntPtr hWnd);
}
"@
}

function Try-Activate([System.Diagnostics.Process]$proc, [int]$timeoutMs, [int]$pollMs) {
    if (-not (Wait-ForMainWindow $proc $timeoutMs $pollMs)) {
        return $false
    }
    try {
        Add-Type -AssemblyName Microsoft.VisualBasic
        return [Microsoft.VisualBasic.Interaction]::AppActivate($proc.Id)
    } catch {
        return $false
    }
}

function Force-Activate([System.Diagnostics.Process]$proc, [int]$timeoutMs, [int]$pollMs) {
    if (-not (Wait-ForMainWindow $proc $timeoutMs $pollMs)) {
        return $false
    }
    try {
        Ensure-Win32
    } catch {
    }
    $proc.Refresh()
    $handle = $proc.MainWindowHandle
    if ($handle -eq 0) {
        return $false
    }
    try {
        [Win32]::ShowWindow($handle, 5) | Out-Null
        [Win32]::SetForegroundWindow($handle) | Out-Null
    } catch {
    }
    Start-Sleep -Milliseconds $DelayMs
    try {
        return ([Win32]::GetForegroundWindow() -eq $handle)
    } catch {
        return $true
    }
}

function Get-ForegroundTitle {
    try {
        Ensure-Win32
        $handle = [Win32]::GetForegroundWindow()
        if ($handle -eq 0) {
            return ""
        }
        $length = [Win32]::GetWindowTextLength($handle)
        if ($length -le 0) {
            return ""
        }
        $builder = New-Object System.Text.StringBuilder ($length + 1)
        [Win32]::GetWindowText($handle, $builder, $builder.Capacity) | Out-Null
        return $builder.ToString()
    } catch {
        return ""
    }
}

function Find-CalculatorProcess([string]$title) {
    $proc = Get-Process | Where-Object { $_.MainWindowTitle -like "*$title*" } | Select-Object -First 1
    return $proc
}

function Wait-ForCalculatorForeground([string]$title, [int]$timeoutMs, [int]$pollMs) {
    $deadline = (Get-Date).AddMilliseconds($timeoutMs)
    while ((Get-Date) -lt $deadline) {
        $current = Get-ForegroundTitle
        if ($current -like "*$title*") {
            return $true
        }
        Start-Sleep -Milliseconds $pollMs
    }
    return $false
}

function Activate-Calculator([System.Diagnostics.Process]$proc, [string]$title, [int]$timeoutMs, [int]$pollMs) {
    if (Force-Activate $proc $timeoutMs $pollMs) {
        return $true
    }
    $altProc = Find-CalculatorProcess $title
    if ($altProc) {
        try {
            Ensure-Win32
            $altProc.Refresh()
            if ($altProc.MainWindowHandle -ne 0) {
                [Win32]::ShowWindow($altProc.MainWindowHandle, 5) | Out-Null
                [Win32]::SetForegroundWindow($altProc.MainWindowHandle) | Out-Null
            } else {
                Add-Type -AssemblyName Microsoft.VisualBasic
                [Microsoft.VisualBasic.Interaction]::AppActivate($altProc.Id) | Out-Null
            }
        } catch {
        }
    }
    return Wait-ForCalculatorForeground $title $timeoutMs $pollMs
}

Write-Host "Launching Calculator..."
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
    $gateJson = & python $gateScript --mode calculator --text $Expression --max-len $MaxExpressionLength
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

$process = Start-Process calc.exe -PassThru
Start-Sleep -Milliseconds $DelayMs
if (-not (Activate-Calculator $process $WindowTitle $ActivateTimeoutMs $ActivatePollMs)) {
    Write-Warning "Unable to activate Calculator window. Click it now to continue."
    if (-not (Wait-ForCalculatorForeground $WindowTitle $FocusTimeoutMs $ActivatePollMs)) {
        Write-Warning "Calculator never became active; stopping to avoid sending keys to the wrong window."
        exit 1
    }
}

[System.Windows.Forms.SendKeys]::SendWait("{ESC}")
Start-Sleep -Milliseconds $DelayMs

$escaped = Escape-SendKeys $Expression
[System.Windows.Forms.SendKeys]::SendWait($escaped)
Start-Sleep -Milliseconds $DelayMs
[System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
Start-Sleep -Milliseconds $DelayMs
[System.Windows.Forms.SendKeys]::SendWait("^c")
Start-Sleep -Milliseconds $DelayMs

Write-Host "Expression: $Expression"
if ($VerifyResult) {
    if ([string]::IsNullOrWhiteSpace($Expected)) {
        Write-Warning "VerifyResult requested but Expected is empty."
    } else {
        if (Wait-ClipboardContains $Expected $VerifyTimeoutMs $VerifyPollMs) {
            Write-Host "VerifyResult OK: clipboard matches $Expected"
        } else {
            Write-Warning "VerifyResult failed: clipboard did not match $Expected"
        }
    }
}

if ($CloseAfter) {
    Write-Host "Closing Calculator..."
    $closeProc = Find-CalculatorProcess $WindowTitle
    if ($closeProc) {
        $null = Activate-Calculator $closeProc $WindowTitle $ActivateTimeoutMs $ActivatePollMs
    } else {
        $null = Activate-Calculator $process $WindowTitle $ActivateTimeoutMs $ActivatePollMs
    }
    Start-Sleep -Milliseconds $DelayMs
    [System.Windows.Forms.SendKeys]::SendWait("%{F4}")
    Start-Sleep -Milliseconds $DelayMs
    $remaining = Find-CalculatorProcess $WindowTitle
    if ($remaining) {
        $remaining.Refresh()
        if ($remaining.MainWindowHandle -ne 0 -and -not [string]::IsNullOrWhiteSpace($remaining.MainWindowTitle)) {
            Write-Warning "Calculator is still open; close it manually if needed."
        }
    }
}
