param(
    [string]$ModelPath = "",
    [string]$Preset = "",
    [string]$Task = "",
    [string]$Text = "",
    [string]$TextPrompt = "Write a short, friendly note suitable for Notepad.",
    [string]$FilePath = "",
    [string]$ConfigPath = "configs\\demo_presets.json",
    [switch]$UseRpaController,
    [string]$ControlSnapshotPath = "runs\\rpa_control_latest.json",
    [switch]$List,
    [switch]$PromptForText,
    [switch]$GenerateText,
    [switch]$DryRun
)

function Read-DemoConfig([string]$path) {
    if (-not (Test-Path $path)) {
        Write-Error "Demo presets config not found: $path"
        exit 1
    }
    return (Get-Content $path -Raw | ConvertFrom-Json)
}

function Write-PresetList($presets) {
    $index = 1
    foreach ($preset in $presets) {
        $desc = $preset.description
        if ([string]::IsNullOrWhiteSpace($desc)) {
            $desc = "(no description)"
        }
        $mode = $preset.mode
        if ([string]::IsNullOrWhiteSpace($mode)) {
            $mode = "unknown"
        }
        Write-Host ("[{0}] {1} ({2}) - {3}" -f $index, $preset.name, $mode, $desc)
        $slots = @()
        if ($preset.args -contains "-Text") {
            $slots += "Text"
        }
        if ($preset.args -contains "-FilePath") {
            $slots += "FilePath"
        }
        if ($slots.Count -gt 0) {
            Write-Host ("    Slots: {0}" -f ($slots -join ", "))
        }
        Write-Host ("    Example: .\\scripts\\run_demo.ps1 -Preset {0} -ModelPath ""<path>""" -f $preset.name)
        Write-Host ("    Script: {0}" -f $preset.script)
        $index += 1
    }
}

function Add-ArgValue([hashtable]$argsMap, [string]$name, $value) {
    if ([string]::IsNullOrWhiteSpace($name)) {
        return
    }
    $argsMap[$name] = $value
}

function Expand-EnvValue($value) {
    if ($null -eq $value) {
        return $value
    }
    if ($value -isnot [string]) {
        return $value
    }
    return [System.Environment]::ExpandEnvironmentVariables($value)
}

function Build-ArgsMap([System.Collections.Generic.List[string]]$tokens) {
    $argsMap = @{}
    for ($i = 0; $i -lt $tokens.Count; $i++) {
        $token = $tokens[$i]
        if ([string]::IsNullOrWhiteSpace($token) -or -not $token.StartsWith("-")) {
            continue
        }
        $name = $token.TrimStart("-")
        $value = $true
        if (($i + 1) -lt $tokens.Count) {
            $peek = $tokens[$i + 1]
            if (-not [string]::IsNullOrWhiteSpace($peek) -and -not $peek.StartsWith("-")) {
                $value = $peek
                $i += 1
            }
        }
        Add-ArgValue $argsMap $name $value
    }
    return $argsMap
}

function Get-GeneratedText([string]$modelPath, [string]$prompt, [string]$scriptPath) {
    if (-not (Test-Path $scriptPath)) {
        Write-Warning "Text generation script not found: $scriptPath"
        return ""
    }
    $output = & python $scriptPath --model $modelPath --prompt $prompt --ascii-only
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Text generation failed; using preset default."
        return ""
    }
    if ($null -eq $output) {
        return ""
    }
    return ($output | Out-String).Trim()
}

function Select-PresetByTask($presets, [string]$task) {
    if ([string]::IsNullOrWhiteSpace($task)) {
        return $null
    }
    $text = $task.ToLowerInvariant()
    $best = $null
    $bestScore = 0
    foreach ($preset in $presets) {
        $score = 0
        if ($preset.match_regex) {
            try {
                if ($text -match $preset.match_regex) {
                    $score += 2
                }
            } catch {
            }
        }
        foreach ($keyword in $preset.keywords) {
            if ([string]::IsNullOrWhiteSpace($keyword)) {
                continue
            }
            if ($text -like ("*" + $keyword.ToLowerInvariant() + "*")) {
                $score += 1
            }
        }
        if ($score -gt $bestScore) {
            $bestScore = $score
            $best = $preset
        }
    }
    if ($bestScore -le 0) {
        return $null
    }
    return $best
}

