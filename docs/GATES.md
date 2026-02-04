# Gate Contracts (Source of Truth)

This page lists each gate or benchmark, where its thresholds live, and the artifact it produces.
Treat the linked config files as the source of truth for PASS/FAIL semantics.

Terminology note: "commit policy" (aka selector/reranker) is the chooser that picks which candidate commits to state. Script and env var names still use "selector".
Gates are constraint checks: they don’t prevent optimization, they ensure optimization respects the contract.

## Core gates and benchmarks

| Gate / Benchmark | Command | Threshold / Fixture Config | Primary Artifact |
| --- | --- | --- | --- |
| Drift holdout gate | `.\scripts\run_drift_holdout_gate.ps1` | `configs/usecase_checks.json` (`drift_holdout_gate`: `canary_min`, `drift.step_rate` max) | `runs/release_gates/drift_holdout_gate.json` |
| Drift wall | `.\scripts\run_drift_wall.ps1` | `configs/usecase_checks.json` (`drift_gate`) | `runs/drift_wall_latest/summary.json` (safety wall); optional stress wall at `runs/drift_wall_latest_stress/summary.json` |
| Core benchmark | `.\scripts\run_core_benchmark.ps1` | `configs/core_benchmark.json` + `configs/core_thresholds.json` | `runs/<run_dir>/summary.json` |
| RAG benchmark (lenient/strict) | `.\scripts\run_rag_benchmark.ps1 -Preset lenient|strict` | `configs/rag_benchmark_lenient.json` / `configs/rag_benchmark_strict.json` + `configs/rag_thresholds.json` | `runs/<run_dir>/summary.json` |

## Release checks (gates)

| Gate | Command | Threshold / Fixture Config | Primary Artifact |
| --- | --- | --- | --- |
| Instruction override | `.\scripts\run_instruction_override_gate.ps1` | `configs/usecase_checks.json` (`instruction_override`) | `runs/release_gates/instruction_override_gate/summary.json` |
| Memory verify | `python .\scripts\verify_memories.py ...` | `configs/usecase_checks.json` (`memory_verify_gate`) | `runs/release_gates/memory_verify.json` |
| Update burst release gate | `.\scripts\run_update_burst_full_linear_bucket10.ps1` (via release check) | `configs/usecase_checks.json` (`update_burst_release_gate`) | `runs/release_gates/update_burst_full_linear_k16_bucket5_rate0.12/summary.json` |
| Bad actor holdout gate | `.\scripts\run_bad_actor_holdout_gate.ps1` | `configs/bad_actor_holdout_list.json` + `configs/usecase_checks.json` (`bad_actor_holdout_gate`) | `runs/bad_actor_holdout_latest/summary.json` |
| UI same_label stub | `.\scripts\run_ui_same_label_stub.ps1` | `configs/usecase_checks.json` (`ui_same_label_gate`) | `runs/ui_same_label_gate.json` |
| UI popup_overlay stub | `.\scripts\run_ui_popup_overlay_stub.ps1` | `configs/usecase_checks.json` (`ui_popup_overlay_gate`) | `runs/ui_popup_overlay_gate.json` |

Bad actor holdout defaults: `prefer_update_latest` rerank + authority filter (set in `scripts/run_bad_actor_holdout_gate.ps1`).

Every gate run writes a compact, human-friendly summary (`summary_compact.json` / `summary_compact.csv`) alongside `summary.json`. Latest pointers live under `runs/latest_*` (e.g., `runs/latest_release`, `runs/latest_regression`, `runs/latest_rag_lenient`).

## Holdout suite inputs

- UI holdout rotation list: `configs/ui_holdout_list.json`
- Bad actor holdout subset list: `configs/bad_actor_holdout_list.json`
- Gate threshold checks: `configs/usecase_checks.json`

If you add a new fixture or holdout, update the config file first, then wire it into the scripts or benchmarks that consume it.
