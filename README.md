# GoldEvidenceBench

GoldEvidenceBench (CLI: `goldevidencebench`) is a **regression harness** for long-context state tracking and safety gates. It generates synthetic tasks with known ground truth, measures drift/authority/selection failures, and blocks regressions with repeatable artifacts.

What it **is**: a measurement + gate system for defined behaviors.  
What it **is not**: a general agent that makes models smarter on its own.

Stability: `main` moves; tagged releases are stable snapshots.

## Run quickly (no model, no keys)

Install (editable): `python -m pip install -e .`

```powershell
.\scripts\run_adapter_baseline.ps1 -Preset smoke -Adapter goldevidencebench.adapters.mock_adapter:create_adapter
```

On Linux/macOS, run the Python entrypoints directly (see [docs/WORKFLOWS.md](docs/WORKFLOWS.md)); the PowerShell runners are Windows-first.

Cross-platform front door (presets):

```powershell
python -m goldevidencebench run --preset smoke
python -m goldevidencebench run --preset regression --model-path "<MODEL_PATH>"
python -m goldevidencebench run --preset release --model-path "<MODEL_PATH>"
```

Key artifacts (smoke run):

```
runs/<run_dir>/
  report.md
  summary.json
  diagnosis.json
```

Find the newest smoke run dir (PowerShell):

```powershell
# Newest run dir (smoke run does not write a latest pointer)
Get-ChildItem runs -Directory |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1 -ExpandProperty FullName
```

Find the newest smoke run dir (bash/zsh):

```bash
ls -td runs/*/ | head -n 1
```

This verifies, without any model or API keys:

- The repo installs and runs end-to-end on your machine/CI.
- The CLI/scripts produce artifacts with the expected structure.
- The gate logic (thresholds, exit codes) behaves deterministically.
- You can inspect the evidence artifacts before wiring a real model.

## Run -> Artifacts -> Failure story

One command:

```powershell
.\scripts\run_regression_check.ps1 -ModelPath "<MODEL_PATH>"
```

Tiny artifact tree:

```
runs/<run_dir>/
  report.md
  summary.json
  diagnosis.json
  compact_state.json
  thread.jsonl
  repro_commands.json
```

Example excerpt (report.md + diagnosis.json from `runs/bad_actor_holdout_20260202_230442`):

```
Overall: FAIL
Primary bottleneck: action_safety
unsafe_commit_rate: 0.0833 (<= 0.0500) FAIL
authority_violation_rate: 0.0000 (<= 0.0100) PASS
drift.step_rate: 0.0000 (<= 0.2500) PASS
{"primary_bottleneck":"action_safety","top_fix":"Tighten safety gate for unsafe commits"}
{"next_fix":"Add abstain/escalation on unsafe signals"}
```

Screenshot (rendered excerpt):

![Report + diagnosis excerpt](docs/sample_artifacts/report_diagnosis_excerpt.svg)

Mini failure story: an authority decoy was selected -> a wrong commit happened -> drift persisted across steps.

Canonical caught regression story: see [docs/KNOWN_REGRESSION.md](docs/KNOWN_REGRESSION.md).

Pinned sample artifact pack (intentional FAIL example): see [docs/sample_artifacts](docs/sample_artifacts).

## If you want the one-pager case pack (model + PDF)

```powershell
.\scripts\run_case_pack_latest.ps1 -ModelPath "<MODEL_PATH>" -PdfPath "<PATH_TO_PDF>"
```

`-ModelPath` is adapter-specific (e.g., local GGUF path, server endpoint, or model directory), depending on the runner.

If you'll use `-PdfPath`, install: `python -m pip install -e ".[pdf]"`.

This prints the one-pager path when generated and appends a summary to `docs/RUN_LOG.md`.

## Behavioral contract

- Passing these commands means the metrics meet thresholds **on the listed fixtures only**.
- `.\scripts\run_regression_check.ps1` means drift gates pass on the drift wall + holdout fixtures.
- `.\scripts\run_rag_benchmark.ps1 -Preset lenient/strict` means value_acc/cite_f1 meet thresholds on the listed datasets.
- See **Behavioral contract (core)** below for the full list.
- Gate source-of-truth configs and artifacts: see [docs/GATES.md](docs/GATES.md).

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

## What this is useful for (plain English)

