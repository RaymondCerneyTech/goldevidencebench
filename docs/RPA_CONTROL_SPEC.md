# RPA Control Spec

This spec defines runtime control decisions driven by reliability artifacts.
It is additive to existing trap gates.

## Contract

Controller output contract (`runs/rpa_control_latest.json`):

```json
{
  "mode": "reason|plan|act",
  "decision": "answer|abstain|ask|retrieve|verify|defer",
  "confidence": 0.0,
  "risk": 0.0,
  "horizon_depth": 0,
  "needed_info": [],
  "support_ids": [],
  "reversibility": "reversible|irreversible",
  "why": []
}
```

## Inputs

`scripts/build_rpa_control_snapshot.py` reads:

- `runs/reliability_signal_latest.json`
- `runs/epistemic_calibration_suite_reliability_latest.json`
- `runs/authority_under_interference_hardening_reliability_latest.json`
- `runs/myopic_planning_traps_reliability_latest.json`
- `runs/referential_indexing_suite_reliability_latest.json`
- `runs/novel_continuity_long_horizon_reliability_latest.json`

It also loads latest holdout means from each family run for richer signal use.

## Mode Switching Rules (initial policy)

- `reason`:
  - confidence below floor, or missing dependencies (`needed_info` non-empty)
  - high authority conflict risk
- `plan`:
  - planning signal below floor (`planning_score`, trap-entry, horizon risk)
- `act`:
  - confidence/risk acceptable and no blocking dependencies

Decision policy:

- if reliability is unstable and risk is high: `defer`
- in `reason`: prefer `retrieve` for authority risk, otherwise `ask`/`abstain`
- in `plan`: `verify` for irreversible operations, otherwise `retrieve`
- in `act`: allow `answer`; force `verify` when irreversible and risk/confidence is weak

## Usage

PowerShell:

```powershell
.\scripts\run_rpa_control_snapshot.ps1 -Reversibility reversible
```

Python:

```bash
python .\scripts\build_rpa_control_snapshot.py --reversibility reversible --out runs\rpa_control_latest.json
```

## Notes

- This controller does not replace family gates.
- Family gates remain source of truth for promotion.
- Controller is an online policy layer to reduce error propagation between gate runs.
