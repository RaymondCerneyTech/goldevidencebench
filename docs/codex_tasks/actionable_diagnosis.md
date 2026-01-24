# Actionable Diagnosis (Phase 1)

This spec defines the minimal diagnosis output and why-step taxonomy used to
pinpoint the failing decision in a run.

## WhyType (minimal list)
- choose_support
- choose_action
- commit_state
- abstain_or_escalate
- recalibrate
- rollback
- verify

## Evidence examples
When diagnosis includes evidence examples, each example should include:
- why_type (from the list above, if available)
- id (row/task id)
- reason (short, human-readable)

If why_type is not available, set it to null and keep the rest of the example
so downstream tooling can still surface the failure.