Use GoldEvidenceBench when you want **repeatable, auditable signals** about long-horizon state tracking:

- You are changing a model/prompt/retriever and need to know if state tracking regressed.
- You want to separate *what failed* (retrieval vs selection vs authority vs answering) instead of guessing.
- You need artifacts you can point to later (report, diagnosis, repro commands, gate JSON).
- You want a CI-friendly gate that blocks unsafe changes with a non-zero exit code.
- You need coverage for RAG-style failure modes and want them measured with repeatable datasets.

If you already know a failure exists, this still helps by making it **measurable and repeatable** so it can be fixed, guarded, and compared over time.

## How this differs from common eval frameworks

GoldEvidenceBench is a **local, artifact-first regression gate**. It emphasizes repeatable runs, on-disk artifacts, and explicit expected-fail semantics (canaries/holdouts).

Use this when you need:

- Auditable run artifacts you can attach to a PR or review.
- Long-horizon drift detection with clear bottlenecks.
- A one-command trust report (case pack) that tells a story.

Other eval tools are great for different goals:

- Standardized benchmark suites and leaderboards (academic coverage).
- Hosted evaluation platforms with dashboards and monitoring.
- Unit-test-style evals for prompt iterations in app development.

This repo is intentionally narrow: it prioritizes **repeatable regression gating** over breadth of benchmarks.

## Comparison (quick)

| Capability | GoldEvidenceBench | OpenAI Evals | LangSmith | RAGAS | lm-eval-harness |
| --- | --- | --- | --- | --- | --- |
| Local/offline | Yes (Windows-first) | No (API-first) | No (hosted) | Yes | Yes |
| Artifact bundles | Yes (report/summary/diagnosis/repro) | Limited (run logs) | Yes (run views) | No | Limited |
| Holdout + canary gates | Yes (built-in) | Custom | Custom | No | No |
| State-drift fixtures | Yes (long-horizon state logs) | Custom | Custom | No | No |
| State-update decision policy | Yes (commit policy + authority/commit) | Custom | Custom | Partial | No |
| CI gate outputs | Yes (exit codes + artifacts) | Custom | Yes (hosted) | No | Custom |

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

## Behavioral contract (core)

If these commands pass, you can claim the following behaviors **on the listed fixtures only**:

Fixtures and thresholds live in the linked configs below; the drift holdout gate logic lives in `scripts/run_drift_holdout_gate.ps1` and `scripts/run_drift_holdouts.ps1`.

- `.\scripts\run_regression_check.ps1`: drift.step_rate stays under the configured max on the drift wall and the drift holdout fixes pass.
- `.\scripts\run_core_benchmark.ps1`: policy task pass rate meets defaults in [`configs/core_thresholds.json`](configs/core_thresholds.json) for [`configs/core_benchmark.json`](configs/core_benchmark.json).
- `.\scripts\run_core_benchmark.ps1 -ConfigPath "configs/internal_tooling_benchmark.json"`: policy task pass rate meets defaults for the internal tooling set (state drift + wrong-path workflows). See [`configs/internal_tooling_benchmark.json`](configs/internal_tooling_benchmark.json).
- `.\scripts\run_core_benchmark.ps1 -ConfigPath "configs/compliance_benchmark.json"`: policy task pass rate meets defaults for the compliance set (bad-actor resistance + safety gates). See [`configs/compliance_benchmark.json`](configs/compliance_benchmark.json).
- `.\scripts\run_rag_benchmark.ps1 -Preset lenient`: value_acc and cite_f1 meet the lenient defaults in [`configs/rag_thresholds.json`](configs/rag_thresholds.json) for [`configs/rag_benchmark_lenient.json`](configs/rag_benchmark_lenient.json).
- `.\scripts\run_rag_benchmark.ps1 -Preset strict`: value_acc and cite_f1 meet the strict defaults in [`configs/rag_thresholds.json`](configs/rag_thresholds.json) for [`configs/rag_benchmark_strict.json`](configs/rag_benchmark_strict.json) (stricter thresholds + harder datasets, including the domain pack).

Outside these fixtures, behavior is not guaranteed; treat any new family as unknown until you add fixtures and enforce it.

## Requirements

- Python 3.10+ recommended.
- Windows PowerShell for the `.ps1` scripts.
- Optional: `GOLDEVIDENCEBENCH_MODEL` env var to avoid repeating `-ModelPath`.

