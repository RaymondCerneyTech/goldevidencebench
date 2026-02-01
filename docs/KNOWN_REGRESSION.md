# Known Regression (Canonical Example)

This repo includes a **canonical caught-regression example** from a real case pack run.
It is intentionally set up so the **bad-actor holdout fails** (expected), demonstrating
that the safety gate detects subtle regressions even when a wall passes.

Artifacts for the canonical run pair:

- Baseline one-pager: `runs/case_pack_20260129_205412/case_pack_onepager.md`
- Regressed one-pager: `runs/case_pack_20260129_210655/case_pack_onepager.md`
- Delta report: `runs/case_pack_20260129_210655/delta_report.md`
- Gate artifact (regressed): `runs/case_pack_20260129_210655/bad_actor/holdout/drift_holdout_gate.json`

Regression signal:

- Model B exceeded the drift wall threshold (wall rate > max) and the bad-actor holdout remained failing despite fixes.
- Delta report captures the wall-rate jump: `runs/case_pack_20260129_210655/delta_report.md`

If those files are missing (e.g., runs were cleaned), regenerate with:

```powershell
.\scripts\run_case_pack_latest.ps1 -ModelPath "<MODEL_PATH>" -PdfPath "<PATH_TO_PDF>"
```

Compare the canonical regression pair (full report):

```powershell
.\scripts\run_case_pack_delta_latest.ps1 -Canonical -Full -Print
```

Expected outcome:

- Bad-actor holdout shows **PASS (expected holdout FAIL)** in the one-pager.
- The delta report highlights the regression vs the previous run.
