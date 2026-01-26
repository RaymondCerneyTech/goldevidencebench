# GoldEvidenceBench

GoldEvidenceBench (CLI: `goldevidencebench`) is a **regression harness** for long-context state tracking and safety gates. It generates synthetic tasks with known ground truth, measures drift/authority/selection failures, and blocks regressions with repeatable artifacts.

What it **is**: a measurement + gate system for defined behaviors.  
What it **is not**: a general agent that makes models smarter on its own.

## Project goals

- Make long-horizon state tracking measurable, reproducible, and gateable.
- Separate retrieval vs selection vs authority vs answering failures for targeted fixes.
- Provide safety-focused regression gates (drift, holdouts) that block unsafe commits.
- Enable low-cost, model-agnostic evaluation and repeatable workflows.
- Produce compact, auditable run artifacts that can resume without chat history.

## Current capabilities (short version)

- Regression gates for drift/authority/selection on deterministic tasks.
- Holdouts + rotation/coverage for cumulative divergence.
- Thread log + compaction snapshots + report generator.
- Health check, resume, and run-to-run diff.
- Repro metadata + schema-validated artifacts.

## Short roadmap

- Keep drift/holdout gates green and tighten coverage for the core trap families.
- Improve run ergonomics (reports, diffs, cleanup) without expanding scope.

## Where this fits (and reliability expectations)

GoldEvidenceBench sits in the **evaluation + safety gating** part of AI systems: it measures failures in long-horizon state tracking (retrieval vs selection vs authority vs answering) and blocks regressions with repeatable artifacts.

Reliability correlates with **how close your real use case is to your fixtures/holdouts**. Expect strong, repeatable behavior on covered families; expect lower reliability and more work outside that coverage. Passing gates is a good signal for the behaviors you explicitly measure, not a guarantee for tasks you haven't modeled.

## What this project **can't** do

- It does **not** make a model smarter or add new capabilities on its own.
- It does **not** solve real tasks without an adapter/tool that can actually perform them.
- It does **not** guarantee real-world correctness outside the fixtures/holdouts you define.
- It does **not** replace model training, data collection, or product UX work.
- It does **not** generalize to arbitrary UI/coding tasks without explicit evaluation sets.

## Requirements

- Python 3.10+ recommended.
- Windows PowerShell for the `.ps1` scripts.
- Optional: `GOLDEVIDENCEBENCH_MODEL` env var to avoid repeating `-ModelPath`.

## Supported platforms

- Windows-first (PowerShell entrypoints).
- Linux/macOS: run Python entrypoints directly.

## Quickstart (recommended)

Regression check (focused, exits non-zero on FAIL/WARN):

```powershell
.\scripts\run_regression_check.ps1 -ModelPath "<MODEL_PATH>"
```

Release check (full suite):

```powershell
.\scripts\run_release_check.ps1 -ModelPath "<MODEL_PATH>"
```

Reference run (selector baselines):

```powershell
.\scripts\run_reference.ps1 -Preset standard -ModelPath "<MODEL_PATH>"
```

Minimal workflow (run → open report → optional compare):

```powershell
.\scripts\run_regression_check.ps1 -ModelPath "<MODEL_PATH>"
notepad runs\<latest>\report.md
python .\scripts\compare_runs.py --latest-pair --require-compact-state --print
```

What you get after a run:

```
runs\<latest>\
  report.md
  summary.json
  diagnosis.json
```

Demo (30 seconds):

```powershell
.\scripts\run_regression_check.ps1 -ModelPath "<MODEL_PATH>"
```

Then open:

- `runs\<latest>\report.md`

If FAIL/WARN, inspect `diagnosis.json` and the gate artifacts for details.

## Individual 'Why' Steps (DecisionPoints)

Long tasks are modeled as chains of 'why' steps (DecisionPoints): each step is a constrained choice among candidates (evidence/action/state update). Example DecisionPoint: choose which candidate key/value to commit when multiple plausible evidence entries exist. GoldEvidenceBench scores these choices, especially commit decisions, to prevent drift. Diagnosis and holdout reports tie failures back to the specific why-step so fixes are targeted and repeatable.

## Glossary (short)

- Drift: state diverges after a wrong commit and the error persists across steps.
- Holdout: a small, fixed subset of tasks used to detect regressions.
- Canary: a known-fail baseline used to confirm the holdout is sensitive to drift.
- Wall: a broader set of fixtures used for baseline coverage.
- Authority filter: rejects low-authority evidence (e.g., NOTE/INFO decoys).
- Retrieval vs selection vs answering: find evidence → choose candidate → produce final answer.
- PASS/FAIL: PASS means all configured gates met thresholds; FAIL/WARN means inspect the gate artifacts.

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
.\scripts\resume_run.ps1 -Latest -RunDriftGate -ModelPath "<MODEL_PATH>"
python .\scripts\compare_runs.py --latest-pair --require-compact-state --print
```

Drift wall + drift holdout gate:

```powershell
.\scripts\run_drift_wall.ps1 -ModelPath "<MODEL_PATH>"
.\scripts\run_drift_holdout_gate.ps1 -ModelPath "<MODEL_PATH>"
```

Drift holdout gate expectations (stale_tab_state):

- Canary (latest_step, authority filter off) is expected to FAIL with drift.step_rate >= 0.5.
- Fix A (authority filter on) is expected to PASS with drift.step_rate <= 0.25.
- Fix B (prefer_set_latest) is expected to PASS with drift.step_rate <= 0.25.
- Artifact: `runs\release_gates\drift_holdout_gate.json` plus per-run summaries under the run folder.

What the terms mean:

- Canary = known-fail baseline. It proves the holdout is sensitive to drift.
- Fix A/B = two mitigation paths. If either fails, that mitigation regressed.

How to interpret the artifact:

- PASS means canary failed and both fixes passed.
- Canary PASS means the holdout stopped detecting drift (bad signal).
- Fix FAIL means a mitigation no longer works (regression to investigate).

CI-friendly baseline (no model needed):

```powershell
.\scripts\run_adapter_baseline.ps1 -Preset smoke -Adapter goldevidencebench.adapters.mock_adapter:create_adapter
```

Cleanup runs (dry-run by default):

```powershell
.\scripts\cleanup_runs.ps1
.\scripts\cleanup_runs.ps1 -OlderThanDays 7 -Execute
```

## Project layout (short map)

- `scripts/` entrypoints and runners.
- `docs/` explanations and workflows.
- `schemas/` artifact validation schemas.
- `runs/` outputs (safe to delete).
- `data/` fixtures and holdouts.

To add a new holdout: create fixtures under `data/`, register the family in `docs/TRAP_FAMILIES.md`, and wire it into the holdout gate (and optionally the release check if you want it enforced in CI).

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

## License

MIT License. See `LICENSE`.

## Contributing

Contributions are welcome. Keep changes focused, add or update tests when behavior changes, and run:

```powershell
python -m pytest
```

Donations and advice are welcome.

AI-assisted development note: Most of this project was created with AI assistance (planning, code generation, and edits), with human review and iteration on top.
