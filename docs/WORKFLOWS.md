# Workflow Index

This page lists the primary flows and the single command to run each one.

Use `.\scripts\run_demo.ps1 -List` to see all presets with live vs fixture mode.

PowerShell scripts (`.ps1`) are Windows-first; on Linux/macOS use the equivalent Python entrypoints (see `scripts/` and [ADAPTERS.md](ADAPTERS.md)) or run gates in Windows CI for parity. Paths below use Windows-friendly examples unless explicitly labeled.

## Quick index

- [End-to-end demos](#end-to-end-demos-safe-ui-actions)
- [Release checks](#release-checks-gates)
- [Drift holdout gate](#drift-holdout-gate)
- [Benchmarks (core and RAG)](#benchmarks-core-and-rag)
- [Gate training](#gate-training-local-optimum-families)
- [Trap families](#trap-families)

## End-to-end demos (safe UI actions)

Notepad demo (live UI):

```powershell
.\scripts\run_demo.ps1 -ModelPath "<MODEL_PATH>" -Task "Open Notepad and write a note"
```

Multi-app demo (live UI, Notepad then Calculator):

```powershell
.\scripts\run_demo.ps1 -ModelPath "<MODEL_PATH>" -Task "Write a note and compute 12+34"
```

### Safety knobs (UI demos)

- Keystroke safety gate runs by default.
- `-DisableKeystrokeGate` bypasses it.
- `-MaxTextLength` and `-MaxExpressionLength` tune input size.
- `-GenerateText` uses model-generated ASCII-only text by default (SendKeys-safe).

Use `-PromptForText` to enter custom text, or `-GenerateText` to let the model generate it:

```powershell
.\scripts\run_demo.ps1 -ModelPath "<MODEL_PATH>" `
  -Task "Open Notepad and write a note" -GenerateText
```

Form demo (live UI):

```powershell
.\scripts\run_demo.ps1 -ModelPath "<MODEL_PATH>" -Task "Fill the login form"
```

If the form window doesn't activate automatically, click the form once and the script will proceed.

Form stub (fixtures only):

```powershell
.\scripts\run_demo.ps1 -ModelPath "<MODEL_PATH>" -Preset form_stub
```

Table demo (stubbed, fixtures only):

```powershell
.\scripts\run_demo.ps1 -ModelPath "<MODEL_PATH>" -Task "Export the table"
```

This task is routed to the table stub preset (no live UI) to keep demos deterministic.

Calculator demo (live UI, clipboard verify):

```powershell
.\scripts\run_demo.ps1 -ModelPath "<MODEL_PATH>" -Task "Compute 12+34"
```

## Release checks (gates)

Release check (runs pinned gates and UI stubs):

```powershell
.\scripts\run_release_check.ps1 -ModelPath "<MODEL_PATH>"
```

## Drift holdout gate

**Drift holdout gate expectations (`stale_tab_state`)**

- `stale_tab_state`: model tends to commit stale UI state.

Expected outcomes (thresholds in [configs/usecase_checks.json](../configs/usecase_checks.json)):

- Canary (latest_step, authority filter off) is expected to FAIL per `drift.step_rate` thresholds.
- Fix A (authority filter on) is expected to PASS per `drift.step_rate` thresholds.
- Fix B (prefer_set_latest, authority filter on) is expected to PASS per `drift.step_rate` thresholds.
- Artifact: `runs/release_gates/drift_holdout_gate.json` (overwritten on each release check). Per-run summaries live under `runs/<run_dir>/`.

What the terms mean:

- Canary = known-fail baseline. It proves the holdout is sensitive to drift.
- Fix A/B = two mitigation paths. If either fails, that mitigation regressed.

How to interpret the artifact:

- PASS means canary failed and both fixes passed.
- Canary PASS means the holdout stopped detecting drift (bad signal).
- Fix FAIL means a mitigation no longer works (regression to investigate).

## Benchmarks (core and RAG)

Core benchmark (curated fixtures):

```powershell
.\scripts\run_core_benchmark.ps1
```

Outputs are written under `runs/<run_dir>/` (new folder per run), including `summary.json` and `report.md`, for the curated fixtures in `configs/core_benchmark.json`. 
Defaults come from `configs/core_thresholds.json` (override with `-MinPolicyPass` if needed).

Internal tooling benchmark (state drift + wrong-path workflows):

```powershell
.\scripts\run_core_benchmark.ps1 -ConfigPath "configs\internal_tooling_benchmark.json"
```

Compliance/safety benchmark (bad-actor resistance + safety gates):

```powershell
.\scripts\run_core_benchmark.ps1 -ConfigPath "configs\compliance_benchmark.json"
```

Reference run (selector baselines):

```powershell
.\scripts\run_reference.ps1 -Preset standard -ModelPath "<MODEL_PATH>"
```

RAG benchmark (curated long-context datasets):

```powershell
.\scripts\run_rag_benchmark.ps1 -Preset lenient -ModelPath "<MODEL_PATH>"
.\scripts\run_rag_benchmark.ps1 -Preset strict -ModelPath "<MODEL_PATH>"
python .\scripts\compare_runs.py --latest-pair --print
```

This compares the newest two runs under `runs/`.

Bring your own docs (domain pack):

```powershell
python .\scripts\build_rag_domain_pack.py --in ".\examples\domain_pack_example.jsonl" --out-dir "data"
.\scripts\run_rag_benchmark.ps1 -Preset strict -ModelPath "<MODEL_PATH>"
```

Note: this overwrites `data/rag_domain_stale.jsonl` and `data/rag_domain_authority.jsonl`.

Defaults live in [configs/rag_thresholds.json](../configs/rag_thresholds.json) (lenient/strict). Adjust per dataset; closed-book strict on the domain pack is expected to fail until retrieval/open-book wiring is in place.

The strict preset also includes smaller/harder datasets.

Domain pack contents:

- Policy handbook stale-doc traps (`data/rag_domain_stale.jsonl`)
- Policy handbook authority decoys (`data/rag_domain_authority.jsonl`)

The domain pack is included in the **strict** preset by default so lenient stays green for CI.

Contract clarity:

- **Lenient** should be green in CI for day-to-day regressions.
- **Strict** is expected to be red in closed-book mode on the domain pack until retrieval/open-book wiring is in place.

Retriever swap delta (BM25 vs dense):

```powershell
.\scripts\run_rag_retriever_delta.ps1 -Preset lenient -ModelPath "<MODEL_PATH>"
```

Import your own domain pack (JSON or JSONL):

```powershell
python .\scripts\build_rag_domain_pack.py --in "<PATH_TO_JSON_OR_JSONL>"
```

PDF import demo (writes a temporary pack under `runs/`):

```powershell
.\scripts\run_rag_import_demo.ps1 -PdfPath "<PATH_TO_PDF>" -ModelPath "<MODEL_PATH>"
```

Open-book RAG demo (doc index + dataset from PDF, then open-book adapter):

```powershell
.\scripts\run_rag_open_book_demo.ps1 -PdfPath "<PATH_TO_PDF>" -ModelPath "<MODEL_PATH>"
```

Runtime knobs:

- `-MaxRows <N>` on `run_rag_benchmark.ps1` limits each dataset to N rows.
- `-MaxRows <N>` on `run_rag_open_book_demo.ps1` limits the generated dataset size.

Open-book vs closed-book (what to expect):

- Closed-book strict is expected to fail on the domain pack (no access to the source docs).
- Open-book should improve value_acc and cite_f1 on the same doc family when retrieval is working.
- Compare the two reports to show the gap:
  - Closed-book strict: `runs/<strict_run>/report.md`
  - Open-book demo: `runs/<open_book_run>/rag_open_book_run/report.md`
- A healthy open-book run will also show a non-zero `retrieval_hit_rate` in the report.

Example signature (illustrative, not guaranteed): an open-book run may show materially higher `value_acc`/`cite_f1` and non-zero `retrieval_hit_rate` compared to closed-book strict on the same family (e.g., `value_acc≈0.58`, `cite_f1≈0.96` on `n=24`).

Entry format (each row):

```json
{
  "id": "POL001-Q001",
  "label": "Data retention days",
  "policy": "Customer data retention window.",
  "current": "retention_days=45",
  "old": "retention_days=30",
  "decoy": "retention_days=90",
  "bucket": "stale_doc"
}
```

Set `bucket` to `stale_doc` or `authority_decoy`. `old` is optional. If `id/label/episode/key` are omitted, defaults are generated.

Reading strict failures:

- `report.md` includes a **Top failing datasets** section to show which domain pack datasets missed thresholds.

## Gate training (local optimum families)

Train + evaluate gate models across local-optimum fixtures:

```powershell
.\scripts\run_gate_sweep.ps1 -ModelPath "<MODEL_PATH>"
```

## Trap families

Get the next trap family to implement:

```powershell
.\scripts\next_trap_family.ps1
```
