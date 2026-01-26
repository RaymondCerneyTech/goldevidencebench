# AGENTS.md (Repo House Rules)

These rules apply to the entire repository.

## Prompts
- Keep prompts minimal and unambiguous.
- Prefer programmatic evaluation over subjective judging.

## Change size
- Prefer small, PR-sized changes (focused diffs; avoid drive-by refactors).
- If a large change is necessary, split it into incremental commits/patches (within the same task) and keep each step verifiable.

## Tests
- Always run the test suite locally before finishing a task: `python -m pytest`.
- Add or update tests when changing behavior.

## Docs
- Update `README.md` whenever behavior, CLI, formats, or defaults change.
- When README changes, ensure this `AGENTS.md` stays accurate (house rules + current contracts).

## Scope & platform
- Windows-first repo; prefer PowerShell entrypoints, with Python entrypoints for portability.
- Keep changes aligned with the regression harness + gate system; avoid scope creep.

## Hygiene
- Run outputs can be large; use `scripts/cleanup_runs.ps1` when needed.

## Architecture (weak-machine intent)
- 7B is the planner + candidate generator (steps, candidates, postconditions); it does not execute directly.
- Tiny gates (rules/linear/logistic/small MLP) choose among candidates, block unsafe actions, and trigger abstain.
- Tools execute; verifiers confirm; failures are tagged with trap family + root cause.

## Near-term build plan (gate training loop)
1) `extract_gate_features(trace/obs)` -> dataset for one family.
2) `train_gate_model(family, dataset)` -> weights (logistic regression or tiny MLP).
3) `gate_score_candidates(candidates, x)` -> ranked choice / abstain.
4) Integrate into runs: 7B proposes candidates; gate picks/blocks; verifier checks.

## Completion & next phase
- When auto-curriculum is exhausted and all gates are green, freeze the trap suite + holdout list as a versioned contract.
- Pin release gate outputs and use the release check as the acceptance signal.
- After freezing, focus on end-to-end demos and external validity fixtures; keep SA offline as an oracle.

## Demo milestone (Notepad)
- Use the gate map + preselect rules with the 7B planner and close the app after save:
  - `GOLDEVIDENCEBENCH_UI_GATE_MODELS=.\configs\ui_gate_models.json`
  - `GOLDEVIDENCEBENCH_UI_PRESELECT_RULES=1`
  - `.\scripts\run_notepad_demo.ps1 -ModelPath <path> -Text "<msg>" -FilePath "<path>" -OnExistingFile rename -InputMode type -VerifySaved -CloseAfterSave`
- Prompt routing for safe demos lives in `scripts/run_demo.ps1` and `configs/demo_presets.json`.
- `scripts/run_demo.ps1` supports `-PromptForText` (manual input) and `-GenerateText` (7B-generated) for the Notepad demo.

## Current contracts (keep in sync)
- Adapter schema version: `1.0` (adapter outputs must include `value`, `support_ids` list; extra fields rejected).
- Results output: `--results-json` writes JSON (object or array); `--out` writes predictions JSONL.
- Cited memory: memory JSONL entries must be citation-backed and verified at read time; gate summary lives at `runs/release_gates/memory_verify.json`.
