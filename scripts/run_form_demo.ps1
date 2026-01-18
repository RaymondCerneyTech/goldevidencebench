param(
    [string]$ModelPath = "",
    [string]$Username = "demo_user",
    [string]$Password = "demo_pass123",
    [switch]$RememberMe,
    [string]$OutputPath = "",
    [ValidateSet("prompt","rename","overwrite")]
    [string]$OnExistingFile = "prompt",
    [int]$DelayMs = 200,
    [int]$ActivateTimeoutMs = 5000,
    [int]$ActivatePollMs = 100,
    [int]$FocusTimeoutMs = 15000,
    [int]$DetectTimeoutMs = 500,
    [string]$WindowTitle = "GoldEvidenceBench Practice Form",
    [int]$MaxFieldLength = 64,
    [switch]$AllowNonAscii,
    [switch]$AllowEmptyFields,
    [switch]$DisableKeystrokeGate,
    [switch]$VerifySaved,
    [ValidateRange(500,30000)]
    [int]$VerifyTimeoutMs = 5000,
    [ValidateRange(50,5000)]
    [int]$VerifyPollMs = 200,
    [switch]$CloseAfterSave,
    [switch]$DryRun
)

function Escape-SendKeys([string]$value) {
    if ($null -eq $value) {
        return ""
    }
    return ($value -replace '([+\^%~\(\)\{\}\[\]])', '{$1}')
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

function Ensure-Win32 {
    if ("Win32" -as [type]) {
        return
    }
    Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class Win32 {
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder text, int maxLength);
    [DllImport("user32.dll")] public static extern int GetWindowTextLength(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);

    public static IntPtr FindWindowByTitle(string title) {
        if (string.IsNullOrEmpty(title)) {
            return IntPtr.Zero;
        }
        IntPtr found = IntPtr.Zero;
        EnumWindows((hWnd, lParam) => {
            if (!IsWindowVisible(hWnd)) {
                return true;
            }
            int length = GetWindowTextLength(hWnd);
            if (length <= 0) {
                return true;
            }
            var sb = new StringBuilder(length + 1);
            GetWindowText(hWnd, sb, sb.Capacity);
            string text = sb.ToString();
            if (text.IndexOf(title, StringComparison.OrdinalIgnoreCase) >= 0) {
                found = hWnd;
                return false;
            }
            return true;
        }, IntPtr.Zero);
        return found;
    }
}
"@
}

function Ensure-Uia {
    if ($script:UiaLoaded) {
        return $true
    }
    try {
        Add-Type -AssemblyName UIAutomationClient
        Add-Type -AssemblyName UIAutomationTypes
        $script:UiaLoaded = $true
        return $true
    } catch {
        $script:UiaLoaded = $false
        return $false
    }
}

function Get-UiaFocusedWindowTitle {
    if (-not $script:UiaLoaded) {
        return ""
    }
    try {
        $focused = [System.Windows.Automation.AutomationElement]::FocusedElement
        if ($null -eq $focused) {
            return ""
        }
        $windowType = [System.Windows.Automation.ControlType]::Window
        $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
        $node = $focused
        while ($node -ne $null -and $node.Current.ControlType -ne $windowType) {
            $node = $walker.GetParent($node)
        }
        if ($node -eq $null) {
            return ""
        }
        return $node.Current.Name
    } catch {
        return ""
    }
}

function Find-UiaWindow([string[]]$titles) {
    if (-not $script:UiaLoaded) {
        return $null
    }
    try {
        $root = [System.Windows.Automation.AutomationElement]::RootElement
        $condition = New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
            [System.Windows.Automation.ControlType]::Window
        )
        $windows = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $condition)
        foreach ($window in $windows) {
            $name = $window.Current.Name
            foreach ($title in $titles) {
                if (-not [string]::IsNullOrWhiteSpace($title) -and $name -like "*$title*") {
                    return $window
                }
            }
        }
    } catch {
        return $null
    }
    return $null
}

function Try-FocusFormInput([string[]]$titles) {
    $window = Find-UiaWindow $titles
    if ($null -eq $window) {
        return $false
    }
    try {
        $editCondition = New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
            [System.Windows.Automation.ControlType]::Edit
        )
        $edit = $window.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $editCondition)
        if ($null -ne $edit) {
            $edit.SetFocus()
            return $true
        }
    } catch {
        return $false
    }
    return $false
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

function Find-WindowProcess([string]$title) {
    return (Get-Process | Where-Object { $_.MainWindowTitle -like "*$title*" } | Select-Object -First 1)
}