## Supported platforms

- Windows-first (PowerShell entrypoints).
- Linux/macOS: run Python entrypoints directly.

## Quickstart (recommended)

Regression check (first real-model run):

```powershell
.\scripts\run_regression_check.ps1 -ModelPath "<MODEL_PATH>"
```

Tip: set `GOLDEVIDENCEBENCH_MODEL` to avoid repeating `-ModelPath`.

Release check (full suite):

```powershell
.\scripts\run_release_check.ps1 -ModelPath "<MODEL_PATH>"
```

Includes the bad_actor holdout safety gate (fixtures in `configs/bad_actor_holdout_list.json`, thresholds in `configs/usecase_checks.json`), using `prefer_update_latest` rerank (CLEAR-aware) with authority filtering by default.

Core benchmark (curated fixtures):

```powershell
.\scripts\run_core_benchmark.ps1
```

RAG benchmark (curated long-context datasets):

```powershell
.\scripts\run_rag_benchmark.ps1 -Preset lenient -ModelPath "<MODEL_PATH>"
.\scripts\run_rag_benchmark.ps1 -Preset strict -ModelPath "<MODEL_PATH>"
python .\scripts\compare_runs.py --latest-pair --print
```

Case pack: see **If you want the one-pager case pack (model + PDF)** above.

Details for RAG domain packs, open-book vs closed-book, and dataset formats live in [docs/WORKFLOWS.md](docs/WORKFLOWS.md).

## State-update decisions (DecisionPoints)

```
Retrieve -> Candidate set -> Commit policy -> Commit -> State -> Answer
```

Long tasks are modeled as chains of state-update decisions (DecisionPoints): each step is a constrained choice among candidates (evidence/action/state update). Example DecisionPoint: choose which candidate key/value to commit when multiple plausible evidence entries exist. GoldEvidenceBench scores these choices, especially commit decisions, to prevent drift. Diagnosis and holdout reports tie failures back to the specific decision step so fixes are targeted and repeatable.

## Glossary (short)

- Drift: state diverges after a wrong commit and the error persists across steps.
- Holdout: a small, fixed subset of tasks used to detect regressions.
- Canary: a known-fail baseline used to confirm the holdout is sensitive to drift.
- Wall: a broader set of fixtures used for baseline coverage.
- Authority filter: rejects low-authority evidence (e.g., NOTE/INFO decoys).
- State-update decision (DecisionPoint): a step that chooses which evidence/action commits to state.
- Retrieval vs selection vs answering: find evidence -> choose candidate -> produce final answer.
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

## Key commands (maintenance)

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

Note: `runs/drift_wall_latest` is the safety wall snapshot; `runs/drift_wall_latest_stress` is optional for diagnostic pressure tests.

Tip: add `-SafetyMode` to `run_drift_wall.ps1` for CLEAR-aware reranking + authority filtering when you want a safety-default wall run. Use `-LatestTag stress` if you want a separate "stress wall" snapshot under `runs/drift_wall_latest_stress`.

Drift holdout semantics and expected-fail canaries: see [docs/WORKFLOWS.md](docs/WORKFLOWS.md) (Drift holdout gate).

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

## Docs (start here)

- `docs/WORKFLOWS.md` - primary flows and demos.
- `docs/ADAPTERS.md` - adapter contract.
- `docs/TRAP_FAMILIES.md` - trap family catalog.
- `docs/THREAD_ARTIFACTS.md` - thread/compaction artifacts.

## Docs (deep dives and logs)

- `docs/MEASUREMENTS.md` - experiments, tables, and historical plans (archive older notes in `docs/MEASUREMENTS_ARCHIVE.md`).
- `docs/RUN_LOG.md` - summary of representative runs (archive older entries in `docs/RUN_LOG_ARCHIVE.md`).
- `docs/KNOWN_REGRESSION.md` - canonical caught regression example.
- `docs/RELATED.md` - related work.

## License

MIT License. See `LICENSE`.

## Contributing

Contributions are welcome. Keep changes focused, add or update tests when behavior changes, and run:

```powershell
python -m pytest
```

Donations are welcome; feature requests via Issues are best-effort.

AI-assisted development note: Most of this project was created with AI assistance (planning, code generation, and edits), with human review and iteration on top.
