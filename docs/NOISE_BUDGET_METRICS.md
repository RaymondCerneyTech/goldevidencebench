# Noise Budget Metrics

This spec tracks long-horizon noise accumulation and correction pressure.

## Model

Per-step noise proxy:

```
N_t = alpha * N_{t-1} + epsilon_t - beta * C_t
```

- `epsilon_t`: new error signal introduced at step `t`
- `C_t`: corrective signal (retrieval, verification, hard constraints)
- `alpha`: carry-over from previous state
- `beta`: correction gain

## Operational Signals

Use measured proxies from trap families:

- `trap_entry_rate` (myopic planning)
- `authority_violation_rate` / `latest_support_hit_rate` (authority)
- `hallucinated_expansion_rate` / `stale_pointer_override_rate` (referential)
- `overclaim_rate`, `abstain_f1`, `needed_info_recall` (epistemic)

## Derived Metrics

- `noise_slope`: linear fit slope of `N_t` over horizon
- `recovery_latency`: steps to return below safe noise threshold
- `irrecoverable_drift_rate`: fraction of episodes that never recover

## Control Actions

Escalate controller behavior when noise budget degrades:

- low risk: stay in `reason`/`plan` with retrieval
- medium risk: force `verify` before irreversible actions
- high risk: `defer` and request constraint clarification

## Planned Trap Family

Family: `noise_escalation`

Core metrics:

- `noise_slope`
- `recovery_latency`
- `irrecoverable_drift_rate`
- `mode_switch_accuracy` (with RPA controller in loop)

Promotion expectation:

- bounded noise slope
- bounded irrecoverable drift
- stable recovery under holdout perturbations