function Get-TitleHints([string]$title) {
    $hints = @()
    if (-not [string]::IsNullOrWhiteSpace($title)) {
        $hints += $title
        $parts = $title -split "\s+"
        if ($parts.Length -ge 1) {
            $hints += $parts[0]
            $hints += $parts[$parts.Length - 1]
        }
        if ($parts.Length -ge 2) {
            $hints += ($parts[0..1] -join " ")
            $hints += ($parts[($parts.Length - 2)..($parts.Length - 1)] -join " ")
        }
        $longest = ($parts | Sort-Object Length -Descending | Select-Object -First 1)
        if ($longest) {
            $hints += $longest
        }
    }
    return ($hints | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique)
}

function Find-WindowHandle([string[]]$titles) {
    try {
        Ensure-Win32
        foreach ($title in $titles) {
            if ([string]::IsNullOrWhiteSpace($title)) {
                continue
            }
            $handle = [Win32]::FindWindowByTitle($title)
            if ($handle -ne [IntPtr]::Zero) {
                return $handle
            }
        }
        return [IntPtr]::Zero
    } catch {
        return [IntPtr]::Zero
    }
}

function Wait-ForWindowHandle([string[]]$titles, [int]$timeoutMs, [int]$pollMs) {
    $deadline = (Get-Date).AddMilliseconds($timeoutMs)
    while ((Get-Date) -lt $deadline) {
        $handle = Find-WindowHandle $titles
        if ($handle -ne [IntPtr]::Zero) {
            return $true
        }
        Start-Sleep -Milliseconds $pollMs
    }
    return (Find-WindowHandle $titles) -ne [IntPtr]::Zero
}

function Wait-ForWindowForeground([string[]]$titles, [int]$timeoutMs, [int]$pollMs) {
    $deadline = (Get-Date).AddMilliseconds($timeoutMs)
    while ((Get-Date) -lt $deadline) {
        $current = Get-ForegroundTitle
        foreach ($title in $titles) {
            if (-not [string]::IsNullOrWhiteSpace($title) -and $current -like "*$title*") {
                return $true
            }
        }
        Start-Sleep -Milliseconds $pollMs
    }
    return $false
}

function Wait-ForFocus([string[]]$titles, [int]$timeoutMs, [int]$pollMs) {
    $deadline = (Get-Date).AddMilliseconds($timeoutMs)
    while ((Get-Date) -lt $deadline) {
        $current = Get-ForegroundTitle
        foreach ($title in $titles) {
            if (-not [string]::IsNullOrWhiteSpace($title) -and $current -like "*$title*") {
                return $true
            }
        }
        if ($script:UiaLoaded) {
            $uiaTitle = Get-UiaFocusedWindowTitle
            foreach ($title in $titles) {
                if (-not [string]::IsNullOrWhiteSpace($title) -and $uiaTitle -like "*$title*") {
                    return $true
                }
            }
        }
        Start-Sleep -Milliseconds $pollMs
    }
    return $false
}

function Activate-Window([string]$title, [int]$timeoutMs, [int]$pollMs) {
    $titles = Get-TitleHints $title
    $handle = Find-WindowHandle $titles
    if ($handle -ne [IntPtr]::Zero) {
        try {
            Ensure-Win32
            [Win32]::ShowWindow($handle, 5) | Out-Null
            [Win32]::SetForegroundWindow($handle) | Out-Null
        } catch {
        }
        if (Wait-ForWindowForeground $titles $timeoutMs $pollMs) {
            return $true
        }
    }
    $proc = Find-WindowProcess $title
    if (-not $proc) {
        return $false
    }
    try {
        Ensure-Win32
        $proc.Refresh()
        if ($proc.MainWindowHandle -ne 0) {
            [Win32]::ShowWindow($proc.MainWindowHandle, 5) | Out-Null
            [Win32]::SetForegroundWindow($proc.MainWindowHandle) | Out-Null
        } else {
            Add-Type -AssemblyName Microsoft.VisualBasic
            [Microsoft.VisualBasic.Interaction]::AppActivate($proc.Id) | Out-Null
        }
    } catch {
    }
    return Wait-ForWindowForeground $titles $timeoutMs $pollMs
}

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutputPath = Join-Path $env:TEMP "practice_form_$timestamp.txt"
}

