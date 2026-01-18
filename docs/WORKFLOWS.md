# Workflow Index

This page lists the primary flows and the single command to run each one.
Use `.\scripts\run_demo.ps1 -List` to see all presets with live vs fixture mode.

## End-to-end demos (safe UI actions)

Notepad demo (planner + gates + verify + close):

```powershell
.\scripts\run_demo.ps1 -ModelPath "C:\AI\models\qwen2.5-7b-instruct-q5_k_m-00001-of-00002.gguf" -Task "Open Notepad and write a note"
```

Multi-app demo (Notepad then Calculator):

```powershell
.\scripts\run_demo.ps1 -ModelPath "C:\AI\models\qwen2.5-7b-instruct-q5_k_m-00001-of-00002.gguf" -Task "Write a note and compute 12+34"
```

Keystroke safety gate runs by default; use `-DisableKeystrokeGate` to bypass (and `-MaxTextLength` to tune).

Use `-PromptForText` to enter custom text, or `-GenerateText` to let the 7B generate it:

```powershell
.\scripts\run_demo.ps1 -ModelPath "C:\AI\models\qwen2.5-7b-instruct-q5_k_m-00001-of-00002.gguf" `
  -Task "Open Notepad and write a note" -GenerateText
```

Generated demo text is ASCII-only by default to keep SendKeys safe.

Form demo (live practice form):

```powershell
.\scripts\run_demo.ps1 -ModelPath "C:\AI\models\qwen2.5-7b-instruct-q5_k_m-00001-of-00002.gguf" -Task "Fill the login form"
```
If the form window doesn't activate automatically, click the form once and the script will proceed.

Fixture-only form stub:

```powershell
.\scripts\run_demo.ps1 -ModelPath "C:\AI\models\qwen2.5-7b-instruct-q5_k_m-00001-of-00002.gguf" -Preset form_stub
```

Table demo (fixture-only, gate + stub):

```powershell
.\scripts\run_demo.ps1 -ModelPath "C:\AI\models\qwen2.5-7b-instruct-q5_k_m-00001-of-00002.gguf" -Task "Export the table"
```

Calculator demo (live UI, verify via clipboard):

```powershell
.\scripts\run_demo.ps1 -ModelPath "C:\AI\models\qwen2.5-7b-instruct-q5_k_m-00001-of-00002.gguf" -Task "Compute 12+34"
```

Keystroke safety gate runs by default; use `-DisableKeystrokeGate` (and `-MaxExpressionLength` to tune).

## Release checks (gates)

Release check (runs pinned gates and UI stubs):

```powershell
.\scripts\run_release_check.ps1 -ModelPath "C:\AI\models\qwen2.5-7b-instruct-q5_k_m-00001-of-00002.gguf"
```

## Gate training (local optimum families)

Train + evaluate gate models across local-optimum fixtures:

```powershell
.\scripts\run_gate_sweep.ps1 -ModelPath "C:\AI\models\qwen2.5-7b-instruct-q5_k_m-00001-of-00002.gguf"
```

## Trap families

Get the next trap family to implement:

```powershell
.\scripts\next_trap_family.ps1
```