function Read-JsonFile([string]$path) {
    if (-not (Test-Path $path)) {
        return $null
    }
    return (Get-Content $path -Raw | ConvertFrom-Json)
}

function Resolve-PolicyReasonCode($control) {
    if ($null -eq $control) {
        return "BLOCKED_BY_RUNTIME_POLICY"
    }
    if ($control.control_v2 -and $control.control_v2.policy -and $control.control_v2.policy.reasons) {
        $reasons = @($control.control_v2.policy.reasons)
        if ($reasons.Count -gt 0 -and $reasons[0].code) {
            return [string]$reasons[0].code
        }
    }
    return "BLOCKED_BY_RUNTIME_POLICY"
}

function Resolve-NextAction([string]$decision) {
    if ([string]::IsNullOrWhiteSpace($decision)) {
        return "defer"
    }
    switch ($decision.Trim().ToLowerInvariant()) {
        "ask" { return "ask" }
        "retrieve" { return "retrieve" }
        "verify" { return "verify" }
        "defer" { return "defer" }
        "abstain" { return "ask" }
        default { return "defer" }
    }
}

$config = Read-DemoConfig $ConfigPath
$presets = $config.presets
if (-not $presets -or $presets.Count -eq 0) {
    Write-Error "No presets found in $ConfigPath"
    exit 1
}

if ($List) {
    Write-PresetList $presets
    exit 0
}

if ([string]::IsNullOrWhiteSpace($ModelPath)) {
    Write-Error "ModelPath is required."
    exit 1
}

if ($config.defaults) {
    if ([string]::IsNullOrWhiteSpace($env:GOLDEVIDENCEBENCH_UI_GATE_MODELS) -and $config.defaults.gate_models) {
        $env:GOLDEVIDENCEBENCH_UI_GATE_MODELS = $config.defaults.gate_models
    }
    if ([string]::IsNullOrWhiteSpace($env:GOLDEVIDENCEBENCH_UI_PRESELECT_RULES) -and $config.defaults.preselect_rules) {
        $env:GOLDEVIDENCEBENCH_UI_PRESELECT_RULES = $config.defaults.preselect_rules
    }
}

$selected = $null
if (-not [string]::IsNullOrWhiteSpace($Preset)) {
    $selected = $presets | Where-Object { $_.name -ieq $Preset } | Select-Object -First 1
    if (-not $selected) {
        Write-Error "Preset not found: $Preset"
        exit 1
    }
} elseif (-not [string]::IsNullOrWhiteSpace($Task)) {
    $selected = Select-PresetByTask $presets $Task
    if (-not $selected) {
        Write-Error "No preset matched Task. Use -List to see available presets."
        exit 1
    }
} else {
    Write-PresetList $presets
    $choice = Read-Host "Select a preset (number)"
    $parsed = 0
    if (-not [int]::TryParse($choice, [ref]$parsed)) {
        Write-Error "Invalid choice."
        exit 1
    }
    $index = $parsed - 1
    if ($index -lt 0 -or $index -ge $presets.Count) {
        Write-Error "Choice out of range."
        exit 1
    }
    $selected = $presets[$index]
}

$repoRoot = Split-Path $PSScriptRoot -Parent
$scriptPath = $selected.script
if ([string]::IsNullOrWhiteSpace($scriptPath)) {
    Write-Error "Selected preset missing script path."
    exit 1
}
if (-not [System.IO.Path]::IsPathRooted($scriptPath)) {
    $scriptPath = Join-Path $repoRoot $scriptPath
}
if (-not (Test-Path $scriptPath)) {
    Write-Error "Preset script not found: $scriptPath"
    exit 1
}

