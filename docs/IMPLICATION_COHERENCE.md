# Implication Coherence (IC)

Implication coherence measures whether the system preserves valid consequence
chains over time.

## Definition

A model is implication-coherent when it:

1. Preserves prerequisites (no dependency omissions).
2. Avoids contradiction with accepted state.
3. Distinguishes causal implications from coincidence/correlation.
4. Updates downstream conclusions when upstream assumptions change.

## Why It Matters

Many long-horizon failures are implication breaks:

- locally plausible outputs that violate prior constraints,
- stale assumptions that are not propagated,
- correlation treated as causality.

IC is therefore a runtime control variable for Reason-Plan-Act reliability.

## Trap Coverage

The `implication_coherence` family includes deterministic anchor/holdout/canary
coverage for:

- dependency omission,
- state-update propagation,
- coincidence-vs-causality discrimination,
- contradiction persistence/repair,
- counterfactual stability.

## Metrics

Holdout means:

- `implication_consistency_rate`
- `dependency_coverage`
- `contradiction_repair_rate`
- `causal_precision`
- `propagation_latency_steps`
- `implication_break_rate`
- `ic_score`

Composite:

`IC_score = 0.30*implication_consistency_rate + 0.20*dependency_coverage + 0.20*contradiction_repair_rate + 0.15*causal_precision + 0.15*(1 - implication_break_rate)`

## Controller Contract Additions

`runs/rpa_control_latest.json` includes IC-relevant decision metadata:

```json
{
  "decision": "answer|abstain|ask|retrieve|plan|think_more",
  "needed_info": ["..."],
  "assumptions_used": ["..."],
  "implications": [
    {"from":"assumption_or_fact_id","to":"claim_or_decision_id","type":"causal|logical|correlative","strength":0.0}
  ],
  "support_ids": ["..."]
}
```

## Target Promotion Floors

- `ic_score >= 0.75`
- `implication_break_rate <= 0.10`
- `contradiction_repair_rate >= 0.80`
- no regression in unified reliability signal

## Controller Hooks

RPA policy should treat IC as a hard control input:

- low `ic_score` or missing dependencies: prefer `ask`/`retrieve`/`plan` over direct `act`,
- contradiction pressure: require repair/verify before irreversible actions,
- high confidence with weak causal precision: downgrade to `plan`/`verify`,
- irreversible actions: require both confidence and IC above stricter floors.
