# CODEX Compatibility Report

Generated: 2026-02-09T03:53:57.418476+00:00

## Scope
- Verify family lifecycle compatibility (generator -> scorer -> wrapper -> reliability checker).
- Verify docs/script consistency for trap-family contracts.
- Export orthogonality diagnostics from observed failure modes (fallback: family mode taxonomy).

## Math Contract Used
- Single-run pass: `P[f,r] = 1` iff all required thresholds pass and canary rule holds.
- Reliability: all runs pass + bounded jitter on selected holdout metrics.
- Orthogonality: `1 - |A ∩ B| / |A ∪ B|` over family mode IDs.

## Artifacts
- `runs/codex_compat/family_matrix.json`
- `runs/codex_compat/orthogonality_matrix.json`
- `runs/codex_compat/scaffold_backlog.json`

## Mismatches
- none

## Unfilled Tracker
- none

## Pairwise Orthogonality
| Family A | Family B | Orthogonality | Intersection |
| --- | --- | ---: | --- |
| compression_loss_bounded | compression_recoverability | 0.857 | parse_failure |
| compression_recoverability | novel_continuity | 0.857 | citation_gap |
| compression_recoverability | novel_continuity_long_horizon | 0.875 | citation_gap |
| novel_continuity | novel_continuity_long_horizon | 0.875 | citation_gap |
| compression_recoverability | compression_roundtrip_generalization | 0.917 | citation_gap |
| compression_roundtrip_generalization | novel_continuity | 0.917 | citation_gap |
| compression_roundtrip_generalization | novel_continuity_long_horizon | 0.923 | citation_gap |
| authority_under_interference | authority_under_interference_hardening | 1.000 | - |
| authority_under_interference | compression_loss_bounded | 1.000 | - |
| authority_under_interference | compression_recoverability | 1.000 | - |
| authority_under_interference | compression_roundtrip_generalization | 1.000 | - |
| authority_under_interference | epistemic_calibration_suite | 1.000 | - |
| authority_under_interference | myopic_planning_traps | 1.000 | - |
| authority_under_interference | novel_continuity | 1.000 | - |
| authority_under_interference | novel_continuity_long_horizon | 1.000 | - |
| authority_under_interference | referential_indexing_suite | 1.000 | - |
| authority_under_interference_hardening | compression_loss_bounded | 1.000 | - |
| authority_under_interference_hardening | compression_recoverability | 1.000 | - |
| authority_under_interference_hardening | compression_roundtrip_generalization | 1.000 | - |
| authority_under_interference_hardening | epistemic_calibration_suite | 1.000 | - |
| authority_under_interference_hardening | myopic_planning_traps | 1.000 | - |
| authority_under_interference_hardening | novel_continuity | 1.000 | - |
| authority_under_interference_hardening | novel_continuity_long_horizon | 1.000 | - |
| authority_under_interference_hardening | referential_indexing_suite | 1.000 | - |
| compression_loss_bounded | compression_roundtrip_generalization | 1.000 | - |
| compression_loss_bounded | epistemic_calibration_suite | 1.000 | - |
| compression_loss_bounded | myopic_planning_traps | 1.000 | - |
| compression_loss_bounded | novel_continuity | 1.000 | - |
| compression_loss_bounded | novel_continuity_long_horizon | 1.000 | - |
| compression_loss_bounded | referential_indexing_suite | 1.000 | - |
| compression_recoverability | epistemic_calibration_suite | 1.000 | - |
| compression_recoverability | myopic_planning_traps | 1.000 | - |
| compression_recoverability | referential_indexing_suite | 1.000 | - |
| compression_roundtrip_generalization | epistemic_calibration_suite | 1.000 | - |
| compression_roundtrip_generalization | myopic_planning_traps | 1.000 | - |
| compression_roundtrip_generalization | referential_indexing_suite | 1.000 | - |
| epistemic_calibration_suite | myopic_planning_traps | 1.000 | - |
| epistemic_calibration_suite | novel_continuity | 1.000 | - |
| epistemic_calibration_suite | novel_continuity_long_horizon | 1.000 | - |
| epistemic_calibration_suite | referential_indexing_suite | 1.000 | - |
| myopic_planning_traps | novel_continuity | 1.000 | - |
| myopic_planning_traps | novel_continuity_long_horizon | 1.000 | - |
| myopic_planning_traps | referential_indexing_suite | 1.000 | - |
| novel_continuity | referential_indexing_suite | 1.000 | - |
| novel_continuity_long_horizon | referential_indexing_suite | 1.000 | - |

## Reproduction Commands
```powershell
python .\scripts\build_codex_compat_report.py
python .\scripts\build_codex_compat_report.py --out-dir runs/codex_compat --report-path docs/CODEX_COMPAT_REPORT.md
```
