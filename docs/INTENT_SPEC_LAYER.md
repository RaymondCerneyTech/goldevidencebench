# Intent Spec Layer

This document defines the user-intent disambiguation layer ("cash-register layer")
for underspecified requests.

## Problem

Underspecified prompts can produce technically valid but user-invalid outputs
("genie dilemma").

## Goal

Ask only when ambiguity risk is high, and only for constraints that change the
plan or final action.

## Minimal Request Profile

Store only small, task-relevant fields:

- `goal`
- `constraints`
- `risk_policy` (e.g., conservative vs aggressive)
- `execution_style` (e.g., terse vs detailed)
- `accepted_facts` with support IDs
- `open_questions`

No hidden profile mutation. User can override or clear profile state.

## Trigger Policy

Trigger clarification menu when at least one is true:

- high ambiguity score
- irreversible action with unresolved constraints
- conflicting constraints or evidence
- low epistemic confidence + non-empty `needed_info`

## Output Shape

When triggered, return bounded options:

```json
{
  "clarification_needed": true,
  "choices": [
    {"id": "A", "label": "Conservative"},
    {"id": "B", "label": "Balanced"},
    {"id": "C", "label": "Aggressive"}
  ],
  "missing_constraints": ["..."],
  "why": ["..."]
}
```

## Planned Trap Family

Family: `intent_spec_layer`

Core metrics:

- `clarification_precision`
- `clarification_recall`
- `user_burden_score`
- `downstream_error_reduction`

Promotion expectation:

- burden stays bounded while downstream errors decrease
- stable 3-run reliability with low jitter
