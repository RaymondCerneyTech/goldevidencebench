# GoldEvidenceBench

GoldEvidenceBench (CLI: `goldevidencebench`) is a benchmark + harness for long-context state tracking. It generates synthetic episode logs with evolving state (kv/kv_commentary/counter/set/relational), distractors, and queries that require choosing the correct update under ambiguity. It decomposes failures (retrieval vs selection vs authority vs answering), adds safety gates, and emits reproducible artifacts.

## Project goals

- Make long-horizon state tracking measurable, reproducible, and gateable.
- Separate retrieval vs selection vs authority vs answering failures for targeted fixes.
- Provide safety-focused regression gates (drift, holdouts) that block unsafe commits.
- Enable low-cost, model-agnostic evaluation and repeatable workflows.
- Produce compact, auditable run artifacts that can resume without chat history.

## Current capabilities (short version)

- Long-context state tracking benchmark with deterministic oracles and trap families.
- Retrieval/selection decomposition with authority filtering and Actionable Diagnosis.
- Drift gate + holdouts + rotation/coverage for cumulative divergence.
- Thread log + compaction snapshots + report generator.
- Health check, resume, and run-to-run diff.
- Repro metadata + schema-validated artifacts.
- Safe UI demos (Notepad/Calculator/Form) and UI fixture gates.

## Quickstart (recommended)

Health check (resume + drift gate, exits non-zero on FAIL/WARN):

```powershell
.\scripts\run_health_check.ps1 -ModelPath "C:\AI\models\your-model.gguf"
```

Release check (pinned gates + UI stubs):

```powershell
.\scripts\run_release_check.ps1 -ModelPath "C:\AI\models\your-model.gguf"
```

Reference run (selector baselines):

```powershell
.\scripts\run_reference.ps1 -Preset standard -ModelPath "C:\AI\models\your-model.gguf"
```

## Individual 'Why' Steps (DecisionPoints)

Long tasks are modeled as chains of 'why' steps (DecisionPoints): each step is a constrained choice among candidates (evidence/action/state update). GoldEvidenceBench scores these choices, especially commit decisions, to prevent drift. Diagnosis and holdout reports tie failures back to the specific why-step so fixes are targeted and repeatable.

## Core run artifacts (per run folder)

- `summary.json`: aggregated metrics.
- `diagnosis.json`: bottleneck + prescription (gate-consistent).
- `compact_state.json`: compaction snapshot (schema + versioned).
- `thread.jsonl`: append-only event log.
- `report.md`: human-readable summary.
- `repro_commands.json`: reproducibility bundle.
- `health_check.json`: health check result (when run).

Schemas live under `schemas\` and artifacts include `artifact_version` for validation.

## Key commands

Reports and resume:

```powershell
python .\scripts\generate_report.py --latest
.\scripts\resume_run.ps1 -Latest
.\scripts\resume_run.ps1 -Latest -RunDriftGate -ModelPath "C:\AI\models\your-model.gguf"
python .\scripts\compare_runs.py --latest-pair --require-compact-state --print
```

Drift gate + holdouts:

```powershell
.\scripts\run_drift_wall.ps1 -ModelPath "C:\AI\models\your-model.gguf"
.\scripts\run_drift_holdout_gate.ps1 -ModelPath "C:\AI\models\your-model.gguf"
```

CI-friendly baseline (no model needed):

```powershell
.\scripts\run_adapter_baseline.ps1 -Preset smoke -Adapter goldevidencebench.adapters.mock_adapter:create_adapter
```

## Docs (deep dives and workflows)

- `docs/WORKFLOWS.md` - primary flows and demos.
- `docs/MEASUREMENTS.md` - experiments, tables, and historical plans.
- `docs/TRAP_FAMILIES.md` - trap family catalog.
- `docs/THREAD_ARTIFACTS.md` - thread/compaction artifacts.
- `docs/ADAPTERS.md` - adapter contract.
- `docs/RELATED.md` - related work.

## Install

```powershell
python -m pip install -e .
```