if (Test-Path $OutputPath) {
    switch ($OnExistingFile.ToLowerInvariant()) {
        "rename" {
            $OutputPath = New-UniqueFilePath $OutputPath
            Write-Host "Target exists; using new path $OutputPath"
        }
        "overwrite" {
            Write-Host "Target exists; will overwrite."
        }
        default {
            while ($true) {
                $choice = Read-Host "File exists at $OutputPath. [R]ename, [O]verwrite, [C]ancel"
                if ([string]::IsNullOrWhiteSpace($choice)) {
                    $choice = "R"
                }
                switch ($choice.Trim().ToUpperInvariant()) {
                    "R" {
                        $OutputPath = New-UniqueFilePath $OutputPath
                        Write-Host "Using new path $OutputPath"
                        break
                    }
                    "O" {
                        Write-Host "Will overwrite."
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
    foreach ($value in @($Username, $Password)) {
        $gateArgs = @("--mode", "text", "--text", $value, "--max-len", $MaxFieldLength)
        if ($AllowNonAscii) {
            $gateArgs += "--allow-non-ascii"
        }
        if ($AllowEmptyFields) {
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
}

$appScript = Join-Path $PSScriptRoot "practice_form_app.ps1"
if (-not (Test-Path $appScript)) {
    Write-Error "Missing practice form app: $appScript"
    exit 1
}

$psExe = (Get-Command powershell -ErrorAction SilentlyContinue).Source
if (-not $psExe) {
    $psExe = (Get-Command pwsh -ErrorAction SilentlyContinue).Source
}
if (-not $psExe) {
    Write-Error "No PowerShell executable found to launch the form app."
    exit 1
}

Write-Host "Launching practice form..."
Ensure-Uia | Out-Null
$argList = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-STA",
    "-File", $appScript,
    "-OutputPath", $OutputPath,
    "-WindowTitle", $WindowTitle
)
$process = Start-Process $psExe -ArgumentList $argList -PassThru -WindowStyle Normal
Start-Sleep -Milliseconds $DelayMs

$titleHints = Get-TitleHints $WindowTitle
if (-not (Wait-ForWindowHandle $titleHints $DetectTimeoutMs $ActivatePollMs)) {
    Write-Host "Form window not detected yet; continuing activation attempts."
}

$needsClick = $false
if (-not (Activate-Window $WindowTitle $ActivateTimeoutMs $ActivatePollMs)) {
    Write-Host "Form not active yet. Click it now to continue."
    $needsClick = $true
}
if (Try-FocusFormInput $titleHints) {
    Write-Host "Focused form input via UI Automation."
}
if (-not (Wait-ForFocus $titleHints $FocusTimeoutMs $ActivatePollMs)) {
    Write-Warning "Form never became active; stopping to avoid sending keys to the wrong window."
    exit 1
}
if ($needsClick) {
    Write-Host "Form active; continuing."
}

Add-Type -AssemblyName System.Windows.Forms

[System.Windows.Forms.SendKeys]::SendWait("^{a}")
[System.Windows.Forms.SendKeys]::SendWait("{BACKSPACE}")
Start-Sleep -Milliseconds $DelayMs

$escapedUser = Escape-SendKeys $Username
[System.Windows.Forms.SendKeys]::SendWait($escapedUser)
Start-Sleep -Milliseconds $DelayMs
[System.Windows.Forms.SendKeys]::SendWait("{TAB}")
Start-Sleep -Milliseconds $DelayMs

$escapedPass = Escape-SendKeys $Password
[System.Windows.Forms.SendKeys]::SendWait($escapedPass)
Start-Sleep -Milliseconds $DelayMs
[System.Windows.Forms.SendKeys]::SendWait("{TAB}")
Start-Sleep -Milliseconds $DelayMs

if ($RememberMe) {
    [System.Windows.Forms.SendKeys]::SendWait(" ")
    Start-Sleep -Milliseconds $DelayMs
}

[System.Windows.Forms.SendKeys]::SendWait("%s")
Start-Sleep -Milliseconds $DelayMs

Write-Host "Done. Saved to $OutputPath"

if ($VerifySaved) {
    if (-not (Wait-ForFile $OutputPath $VerifyTimeoutMs $VerifyPollMs)) {
        Write-Warning "VerifySaved failed: file not found after ${VerifyTimeoutMs}ms."
    } else {
        try {
            $contents = Get-Content -Path $OutputPath -Raw
            if (-not $contents.Contains("username=$Username")) {
                Write-Warning "VerifySaved failed: username not found."
            } elseif (-not $contents.Contains("password=$Password")) {
                Write-Warning "VerifySaved failed: password not found."
            } else {
                Write-Host "VerifySaved OK: file exists and contains expected fields."
            }
        } catch {
            Write-Warning "VerifySaved failed: unable to read file content."
        }
    }
}

if ($CloseAfterSave) {
    Write-Host "Closing practice form..."
    $null = Activate-Window $WindowTitle $ActivateTimeoutMs $ActivatePollMs
    Start-Sleep -Milliseconds $DelayMs
    [System.Windows.Forms.SendKeys]::SendWait("%{F4}")
    Start-Sleep -Milliseconds $DelayMs
}
