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

Fast iterative reliability loop (no heavy gate sweep):

```powershell
.\scripts\run_test_check.ps1 `
  -Adapter "goldevidencebench.adapters.llama_server_adapter:create_adapter"
```

`run_test_check.ps1` uses the release contract matrix in `-UseExistingArtifacts`
mode to find failing families, reruns only those families, and repeats for a
bounded number of rounds. Useful when strict release is too slow for edit/test
cycles.

`run_test_check.ps1` also emits `artifact_audit.json` for release-adjacent
artifacts, including the full strict-release reliability family set. The drift
holdout gate artifact is still audited, but its `FAIL` status is treated as
non-blocking in this iterative loop (missing/invalid artifact still fails).

`run_release_check.ps1` now executes `scripts/check_reliability_signal.ps1` as
its final gate. The script exit code is the ship/no-ship signal. Use
`-SkipReliabilitySignal` only for diagnostics.

Strict release contract source of truth:
- `configs/release_gate_contract.json`
- schema: `schemas/release_gate_contract.schema.json`
- `strict_release.canary_policy` sets the default release canary behavior.
- `required_reliability_families[].canary_policy` optionally overrides per family
  (`strict` or `triage`).

In `release` profile, `run_release_check.ps1` first produces a deterministic
reliability matrix from that contract:
- script: `scripts/run_release_reliability_matrix.ps1`
- artifact: `<release_run_dir>/release_reliability_matrix.json`
- latest pointer: `runs/latest_release_reliability_matrix`
- if contract freshness is `allow_latest`, matrix uses existing artifacts
- standalone matrix runs can use `-FailOnMatrixFail` to return non-zero on matrix `FAIL`

Mixed mode guardrail:
- `-GateProfile release -FastLocal` is blocked unless you pass
  `-AllowReleaseFastLocalTriage`.

Release check also runs persona invariance aggregation before threshold checks:
- `runs/release_gates/persona_invariance/summary.json`
- hard fail on `overall.min_row_invariance_rate < 1.0`
- failure category: `persona_contract_drift`

Release check also collects cross-app intent-preservation pack output (warn-only in v1):
- `runs/release_gates/cross_app_intent_preservation_pack/summary.json`
- threshold check id: `cross_app_intent_preservation_pack` (`severity=warn`)
- does not hard-fail release in v1

By default, the final gate now requires these control families:
- `rpa_mode_switch`
- `intent_spec_layer`
- `noise_escalation`
- `implication_coherence`
- `agency_preserving_substitution`

By default, the final gate also enforces:
- `derived.reasoning_score >= 0.98`
- `derived.planning_score >= 0.98`
- `derived.intelligence_index >= 0.98`
- `derived.implication_coherence_core >= 0.945`
- `derived.agency_preservation_core >= 0.92`

Utility gate ownership is contract-driven from
`strict_release.utility_gate` in `configs/release_gate_contract.json`
(required/deferred + producer + artifact path). Current default contract is
deferred (`required=false`).

Diagnostic-only override:

```powershell
.\scripts\run_release_check.ps1 -SkipRequireControlFamilies
.\scripts\run_release_check.ps1 -SkipDerivedScoreFloors
.\scripts\run_release_check.ps1 -SkipRealWorldUtilityEval
```

Trap-family runner knobs (default on):
- `-RunPersonaTrap $true|$false`
- `-PersonaProfiles "persona_confident_expert,persona_creative_writer,persona_ultra_brief,persona_overly_helpful"`

On unified reliability PASS, release check now also rebuilds Codex compatibility
artifacts and refreshes latest pointers:
- `runs/latest_codex_compat_family_matrix`
- `runs/latest_codex_compat_orthogonality_matrix`
- `runs/latest_codex_compat_rpa_ablation_report`
- `runs/latest_codex_compat_scaffold_backlog`
- `runs/latest_codex_compat_report`
- `runs/latest_codex_next_step_report`

Instruction override soft-fail normalization:
- `run_instruction_override_gate.ps1` writes `runs/release_gates/instruction_override_gate/sweep_status.json`.
- Non-zero sweep exits with complete artifacts are normalized as soft-fail and do not block release by default.
- Use `-FailOnSweepSoftFail` to make that condition blocking.
- From release/nightly wrappers, use `-FailOnInstructionOverrideSoftFail` to escalate normalized soft-fails to hard release failure.

Server-adapter variant (no local model-path loading):

```powershell
.\scripts\run_release_check.ps1 -GateAdapter "goldevidencebench.adapters.llama_server_adapter:create_adapter"
```

Gate threshold sources and artifacts are listed in [docs/GATES.md](docs/GATES.md).

Real-world utility A/B evaluation (baseline vs controlled):

```powershell
.\scripts\run_real_world_utility_eval.ps1 `
  -Adapter "goldevidencebench.adapters.llama_server_adapter:create_adapter"
```

Writes `runs/real_world_utility_eval_latest.json` and updates
`runs/latest_real_world_utility_eval`.

Latest pointers:
- Release: `runs/latest_release` (manifest inside the run dir).
- Regression check (if run via `run_regression_check.ps1`): `runs/latest_regression`.

## Preflight (cross-app pack)

Use preflight to run a single machine-readable pack pass before longer campaigns.

Python CLI:

```powershell
goldevidencebench preflight `
  --profile cross_app_v1 `
  --stage dev `
  --data fixture `
  --adapter "goldevidencebench.adapters.mock_adapter:create_adapter"
```

Alias:

