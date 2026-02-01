# Codex Phase 1 Log

## Repo entrypoints found
- .\scripts\run_release_check.ps1 (main release flow; calls summary generation)
- .\scripts\run_ui_release_check.ps1 (UI-focused release checks)
- .\scripts\run_instruction_override_gate.ps1 (deterministic gate)
- .\scripts\run_update_burst_* (update burst sweeps)
- .\scripts\summarize_results.py (writes summary.json for bench runs)

## Where run completes / where summary is produced
- .\scripts\summarize_results.py reads runs/combined.json and writes summary.json + summary.csv.
- .\scripts\summarize_ui_fixture.py writes ui_*_summary.json for UI stubs.

## Chosen integration point
- Option A: .\scripts\summarize_results.py
- Rationale: already runs at the end of core bench scripts and writes summary.json; minimal additive wiring.

## Where diagnosis.json is written
- Next to summary.json in the same run output directory, filename diagnosis.json.

## Files changed (running list)
- docs/codex_phase1_log.md
- configs/diagnosis_thresholds.json
- src/goldevidencebench/diagnosis.py
- tests/test_diagnosis.py
- .\scripts\summarize_results.py
- docs/codex_tasks/actionable_diagnosis.md
- README.md
- .\scripts\run_reference.ps1

## Commands to run tests
- python -m pytest

## Example output captured
- Actionable Diagnosis: PASS - primary bottleneck = answering
- Top fix: No bottleneck detected; expand coverage (Effort: S, Impact: M)
