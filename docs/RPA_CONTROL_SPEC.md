# RPA Control Spec

This spec defines runtime control decisions driven by reliability artifacts.
It is additive to existing trap gates.

## Contract v0.2 (additive)

`runs/rpa_control_latest.json` preserves existing v0.1 top-level fields and adds:

- `control_contract_version: "0.2"`
- `control_v2` object:
  - `assumptions_used`: `{id,text,source,confidence}[]`
  - `implications`: `{from,to,type,strength,status}[]`
  - `substitution`: `{requested_option,proposed_option,reason_code,disclosed,authorized,recoverable}`
  - `needed_info`: `{id,kind,required_for,source_hint}[]`
  - `reversibility_detail`: `{class,rationale,verify_required}`
  - `policy`: `{blocked,reasons,required_actions}`

Canonical policy reason codes live in `src/goldevidencebench/rpa_reason_codes.py`.

## Inputs

`scripts/build_rpa_control_snapshot.py` reads:

- `runs/reliability_signal_latest.json`
- `runs/epistemic_calibration_suite_reliability_latest.json`
- `runs/authority_under_interference_hardening_reliability_latest.json`
- `runs/myopic_planning_traps_reliability_latest.json`
- `runs/referential_indexing_suite_reliability_latest.json`
- `runs/novel_continuity_long_horizon_reliability_latest.json`
- optional:
  - `runs/implication_coherence_reliability_latest.json`
  - `runs/agency_preserving_substitution_reliability_latest.json`

## Runtime policy thresholds (locked)

Mode routing:

- `reason` if any:
  - `confidence < 0.60`
  - missing needed info
  - authority conflict risk high
  - `ic_score < 0.75`
  - `implication_break_rate > 0.10`
- `plan` if not `reason` and any:
  - `planning_score < 0.70`
  - `horizon_depth >= 2` with weak continuity/planning support
  - contradiction repair pending
- `act` only when all guards pass

Hard blocks:

- Unauthorized substitution block:
  - if proposed option differs from requested option and not
    `(disclosed && (authorized || policy_required) && recoverable)`,
    force `ask`/`defer`.
- IC block:
  - if `ic_score < 0.75` or `implication_break_rate > 0.10`,
    do not allow irreversible direct answer.
- Irreversible guard requires all:
  - `confidence >= 0.85`
  - `risk <= 0.20`
  - `ic_score >= 0.80`
  - `contradiction_repair_rate >= 0.85`
  - `intent_preservation_score >= 0.90`

## Enforcement surfaces

- Planner path: `scripts/select_ui_plan.py`
  - flags: `--use-rpa-controller --control-snapshot --policy-strict`
  - trace fields per step: `policy_mode`, `policy_decision`, `policy_block_reason`
- Router/demo path: `scripts/run_demo.ps1`
  - flags: `-UseRpaController -ControlSnapshotPath`
  - blocked actions emit deterministic policy output and non-zero exit.

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
- Family gates remain source of truth for promotion/release.
- Controller is an online policy layer to reduce unsafe runtime choices.
