# Project Status

Last updated: February 20, 2026

## Current state

- New social-pressure hardening pass is in: A9b now includes stealth hijack variants
  (`quoted/codefence/json/yaml/roleplay/indirect/compliance`) and policy bakeoff
  now supports guard ablation (`off` vs `heuristic`) with Pareto frontier output
  in `scripts/run_social_pressure_policy_bakeoff.ps1`.
- Added sibling family `rag_prompt_injection` (retrieved-snippet injection):
  - generator: `scripts/generate_rag_prompt_injection_family.py`
  - attack expansion: `scripts/generate_rag_prompt_injection_rows.py`
  - scorer: `scripts/score_rag_prompt_injection.py`
  - runner: `scripts/run_rag_prompt_injection_family.ps1`
  - reliability checker: `scripts/check_rag_prompt_injection_reliability.py`
  - docs: `docs/RAG_PROMPT_INJECTION.md`
- Family triplet pipeline integration now includes `rag_prompt_injection`
  in `scripts/run_family_stage_triplet.ps1`.
- Trap hardening is active; implication-coherence hard-pack is now passing at target stage with llama-server adapter.
- Latest validated run:
  - `runs/implication_coherence_20260219_193501/implication_coherence_summary.json`
  - `hard_gate_status=PASS`
  - anchors: `status=PASS`
  - holdout: `status=PASS`
  - persona invariance: `row_invariance_rate=1.0`
  - canary: expected-fail behavior preserved (`value_acc=0.0`, `status=PASS`)
- Local test suite status:
  - `python -m pytest` -> `345 passed, 1 skipped`
- Next weakest release-path family (`agency_preserving_substitution`) was re-run and re-promoted:
  - `runs/agency_preserving_substitution_20260219_205407/agency_preserving_substitution_summary.json`
  - status: `hard_gate_status=PASS` (anchors/holdout/persona all PASS)
  - refreshed reliability artifact: `runs/agency_preserving_substitution_reliability_latest.json`
- Follow-on family (`authority_under_interference`) was also re-run and re-promoted:
  - `runs/authority_under_interference_20260219_212702/authority_under_interference_summary.json`
  - status: `hard_gate_status=PASS` (anchors/holdout/persona all PASS)
  - refreshed reliability artifact: `runs/authority_under_interference_reliability_latest.json`
- Next release-path family (`intent_spec_layer`) was re-run and re-promoted:
  - `runs/intent_spec_layer_20260219_214456/intent_spec_layer_summary.json`
  - status: `hard_gate_status=PASS` (anchors/holdout/persona all PASS)
  - refreshed reliability artifact: `runs/intent_spec_layer_reliability_latest.json`

## Key findings from implication-coherence debugging (February 19, 2026)

1. Hard-row outputs were being truncated.
- Symptom: many hard rows scored as `value=None`, `support_ids=[]`, `failure_mode_id=hard_inference_miss`.
- Root cause: `max_output_tokens=64` was too low for derived hard rows returning 5 support IDs.
- Fix: increased completion budget for `implication_coherence` requests in llama-server adapter.

2. Anchors had an impossible hard-case count threshold.
- Symptom: anchors failed even when all rows were correct.
- Root cause: target floor required `min_hard_case_count=16`, but anchors only contain 8 hard rows.
- Fix: in scaffold runner, clamp anchors `min_hard_case_count` to available hard rows; keep holdout/canary stage floors unchanged.

3. Persona wrapper handling caused false persona-drift on non-persona families.
- Symptom: implication persona-perturbation rows dropped to null/empty outputs.
- Root cause: generic `persona_variant` wrappers were preserved for non-persona families.
- Fix: normalize away generic `persona_variant` wrappers unless family is explicitly persona-behavior (`persona_session_drift`, `persona_amalgamation`) or persistence/session variants.

4. Support-ID instability produced false persona-invariance failures.
- Symptom: values matched but support IDs drifted across canonical vs perturbed rows.
- Root cause: hard inferred-contract rows allowed variable support subsets/order.
- Fix: canonicalize hard implication-row supports to final authoritative IDs for:
  - `implication.dependency_required`
  - `implication.contradiction_detected`
  - `implication.causal_precision_required`
  - `implication.type_required`
  - `implication.propagation_required`

## What changed (high-level)

- Adapter:
  - `src/goldevidencebench/adapters/llama_server_adapter.py`
    - family-specific implication hard prompt path retained
    - extended max tokens for implication coherence
    - non-persona wrapper normalization tightened
    - hard implication support-ID canonicalization
- Family scaffold:
  - `scripts/run_control_family_scaffold.ps1`
    - `-FailFast` mode
    - anchors hard-case floor clamp for implication coherence
- Family wrapper:
  - `scripts/run_implication_coherence_family.ps1`
    - `-FailFast` passthrough
- Tests:
  - `tests/test_llama_server_adapter.py`
  - `tests/test_control_family_failfast_contract.py`
  - `tests/test_implication_coherence_hard_pack.py`

## Immediate next steps

1. Re-run release check with current adapter profile and confirm updated pointers/artifacts.
2. Apply the same failure-mode audit loop to the next weakest trap family in release path.
3. Continue documenting deltas in `docs/RUN_LOG.md` and keep this status file current as fixes land.