```powershell
geb preflight --profile cross_app_v1 --stage dev --data fixture --adapter "goldevidencebench.adapters.mock_adapter:create_adapter"
```

Artifacts:
- `runs/preflight/latest.json`
- `runs/latest_cross_app_intent_preservation_pack`

Drift wall signals:
- Safety wall (default/latest): `runs/drift_wall_latest` (release-relevant).
- Stress wall (optional): `runs/drift_wall_latest_stress` (diagnostic pressure test).

## Manuscript Continuity Mode (retired)

The manuscript/novel longform pipeline has been removed from this repository.

Removed entrypoints:

- `scripts/run_manuscript_mode.ps1`
- `scripts/run_autonomous_novel_mode.ps1`
- `scripts/run_intrinsic_fast_lane.ps1`
- `scripts/run_longform_intrinsic_eval.ps1`
- `scripts/evaluate_longform_intrinsic.py`
- `scripts/generate_longform_intrinsic_tasks.py`
- `scripts/score_longform_intrinsic.py`

If you need reliability evaluation, use the active trap-family and release workflows on this page.

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

Outputs are written under `runs/<run_dir>/` (new folder per run), including `summary_compact.json` / `summary_compact.csv` (readable), plus `summary.json` and `report.md`, for the curated fixtures in `configs/core_benchmark.json`. 
Defaults come from `configs/core_thresholds.json` (override with `-MinPolicyPass` if needed).
Latest pointer: `runs/latest_core_benchmark`.

Internal tooling benchmark (state drift + wrong-path workflows):

```powershell
.\scripts\run_core_benchmark.ps1 -ConfigPath "configs\internal_tooling_benchmark.json"
```

Compliance/safety benchmark (bad-actor resistance + safety gates):

```powershell
.\scripts\run_core_benchmark.ps1 -ConfigPath "configs\compliance_benchmark.json"
```

Reference run (commit policy baselines):

```powershell
.\scripts\run_reference.ps1 -Preset standard -ModelPath "<MODEL_PATH>"
```

RAG benchmark (curated long-context datasets):

```powershell
.\scripts\run_rag_benchmark.ps1 -Preset lenient -ModelPath "<MODEL_PATH>"
.\scripts\run_rag_benchmark.ps1 -Preset strict -ModelPath "<MODEL_PATH>"
python .\scripts\compare_runs.py --latest-pair --print
python .\scripts\compare_runs.py --latest-pair --benchmark rag_benchmark_strict --run-name-prefix rag_benchmark_ --print
```

This compares the newest two runs under `runs/`. Use `--benchmark` and `--run-name-prefix` when you want to avoid cross-family comparisons. Each run writes `summary_compact.json` / `summary_compact.csv` alongside the full `summary.json` and `report.md`.
Latest pointers: `runs/latest_rag_lenient` and `runs/latest_rag_strict`.

Bring your own docs (domain pack):

```powershell
python .\scripts\build_rag_domain_pack.py --in ".\examples\domain_pack_example.jsonl" --out-dir "data"
.\scripts\run_rag_benchmark.ps1 -Preset strict -ModelPath "<MODEL_PATH>"
```

Note: this overwrites `data/rag_domain_stale.jsonl` and `data/rag_domain_authority.jsonl`.

Defaults live in [configs/rag_thresholds.json](../configs/rag_thresholds.json) (lenient/strict). Thresholds include `value_acc`, `exact_acc`, `entailment`, `cite_f1`, and `answer_correct_given_selected` (answer correctness given selected support); strict raises the thresholds. Adjust per dataset; closed-book strict on the domain pack is expected to fail until retrieval/open-book wiring is in place.

The strict preset also includes smaller/harder datasets.

Domain pack contents:

- Policy handbook stale-doc traps (`data/rag_domain_stale.jsonl`)
- Policy handbook authority decoys (`data/rag_domain_authority.jsonl`)
- Policy handbook exceptions (`data/rag_domain_exception.jsonl`)

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
- `run_rag_benchmark.ps1` now writes `preds_<dataset>.jsonl` by default for direct drilldown.

Trap cycle helpers:

```powershell
.\scripts\trap_cycle.ps1 -Mode explore -Preset strict -DatasetId domain_stale -ModelPath "<MODEL_PATH>"
.\scripts\trap_cycle.ps1 -Mode enforce -Preset strict -DatasetId domain_stale -RunDir "<RUN_DIR>" -Family domain_stale
```

Open-book vs closed-book (what to expect):

- Closed-book strict is expected to fail on the domain pack (no access to the source docs).
- Open-book should improve value_acc and cite_f1 on the same doc family when retrieval is working.
- Compare the two reports to show the gap:
  - Closed-book strict: `runs/<strict_run>/report.md`
  - Open-book demo: `runs/<open_book_run>/rag_open_book_run/report.md`
- A healthy open-book run will also show a non-zero `retrieval_hit_rate` in the report.

Pinned example (open-book, citations good ≠ answers correct): see `docs/sample_artifacts/open_book_citation_gap` (`cite_f1=1.00`, `value_acc=0.60` on `n=5`). This is why strict runs also gate on answer correctness and entailment.

Reports also include a **citation gap warning** when `cite_f1` is high but `value_acc` is low (to flag “citations look good, answer is wrong” cases).

Example signature (illustrative, not guaranteed): an open-book run may show materially higher `value_acc`/`cite_f1` and non-zero `retrieval_hit_rate` compared to closed-book strict on the same family (e.g., `value_acc~0.58`, `cite_f1~0.96` on `n=24`).

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