if ($UseRpaController) {
    if (-not (Test-Path $ControlSnapshotPath)) {
        $snapshotBuilder = Join-Path $PSScriptRoot "run_rpa_control_snapshot.ps1"
        if (-not (Test-Path $snapshotBuilder)) {
            Write-Error "Runtime policy enabled but snapshot builder missing: $snapshotBuilder"
            exit 1
        }
        & $snapshotBuilder -Out $ControlSnapshotPath | Out-Host
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to build runtime control snapshot."
            exit $LASTEXITCODE
        }
    }

    $control = Read-JsonFile $ControlSnapshotPath
    if ($null -eq $control) {
        Write-Error "Runtime policy enabled but control snapshot is missing: $ControlSnapshotPath"
        exit 1
    }

    $decision = if ($control.decision) { [string]$control.decision } else { "" }
    $mode = if ($control.mode) { [string]$control.mode } else { "" }
    $policyBlocked = $false
    if ($control.control_v2 -and $control.control_v2.policy) {
        try {
            $policyBlocked = [bool]$control.control_v2.policy.blocked
        } catch {
            $policyBlocked = $false
        }
    }
    $blocked = $policyBlocked -or ($decision.Trim().ToLowerInvariant() -ne "answer")
    if ($blocked) {
        $reasonCode = Resolve-PolicyReasonCode $control
        $nextAction = Resolve-NextAction $decision
        Write-Error ("Runtime policy blocked demo execution: mode={0} decision={1} reason={2}. Next action: {3}" -f `
            $mode, $decision, $reasonCode, $nextAction)
        exit 2
    }
}

$argsList = New-Object System.Collections.Generic.List[string]
foreach ($arg in $selected.args) {
    if ($null -ne $arg) {
        $argsList.Add([string]$arg)
    }
}
$argsMap = Build-ArgsMap $argsList
Add-ArgValue $argsMap "ModelPath" $ModelPath
if (-not [string]::IsNullOrWhiteSpace($Text)) {
    Add-ArgValue $argsMap "Text" $Text
}
if (-not [string]::IsNullOrWhiteSpace($FilePath)) {
    Add-ArgValue $argsMap "FilePath" $FilePath
}
if ($DryRun) {
    Add-ArgValue $argsMap "DryRun" $true
}

$didPrompt = $false
if ($argsMap.ContainsKey("Text") -and [string]::IsNullOrWhiteSpace($Text)) {
    if ($GenerateText) {
        $generatorPath = Join-Path $repoRoot "scripts\\generate_demo_text.py"
        $generated = Get-GeneratedText $ModelPath $TextPrompt $generatorPath
        if (-not [string]::IsNullOrWhiteSpace($generated)) {
            Add-ArgValue $argsMap "Text" $generated
            Write-Host "Generated text for demo."
        } else {
            Write-Warning "Generated text was empty; using preset default."
        }
    } elseif ($PromptForText -or -not [string]::IsNullOrWhiteSpace($Task)) {
        $inputText = Read-Host "Enter text for the demo (leave blank to use default)"
        $didPrompt = $true
        if (-not [string]::IsNullOrWhiteSpace($inputText)) {
            Add-ArgValue $argsMap "Text" $inputText
        }
    }
}

if ($argsMap.ContainsKey("FilePath") -and [string]::IsNullOrWhiteSpace($FilePath) -and -not [string]::IsNullOrWhiteSpace($Task)) {
    $defaultPath = Expand-EnvValue $argsMap["FilePath"]
    $inputPath = Read-Host "File path (leave blank for $defaultPath)"
    $didPrompt = $true
    if (-not [string]::IsNullOrWhiteSpace($inputPath)) {
        Add-ArgValue $argsMap "FilePath" $inputPath
    }
}

foreach ($key in @($argsMap.Keys)) {
    $argsMap[$key] = Expand-EnvValue $argsMap[$key]
}

Write-Host ("Selected preset: {0}" -f $selected.name)
Write-Host ("Script: {0}" -f $scriptPath)

if ($didPrompt -and -not $DryRun) {
    Write-Host "Planned arguments:"
    foreach ($key in ($argsMap.Keys | Sort-Object)) {
        $value = $argsMap[$key]
        if ($key -eq "Text" -and $null -ne $value -and $value.Length -gt 120) {
            $value = $value.Substring(0, 117) + "..."
        }
        Write-Host ("  -{0} {1}" -f $key, $value)
    }
    $confirm = Read-Host "Proceed? [Y/N]"
    if ($confirm -and $confirm.Trim().ToUpperInvariant() -ne "Y") {
        Write-Host "Canceled."
        exit 1
    }
}

& $scriptPath @argsMap
exit $LASTEXITCODE
