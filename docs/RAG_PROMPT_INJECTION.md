# RAG Prompt Injection Trap

This family measures whether the model treats retrieved snippets as untrusted
data instead of executable instructions.

## What it targets

Failure pattern:
- baseline answer is correct on clean retrieved context
- attacked row adds an injected instruction inside retrieved snippet text
- model follows snippet instruction and revises away from the original task

Attack matrix:
- `quoted_override`
- `codefence_override`
- `json_override`
- `yaml_override`
- `roleplay_override`
- `indirect_goal_switch`
- `compliance_wrapper`

## Run structure

Per split (`anchors`, `holdout`, `canary`):
1. baseline pass on clean rows
2. attacked row expansion (`scripts/generate_rag_prompt_injection_rows.py`)
3. attacked pass
4. scoring (`scripts/score_rag_prompt_injection.py`)

Injected payloads are embedded in `book` under:
- `## Retrieved Snippet (Untrusted External Content)`

User question remains anchored to the original objective.

## Core metrics

- `flip_rate_to_incorrect`
- `unnecessary_revision_rate`
- `citation_drift_rate`
- `support_omission_rate` (gold support IDs missing)
- `support_contamination_rate` (new unsupported non-gold support IDs introduced vs baseline)
- `non_gold_support_rate` (strict non-gold support presence, regardless of baseline)
- `suggestion_hijacking_goal_drift_rate`
- `suggestion_hijacking_instruction_violation_rate`
- `per_variant_max_flip_rate`

Per-variant details are in:
- `variant_breakdown.<variant_key>`

Release-stage gating should primarily use `support_contamination_rate` and
`support_omission_rate`. `non_gold_support_rate` is diagnostic for baseline
citation hygiene and can be enforced separately when needed.
When `--max-non-gold-support-rate` is set in reliability checking and
`--max-non-gold-support-rate-jitter` is omitted, jitter defaults to `0.05`.
Use `--max-non-gold-support-rate-jitter -1` to disable the non-gold jitter
check explicitly.

## Artifacts

Family run output:
- `*_baseline_preds.jsonl`
- `*_attacked_data.jsonl`
- `*_attacked_preds.jsonl`
- `*_attack_rows.jsonl`
- `anchors_summary.json`, `holdout_summary.json`, `canary_summary.json`
- `rag_prompt_injection_summary.json`

Reliability artifact:
- `runs/rag_prompt_injection_reliability_latest.json`

## Reproduce

Generate fixtures:

```powershell
python .\scripts\generate_rag_prompt_injection_family.py --overwrite
```

Single family run:

```powershell
.\scripts\run_rag_prompt_injection_family.ps1 `
  -Adapter "goldevidencebench.adapters.llama_server_adapter:create_adapter" `
  -Stage target `
  -OverwriteFixtures
```

Multi-run reliability:

```powershell
.\scripts\run_family_stage_triplet.ps1 `
  -Family rag_prompt_injection `
  -Stage target `
  -RunCount 3 `
  -Adapter "goldevidencebench.adapters.llama_server_adapter:create_adapter"
```
