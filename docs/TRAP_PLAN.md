# Trap Plan (and why this exists)

This plan keeps trap families focused, repeatable, and scalable. The goal is to
avoid an endless list of one-off tests and instead build a small set of
high-leverage families that can be generated, gated, and composed.

## Why a trap plan

- **Stop infinite scope.** Without a plan, traps grow unbounded and feel like
  bespoke chores. A family + generator is the unit of scale.
- **Make skills measurable.** Passing a trap is a narrowly scoped skill gain.
  Chaining those gains leads to emergent robustness, but only if the traps are
  consistent and enforced.
- **Protect against regressions.** Traps are the easiest way to catch drift in
  long-horizon state updates where bugs are subtle and expensive.

This is reverse requirements derivation: repeated failures define the contract.

## Definitions

- **Trap:** a deterministic, narrowly scoped failure pattern.
- **Trap family:** a generator + small anchor set that produces many variants of
  a failure pattern.
- **Skill (operational):** consistently passing the traps in a family.

## Principles

1. **Narrow > broad.** Each trap should target a single failure mode.
2. **Deterministic > clever.** If it cannot be reproduced, it cannot be gated.
3. **Minimal evidence.** Small, auditable artifacts beat huge logs.
4. **Composable.** Families should combine cleanly into higher-order tests.
5. **Low maintenance.** A family must have a generator and a small holdout set.

## Scope (what we focus on)

Core families should align with the critical path of long-context state updates:

- **Authority + spoofing** (avoid low-authority evidence)
- **Stale vs latest state** (prefer latest authoritative update)
- **Wrong-path workflows** (commit policy discipline)
- **Instruction conflicts** (override vs obey)
- **State integrity across steps** (drift prevention)

New families are only added if they block a real workflow or a known regression.

## Priority category sets (execution order)

Use these as the main build sequence for efficient progress. Each set is
orthogonal, so passing one does not hide failures in another.

1. **Novel continuity core** (active)
   - **Goal:** preserve identity, timeline, and constraints over long chains.
   - **Primary contracts:** `identity_acc`, `timeline_acc`, `constraint_acc`,
     plus value/exact continuity.
   - **Why first:** highest leverage for long-horizon coherence and drift
     prevention.
2. **Compression roundtrip** (active)
   - **Goal:** compact state aggressively without losing recoverable facts.
   - **Primary contracts:** loss-bounded precision/recall/bloat and
     recoverability value/exact/citation metrics.
   - **Why second:** enables lower-cost long context while preserving state.
3. **Authority under interference** (active + hardening)
   - **Goal:** pick latest authoritative facts under stale/decoy/noisy evidence.
   - **Primary contracts:** stale-vs-latest correctness, authority filtering,
     wrong-update suppression, abstain calibration under ambiguity.
   - **Why third:** blocks silent bad commits that poison later steps.
4. **Myopic planning traps** (active; target-stage pass)
   - **Goal:** avoid locally good but globally bad choices in multi-step tasks.
   - **Primary contracts:** trap-entry rate, first-error step, recovery rate,
     horizon success.
   - **Why fourth:** converts short-horizon correctness into long-horizon policy
     reliability.
5. **Referential indexing suite** (active; target-stage pass)
   - **Goal:** preserve indexing/reassembly fidelity under compression pressure.
   - **Primary contracts:** coverage/precision/recall/fidelity with bounded
     hallucination and stale-pointer override rates.
   - **Why fifth:** converts compression quality into explicit pointer-graph
     reliability.
6. **Epistemic calibration suite** (active; target-stage pass)
   - **Goal:** reduce false certainty and route uncertain cases correctly.
   - **Primary contracts:** overclaim, abstain behavior, calibration (`ece`,
     `brier`), selective accuracy, needed-info recall.
   - **Why sixth:** prevents high-confidence wrong commits from bypassing
     otherwise strong families.

### Promotion rule (all sets)

Promote a set to release-quality signal only when all are true:

- anchors + holdout hard gate PASS,
- canary behaves as intended (expected-fail or clear degradation),
- 3-run reliability PASS with low jitter,
- no regressions in strict RAG release signal.

### Promotion integrity policy (anti-gaming)

- Never overwrite `*_reliability_latest.json` with a failed candidate.
- Before stage experiments, pin baseline as
  `*_reliability_pinned_<timestamp>.json`.
- Write non-promoted trials to stage-specific candidates (for example,
  `*_reliability_observe_candidate.json`, `*_reliability_ramp_candidate.json`).
- Promote candidate -> `latest` only on explicit checker `RESULT: PASS`.
- Treat `custom` thresholds as bootstrapping mode; do not treat them as release
  claims unless explicitly documented in release notes.
- For release-quality claims, target stage should be the default for mature
  families.
- For robustness hardening, prefer multi-run campaigns (`RunCount=5+`) with
  tighter jitter ceilings (for example `MaxJitter=0.02`) before promotion.
- Use `scripts/run_robustness_threshold.ps1` for one-command hard-mode
  campaigns across long-horizon critical families.

### Release-quality meaning

Passing release gates means a bounded capability envelope, not universal
intelligence. The claim is:

- behavior is reliable on the measured trap sets,
- behavior is stable across reruns (jitter bounded),
- regressions are blocked before ship,
- failures remain localized enough for targeted repair.

### Current verified state (February 8, 2026)

Latest verified aggregate signal:

- `runs/reliability_signal_latest.json` -> `PASS`
- strict RAG reference: `runs/rag_benchmark_20260206_111309_server_strict/summary_compact.json` -> `PASS`
- scaffold backlog: `runs/codex_compat/scaffold_backlog.json` -> `unfilled_count=0`

Current family reliability status:

- `compression` -> `PASS`
- `novel_continuity` -> `PASS` (`target` cite-stage)
- `novel_continuity_long_horizon` -> `PASS` (`target` cite-stage)
- `authority_under_interference` -> `PASS`
- `authority_under_interference_hardening` -> `PASS`
- `compression_roundtrip_generalization` -> `PASS` (`target` stage)
- `myopic_planning_traps` -> `PASS` (`target` stage)
- `referential_indexing_suite` -> `PASS` (`target` stage)
- `epistemic_calibration_suite` -> `PASS` (`target` stage, strict parse/confidence/proxy floors enforced)

### Immediate implementation order

1. Keep `myopic_planning_traps`, `compression_roundtrip_generalization`, and
   `referential_indexing_suite` pinned at `target`:
   - treat current target-stage files as regression baselines.
2. Keep `epistemic_calibration_suite` in target mode and improve canary
   sharpness:
   - maintain strict parse/confidence contracts (`parse_rate=1.0`,
     `confidence_provided_rate=1.0`, `confidence_proxy_used_rate=0.0`),
   - keep needed-info extraction robust as fixtures get harder.
3. Keep release anti-gaming discipline:
   - keep pinned baselines,
   - only promote PASS candidates,
   - track stage provenance in `RUN_LOG`.
4. Run periodic robustness-threshold campaigns:
   - use `scripts/run_robustness_threshold.ps1 -Stage target -RunCount 5 -MaxJitter 0.02`,
   - require unified reliability signal PASS with derived floors
     (`min_reasoning_score`, `min_planning_score`, `min_intelligence_index`).

### Next control-layer expansion

Trap gates now provide stable measurement for the current envelope. The next
step is runtime control from those signals.

1. Add a runtime **Reason-Plan-Act** snapshot per turn:
   - script: `scripts/build_rpa_control_snapshot.py`
   - wrapper: `scripts/run_rpa_control_snapshot.ps1`
   - artifact: `runs/rpa_control_latest.json`
2. Enforce mode/decision switching from measured signals:
   - low confidence or missing dependencies -> `reason` + `ask/retrieve`
   - planning risk or trap pressure -> `plan` + `retrieve/verify`
   - safe/reversible and confidence above floor -> `act` + `answer`
3. Track expansion blockers for next families:
   - script: `scripts/build_codex_next_step_report.py`
   - artifact: `runs/codex_next_step_report.json`
4. Scaffolded control families (ready for staged triplets):
   - `rpa_mode_switch`
     - generator: `scripts/generate_rpa_mode_switch_family.py`
     - scorer: `scripts/score_rpa_mode_switch.py`
     - wrapper: `scripts/run_rpa_mode_switch_family.ps1`
     - checker: `scripts/check_rpa_mode_switch_reliability.py`
   - `intent_spec_layer`
     - generator: `scripts/generate_intent_spec_family.py`
     - scorer: `scripts/score_intent_spec.py`
     - wrapper: `scripts/run_intent_spec_family.ps1`
     - checker: `scripts/check_intent_spec_reliability.py`
   - `noise_escalation`
     - generator: `scripts/generate_noise_escalation_family.py`
     - scorer: `scripts/score_noise_escalation.py`
     - wrapper: `scripts/run_noise_escalation_family.ps1`
     - checker: `scripts/check_noise_escalation_reliability.py`

## Family structure (required)

Each trap family should ship with:

1. **Generator** (script or fixture pattern)
2. **Anchor cases** (small, fixed set for fast feedback)
3. **Holdout set** (stable, CI-gated)
4. **Canary** (expected-fail baseline for sensitivity)
5. **Success metric** (value/exact/entailment/cite_f1 or policy pass rate)

If any of these are missing, the family is experimental and not gateworthy.

## Prioritization rubric

Score each candidate family (1-3) on:

- **Frequency:** how often this failure appears in real runs
- **Severity:** how bad the failure is when it happens
- **Recoverability:** how hard it is to detect or repair downstream
- **Chain leverage:** how much it improves the overall skill chain

Only implement families with a high composite score.

## Planned families (compression + extraction)

These two families are designed to measure memory compression with recoverability.
They should be implemented together and used as a paired gate.

**compression_loss_bounded**
- **Goal:** reward minimal, loss-bounded summaries of long ledgers.
- **Generator outline:**
  - Build a long ledger with many updates, decoys, and distractors.
  - Define authoritative updates per key (SET/CLEAR) and a gold compact state.
  - Ask for a compact state snapshot (schema + versioned).
  - Score on retained authoritative facts (precision/recall) and bloat.
- **Scaffold:** `scripts/generate_compression_loss_bounded_family.py`,
  `scripts/score_compression_loss_bounded.py`,
  `data/compression_loss_bounded/compression_loss_bounded_anchors.jsonl`.

**compression_recoverability**
- **Goal:** ensure compressed state still supports correct extraction.
- **Generator outline:**
  - Take the compressed snapshot from the paired family.
  - Ask questions that require only the retained authoritative facts.
  - Require citations/UIDs when applicable.
  - Score on exact/value accuracy, entailment, and cite_f1.
- **Scaffold:** `scripts/generate_compression_recoverability_family.py`,
  `scripts/score_compression_recoverability.py`,
  `data/compression_recoverability/compression_recoverability_anchors.jsonl`.

### Compression status (2026-02-06)

Current compression-family scaffold status from anchor/holdout runs:

- Anchors (`n=8`): `precision=0.9375`, `recall=0.9167`, `f1=0.9250`,
  `bloat=0.0000`, `parse_rate=1.0000` -> **PASS**.
- Holdout (`n=24`): `precision=0.9167`, `recall=0.9167`, `f1=0.9167`,
  `bloat=0.0000`, `parse_rate=0.9167` -> **PASS**.
- Canary: now generated as a multi-row stress profile
  (`compression_loss_bounded_canary.jsonl`, `expected_fail=true` per row).
  Use it as a sensitivity signal and track fail-rate stability over time.

Operational acceptance bands for this family:

- Anchors:
  - `precision >= 0.90`
  - `recall >= 0.90`
  - `bloat <= 0.20`
  - `parse_rate >= 0.90`
- Holdout:
  - `precision >= 0.90`
  - `recall >= 0.90`
  - `bloat <= 0.20`
  - `parse_rate >= 0.90`
  - `exact_match_rate >= 0.85`

Canary rule for now:

- Keep anchor + holdout as the hard gate.
- Track canary fail-rate; if canary starts passing consistently, refresh the
  stress generator so it remains a sensitivity check.

Canary hardening status:

- `compression_loss_bounded` canary is multi-row stress (`expected_fail=true`).
- `compression_recoverability` canary is multi-row stress with tail-key lookup,
  larger snapshots, and mixed null/non-null query targets (`expected_fail=true`).

Next implementation steps:

1. Use `scripts/run_compression_families.ps1` as the paired runner (anchors +
   holdout hard gate, canary sensitivity warning) and track the combined summary.
2. Tune compression prompts/settings only when anchor/holdout regress; use
   canary drift to detect silent overfitting.

Compression reliability contract (not a daily cadence):

- Reliability means **repeatability across independent runs**, not a single pass.
- Run compression families at least 3 times and require:
  - hard gate PASS on every run,
  - holdout thresholds PASS on every run,
  - low jitter across runs on holdout means.
- Use `scripts/check_compression_reliability.py` to enforce this contract.

Unified release-quality signal:

- Use `scripts/check_reliability_signal.py` (or
  `scripts/check_reliability_signal.ps1`) to aggregate:
  - latest strict RAG summary (`runs/latest_rag_strict`)
  - `runs/compression_reliability_latest.json`
  - `runs/novel_continuity_reliability_latest.json`
  - `runs/authority_under_interference_reliability_latest.json`
  - `runs/compression_roundtrip_generalization_reliability_latest.json`
  - `runs/novel_continuity_long_horizon_reliability_latest.json`
  - `runs/myopic_planning_traps_reliability_latest.json`
  - `runs/referential_indexing_suite_reliability_latest.json`
  - `runs/epistemic_calibration_suite_reliability_latest.json`
  - `runs/authority_under_interference_hardening_reliability_latest.json`
  - `runs/rpa_mode_switch_reliability_latest.json`
  - `runs/intent_spec_layer_reliability_latest.json`
  - `runs/noise_escalation_reliability_latest.json`
- Treat this as the current ship/no-ship signal for this branch.
- Release/nightly defaults now require `rpa_mode_switch`, `intent_spec_layer`,
  and `noise_escalation` in the unified signal; use
  `-SkipRequireControlFamilies` only for diagnostics.
- The unified signal now emits derived controller-aligned scores:
  - `reasoning_score` (strict + authority + referential + epistemic + roundtrip),
  - `planning_score` (myopic + long-horizon continuity),
  - `intelligence_index = sqrt(reasoning_score * planning_score)`.
- Optional hard floors can be enforced directly in the checker:
  - `--min-reasoning-score <0..1>`
  - `--min-planning-score <0..1>`
  - `--min-intelligence-index <0..1>`
- Keep strict domain hard checks enabled (`domain_stale/domain_authority/
  domain_exception exact_acc == 1.0`) unless you are explicitly running
  diagnostics.
- Require stage discipline: do not point `*_latest` to observe/custom outputs
  unless that is explicitly the approved stage for the current cycle.

### Codex compatibility artifacts

Build a machine-readable compatibility snapshot before changing contracts:

- `runs/codex_compat/family_matrix.json`
- `runs/codex_compat/orthogonality_matrix.json`
- `docs/CODEX_COMPAT_REPORT.md`

Command:

- `python .\scripts\build_codex_compat_report.py`

Use this report to catch:

- docs mention without scripts,
- scripts without docs mention,
- mode-overlap spikes between families (orthogonality drop).

## Planned family status (novel continuity)

`novel_continuity` is now scaffolded with the same lifecycle pattern:

- Generator: `scripts/generate_novel_continuity_family.py`
  - emits deterministic `anchors`, `holdout`, `canary`
  - dimensions: `identity`, `timeline`, `constraint`
  - canary profile: long retcon chains with expected-fail stress
- Scorer: `scripts/score_novel_continuity.py`
  - metrics: `value_acc`, `exact_acc`, `cite_f1`, `parse_rate`
  - per-dimension: `identity_acc`, `timeline_acc`, `constraint_acc`
- Wrapper run: `scripts/run_novel_continuity_family.ps1`
  - runs anchors/holdout/canary
  - writes combined summary at `<run_dir>/novel_continuity_summary.json`
  - hard gate = anchors + holdout pass
- Reliability checker: `scripts/check_novel_continuity_reliability.py`
  - requires multi-run pass on hard gate + holdout floors + jitter limits

Suggested operating contract:

- Single-run gate:
  - anchors: `value/exact >= 0.80`
  - holdout: `value/exact >= 0.85`
  - holdout per-dimension: `identity/timeline/constraint >= 0.80`
  - citation floor is staged:
    - `observe` stage: `min_cite_f1 = 0.00`
    - `ramp` stage: `min_cite_f1 = 0.60`
    - `target` stage: `min_cite_f1 = 0.85`
    - `custom` stage: use explicit cite floors
- Reliability gate (3 runs):
  - every run hard-gate PASS
  - holdout floors PASS on every run
  - jitter limits:
    - `value_acc` jitter <= `0.05`
    - `exact_acc` jitter <= `0.05`
    - `cite_f1` jitter <= `0.05`

Staged rollout commands:

- Wrapper:
  - `.\scripts\run_novel_continuity_family.ps1 -CiteStage observe`
  - `.\scripts\run_novel_continuity_family.ps1 -CiteStage ramp`
  - `.\scripts\run_novel_continuity_family.ps1 -CiteStage target`
- Reliability:
  - `python .\scripts\check_novel_continuity_reliability.py --run-dirs "<RUN_A>" "<RUN_B>" "<RUN_C>" --cite-stage observe`
  - `python .\scripts\check_novel_continuity_reliability.py --run-dirs "<RUN_A>" "<RUN_B>" "<RUN_C>" --cite-stage ramp`
- `python .\scripts\check_novel_continuity_reliability.py --run-dirs "<RUN_A>" "<RUN_B>" "<RUN_C>" --cite-stage target`

## Planned family status (compression roundtrip generalization)

`compression_roundtrip_generalization` is now scaffolded with the same lifecycle:

- Generator: `scripts/generate_compression_roundtrip_generalization_family.py`
  - emits deterministic `anchors`, `holdout`, `canary`
  - query-type coverage: `direct`, `aggregate`, `exception`, `negation`
  - tracks orthogonal tags: `tail`, `null/non-null`, `large_snapshot`
- Scorer: `scripts/score_compression_roundtrip_generalization.py`
  - core metrics: `value_acc`, `exact_acc`, `cite_f1`, `parse_rate`
  - subset metrics: `direct_acc`, `aggregate_acc`, `exception_acc`,
    `negation_acc`, `tail_key_acc`, `null_target_acc`,
    `nonnull_target_acc`, `large_snapshot_acc`
- Wrapper run:
  `scripts/run_compression_roundtrip_generalization_family.ps1`
  - runs anchors/holdout/canary and writes
    `<run_dir>/compression_roundtrip_generalization_summary.json`
- Reliability checker:
  `scripts/check_compression_roundtrip_generalization_reliability.py`
  - enforces multi-run pass + holdout floors + jitter bounds

Suggested operating contract:

- Single-run gate:
  - stage-driven floors:
    - `observe`: low floors for baseline signal shaping
    - `ramp`: intermediate floors for hardening
    - `target`: strict floors (`value/exact/cite_f1 >= 0.85`, subset metrics `>= 0.80`)
    - `custom`: explicit min-* args
- Reliability gate (3 runs):
  - hard-gate PASS on every run
  - holdout floors PASS on every run
  - jitter limits on `value_acc`, `exact_acc`, `cite_f1` <= `0.05`

Commands:

- Wrapper:
  - `.\scripts\run_compression_roundtrip_generalization_family.ps1 -Adapter "goldevidencebench.adapters.llama_server_adapter:create_adapter" -Stage observe -OverwriteFixtures`
  - `.\scripts\run_compression_roundtrip_generalization_family.ps1 -Adapter "goldevidencebench.adapters.llama_server_adapter:create_adapter" -Stage ramp`
  - `.\scripts\run_compression_roundtrip_generalization_family.ps1 -Adapter "goldevidencebench.adapters.llama_server_adapter:create_adapter" -Stage target`
- Reliability:
  - `python .\scripts\check_compression_roundtrip_generalization_reliability.py --run-dirs "<RUN_A>" "<RUN_B>" "<RUN_C>" --stage observe --out "runs\compression_roundtrip_generalization_reliability_latest.json"`
  - `python .\scripts\check_compression_roundtrip_generalization_reliability.py --run-dirs "<RUN_A>" "<RUN_B>" "<RUN_C>" --stage ramp --out "runs\compression_roundtrip_generalization_reliability_latest.json"`
  - `python .\scripts\check_compression_roundtrip_generalization_reliability.py --run-dirs "<RUN_A>" "<RUN_B>" "<RUN_C>" --stage target --out "runs\compression_roundtrip_generalization_reliability_latest.json"`

## Planned family status (novel continuity long horizon)

`novel_continuity_long_horizon` is now scaffolded with the same lifecycle:

- Generator: `scripts/generate_novel_continuity_long_horizon_family.py`
  - emits deterministic `anchors`, `holdout`, `canary`
  - increases callback distance and contradiction pressure
  - toggles delayed dependency and repair-transition patterns per case
- Scorer: `scripts/score_novel_continuity_long_horizon.py`
  - core metrics: `value_acc`, `exact_acc`, `cite_f1`, `parse_rate`
  - per-dimension: `identity_acc`, `timeline_acc`, `constraint_acc`
  - long-horizon subsets: `long_gap_acc`, `high_contradiction_acc`,
    `delayed_dependency_acc`, `repair_transition_acc`
- Wrapper run: `scripts/run_novel_continuity_long_horizon_family.ps1`
  - runs anchors/holdout/canary and writes
    `<run_dir>/novel_continuity_long_horizon_summary.json`
  - supports staged citation rollout (`observe`, `ramp`, `target`, `custom`)
- Reliability checker:
  `scripts/check_novel_continuity_long_horizon_reliability.py`
  - enforces multi-run pass + holdout floors + jitter bounds

Suggested operating contract:

- Single-run gate:
  - anchors: `value/exact >= 0.80`, subset metrics `>= 0.70`
  - holdout: `value/exact >= 0.85`, subset metrics `>= 0.80`
  - citation floor is staged:
    - `observe`: `min_cite_f1 = 0.00`
    - `ramp`: `min_cite_f1 = 0.60`
    - `target`: `min_cite_f1 = 0.85`
- Reliability gate (3 runs):
  - hard-gate PASS on every run
  - holdout floors PASS on every run
  - jitter limits on `value_acc`, `exact_acc`, `cite_f1` <= `0.05`

Staged rollout commands:

- Wrapper:
  - `.\scripts\run_novel_continuity_long_horizon_family.ps1 -CiteStage observe`
  - `.\scripts\run_novel_continuity_long_horizon_family.ps1 -CiteStage ramp`
  - `.\scripts\run_novel_continuity_long_horizon_family.ps1 -CiteStage target`
- Reliability:
  - `python .\scripts\check_novel_continuity_long_horizon_reliability.py --run-dirs "<RUN_A>" "<RUN_B>" "<RUN_C>" --cite-stage observe`
  - `python .\scripts\check_novel_continuity_long_horizon_reliability.py --run-dirs "<RUN_A>" "<RUN_B>" "<RUN_C>" --cite-stage ramp`
  - `python .\scripts\check_novel_continuity_long_horizon_reliability.py --run-dirs "<RUN_A>" "<RUN_B>" "<RUN_C>" --cite-stage target`

## Planned family status (authority under interference)

`authority_under_interference` is now scaffolded with the same lifecycle:

- Generator: `scripts/generate_authority_under_interference_family.py`
  - emits deterministic `anchors`, `holdout`, `canary`
  - each case includes stale authoritative repeats + NOTE decoys + latest
    authoritative update (SET/CLEAR)
- Scorer: `scripts/score_authority_under_interference.py`
  - core metrics: `value_acc`, `exact_acc`, `cite_f1`, `parse_rate`
  - interference metrics: `latest_support_hit_rate`, `note_citation_rate`,
    `stale_citation_rate`, `authority_violation_rate`
- Wrapper run: `scripts/run_authority_under_interference_family.ps1`
  - runs anchors/holdout/canary and writes
    `<run_dir>/authority_under_interference_summary.json`
- Reliability checker:
  `scripts/check_authority_under_interference_reliability.py`
  - enforces multi-run pass + floors + jitter bounds

Suggested operating contract:

- Single-run gate:
  - anchors: `value/exact >= 0.85`, `cite_f1 >= 0.80`,
    `latest_support_hit_rate >= 0.80`,
    `authority_violation_rate <= 0.10`
  - holdout: `value/exact >= 0.90`, `cite_f1 >= 0.85`,
    `latest_support_hit_rate >= 0.90`,
    `authority_violation_rate <= 0.05`
- Reliability gate (3 runs):
  - every run hard-gate PASS
  - holdout floors PASS on every run
  - canary sensitivity holds (`canary.exact_rate <= 0.85` by default)
  - jitter limits:
    - `value_acc` jitter <= `0.05`
    - `exact_acc` jitter <= `0.05`
    - `cite_f1` jitter <= `0.05`
    - `authority_violation_rate` jitter <= `0.05`
    - `canary.exact_rate` jitter <= `0.05`

## Planned family status (authority under interference hardening)

`authority_under_interference_hardening` is scaffolded with the same lifecycle:

- Generator: `scripts/generate_authority_under_interference_hardening_family.py`
- Scorer: `scripts/score_authority_under_interference_hardening.py`
- Wrapper run: `scripts/run_authority_under_interference_hardening_family.ps1`
  - writes `<run_dir>/authority_under_interference_hardening_summary.json`
- Reliability checker:
  `scripts/check_authority_under_interference_hardening_reliability.py`

Suggested operating contract:

- Holdout hard gate:
  - `value_acc >= 0.92`
  - `exact_acc >= 0.92`
  - `cite_f1 >= 0.88`
  - `latest_support_hit_rate >= 0.92`
  - `authority_violation_rate <= 0.03`
- Reliability gate (3 runs):
  - hard gate PASS in every run
  - jitter <= `0.05` for value/exact/cite_f1/authority_violation

## Planned family status (referential indexing suite)

`referential_indexing_suite` is scaffolded as a grouped indexing/reassembly
set. Subfamilies are tagged in `meta.family_id` and scored independently:

- `index_loss_bounded`
- `reassembly_recoverability`
- `minimal_pointer_set`
- `reconstruction_fidelity`
- `no_invention_expansion`
- `stale_pointer_conflict`
- `wrong_hub_attraction`
- `assembly_order_traps`
- `wrong_address_traps`

Scaffold components:

- Generator: `scripts/generate_referential_indexing_suite_family.py`
- Scorer: `scripts/score_referential_indexing_suite.py`
- Wrapper run: `scripts/run_referential_indexing_suite_family.ps1`
- Reliability checker:
  `scripts/check_referential_indexing_suite_reliability.py`

Primary metrics:

- `pointer_set_size`, `part_coverage_recall`, `pointer_precision`,
  `pointer_recall`, `reassembly_fidelity`
- `hallucinated_expansion_rate`, `stale_pointer_override_rate`,
  `lookup_depth_cost`

## Planned family status (epistemic calibration suite)

`epistemic_calibration_suite` is scaffolded as a grouped know-what-you-know
set. Subfamilies are tagged in `meta.family_id`:

- `known_answerable`
- `unknown_unanswerable`
- `near_miss_familiar`
- `contradictory_evidence`
- `missing_key_dependency`
- `confidence_inversion`

Scaffold components:

- Generator: `scripts/generate_epistemic_calibration_suite_family.py`
- Scorer: `scripts/score_epistemic_calibration_suite.py`
- Wrapper run: `scripts/run_epistemic_calibration_suite_family.ps1`
- Reliability checker:
  `scripts/check_epistemic_calibration_suite_reliability.py`

Primary metrics:

- `overclaim_rate`, `abstain_precision`, `abstain_recall`, `abstain_f1`
- `ece`, `brier`, `selective_accuracy_at_coverage`, `needed_info_recall`
- `kkyi` composite score

Current hardening target:

- move from permissive bootstrap/custom floors to stage `ramp` then `target`,
- keep `overclaim_rate` low while increasing `abstain_f1` and
  `needed_info_recall`,
- treat epistemic as release-blocking only when the promoted `latest` file is a
  PASS from the approved stage.

## Scaffold tracking (unfilled work)

Run:

- `python .\scripts\build_codex_compat_report.py`

Artifacts:

- `runs/codex_compat/family_matrix.json`
- `runs/codex_compat/orthogonality_matrix.json`
- `runs/codex_compat/scaffold_backlog.json`
- `docs/CODEX_COMPAT_REPORT.md`

Use `runs/codex_compat/scaffold_backlog.json` as the canonical list of what is
still unfilled (`missing_scripts`, `missing_docs`, or no `PASS` reliability
signal).

## Lifecycle

1. **Prototype:** generator + anchors, no gate
2. **Stabilize:** add holdout + canary + thresholds
3. **Gate:** enforce in CI / release check
4. **Retire:** only if superseded by a broader family or no longer relevant

## Evidence and logging

Every family change should:

- Add a short entry in `docs/RUN_LOG.md`
- Include a before/after summary (use `scripts/append_run_log_summary.py`)
- Record exact configs and run dirs

## Noise control

Use these rules to avoid gating on noise:

- **Measure variance first.** Run the same anchors 2-3 times to estimate baseline spread.
- **Use paired comparisons.** Compare before/after on the *same* cases.
- **Require effect size.** Ignore deltas that fall inside the noise band.
- **Add margins.** Gate with hysteresis (e.g., pass at 0.82, fail at 0.78).
- **Keep a stable holdout.** Use a small, fixed set as the anti-noise check.
- **Flag noisy families.** Treat high-variance families as diagnostic until stable.

## Tight loop (minimum viable gating)

This is the smallest loop that still yields reliable signal:

1. **Anchors (3-8 cases):** detect the pattern quickly with low cost.
2. **Fix + rerun anchors:** confirm the change flips the failure.
3. **Mini holdout (10-20 cases):** verify it generalizes beyond anchors.
4. **Full gate (rare):** run the full suite only when mini holdout is green.

If a change does not move anchors, do not escalate. If anchors move but the
mini holdout fails, treat it as brittle and iterate.

**Operational checklist:**
- Anchor size: 3-8 cases
- Mini holdout size: 10-20 cases
- Max rows: keep low for anchors (e.g., 10-50)
- Max book tokens: cap aggressively for anchors (e.g., 400-800)

## Fast-vs-full acceptance bands

Use `strict_fast256` as the daily gate and `strict` as release confirmation.
Compare means with `scripts/compare_runs.py` and apply these exact bands.

### Stage A: fast gate (decide whether to run full strict)

`strict_fast256` must satisfy all of:

- Domain hard checks (from fast run):
  - `domain_stale.exact_acc = 1.0`
  - `domain_authority.exact_acc = 1.0`
  - `domain_exception.exact_acc = 1.0`
- Mean delta checks vs latest full strict baseline (`fast - full >= -band`):
  - `value_acc`: band `0.005`
  - `exact_acc`: band `0.005`
  - `entailment`: band `0.005`
  - `answer_correct_given_selected`: band `0.005`
  - `cite_f1`: band `0.005`
  - `instruction_acc`: band `0.010`
  - `state_integrity_rate`: band `0.005`

If any check fails, do not run full strict; iterate on anchors/mini holdout.

### Stage B: full strict acceptance (update baseline or reject)

After full strict, compare against the prior full strict baseline.
Accept as new baseline if all are true (`new - base >= -band`):

- `value_acc`: band `0.003`
- `exact_acc`: band `0.003`
- `entailment`: band `0.003`
- `answer_correct_given_selected`: band `0.003`
- `cite_f1`: band `0.003`
- `instruction_acc`: band `0.007`
- `state_integrity_rate`: band `0.003`

These bands are intentionally tighter than Stage A because both runs are full
suite measurements.

### Escalation rule

If Stage A passes but Stage B fails, treat as sampling brittleness:

1. run one more `strict_fast256` on the same adapter/settings;
2. if still near the Stage A boundary, increase fast rows to `512` before
   spending another full strict run.

## Integration notes (control loop framing)

Treat traps as the measurement layer in a control loop: run -> measure -> adjust
-> rerun -> gate. The traps do not change the model by themselves, but they
provide a reliable signal that can drive updates in prompts, fine-tunes, RAG,
or routing policies.

MoE and tooling synergy: paired families (e.g., compression + recoverability)
can expose expert specialization and routing stability. Tooling changes (new
retrievers, tool APIs, memory modules) can be gated the same way, keeping the
system behavior stable while the internals evolve.

Hybrid ideal: use rules/constraints for hard invariants, models for ambiguous
reasoning, and traps to keep the combined system aligned to its contract.
Rules encode hard invariants; traps encode concrete edge cases so the rules
can evolve without losing prior coverage.
Seesaw loop: alternate between opening exploration (let the system try) and
tightening enforcement (gate the failures you now understand). This oscillation
is the engine: explore -> name the contract -> build traps -> gate -> repeat.

## Capabilities and operating modes

GoldEvidenceBench turns ambiguous model behavior into a contract-driven,
auditable system: you define the playable field (fixtures + thresholds), and
artifacts make every failure inspectable and repeatable. Each trap family is a
minimal selector for a narrowly scoped skill; broad capability comes from
composing a small, well-chosen portfolio and keeping routing/selection stable.

Operate intentionally in two modes:

- **Experience mode (explore):** maximize coverage to discover failure modes.
- **Goal mode (enforce):** gate the contract to preserve invariants.

Pairing families (e.g., compression_loss_bounded + compression_recoverability)
prevents optimizations from "cheating" the objective by shrinking state without
preserving recoverable facts.

## Counterexample refinement (useful defaults)

Treat trap building as counterexample-guided refinement:

1. **Explore (wide, no new gates):** generate many variants and log failures.
2. **Identify (one lever):** pick a single failure mode class.
3. **Name the contract:** write the "must never happen" invariant.
4. **Shrink to anchors:** minimize failures into small, stable cases.
5. **Enforce (gate):** add anchors + holdout + canary to CI/release.

Property-based testing mindset helps here: search for counterexamples, then
shrink them until they are the smallest reproducible failure.

## Explore vs enforce modes

- **Explore mode:** maximize coverage, tolerate noise, and mine failures into
  future anchors. No new gates.
- **Enforce mode:** freeze minimal anchors and holdouts, then gate changes.
  Keep gates small until they flip reliably.

## Gate promotion checklist (risk + detectability)

Promote a family to a hard gate only when:

- **Impact:** the failure is high-severity or blocks a real workflow.
- **Prevalence:** it shows up in real runs or regressions.
- **Detectability:** the metric is stable (low variance).
- **Fix leverage:** solving it improves multiple downstream behaviors.

## Non-goals

- Exhaustive coverage of all possible failure modes
- General "intelligence" improvements without measurable behavior change
- One-off traps without a reusable generator

## Next steps

- Use this plan when adding or revising families in `docs/TRAP_FAMILIES.md`.
- Keep the core family set small and high leverage.

## Research ledger (source-tracked)

Use this as a living map of external findings that affect trap design.

### Verified signals

- **Transformer linear readout is the final prediction interface.**
  - **What we use:** making hidden states more linearly separable can improve
    downstream prediction and selector behavior.
  - **Source:** Vaswani et al., *Attention Is All You Need* (NeurIPS 2017),
    output projection + softmax.
    https://arxiv.org/abs/1706.03762
- **Trajectory straightening is reported through layers.**
  - **What we use:** geometry diagnostics are plausible for continuity and
    compaction analysis, but metric definitions must match the paper exactly.
  - **Source:** *LLMs Implicitly Learn to Straighten Neural Sentence
    Trajectories* (NeurIPS 2023).
    https://proceedings.neurips.cc/paper_files/paper/2023/hash/88dddaf430b5bc38ab8228902bb61821-Abstract-Conference.html
- **Context structure can change representational geometry.**
  - **What we use:** split trap analysis by regime (continual prediction vs
    structured/few-shot phases) instead of assuming one behavior pattern.
  - **Source:** *Context Structure Reshapes the Representational Geometry of
    Language Models* (arXiv:2601.22364).
    https://arxiv.org/abs/2601.22364
- **Long-horizon failure is often myopic planning failure.**
  - **What we use:** add explicit myopic-trap families and lookahead baselines;
    do not rely only on chain-of-thought style local reasoning.
  - **Source:** *Why Reasoning Fails to Plan* (arXiv:2601.22311).
    https://arxiv.org/abs/2601.22311
- **In-context learning can implement algorithm-like adaptation.**
  - **What we use:** context layout and exemplars are first-class levers in
    trap generation and repair loops, not just model weights.
  - **Sources:** von Oswald et al., ICML 2023 (PMLR v202);
    Li et al., ICML 2023 (PMLR v202).
    https://proceedings.mlr.press/v202/von-oswald23a.html
    https://proceedings.mlr.press/v202/li23l.html

### Information still needed (before hard gating)

- Exact paper-aligned geometry metric definitions we want to standardize on
  (`D/L`, turning-angle curvature, or both), with implementation notes.
- Confirmed planning baseline equations/hyperparameters from full text (not
  abstract summaries), including any UCB/value-backprop details we adopt.
- Backend support decision for hidden-state extraction (required for per-layer
  geometry diagnostics; not required for behavior-level traps).

### Direction recommendations

1. **Prioritize robustness expansion now.**
   Core orthogonal families are target-stage PASS; focus next on harder canaries,
   perturbation stability, and new orthogonal holdouts rather than stage
   promotion.
2. **Treat geometry diagnostics as phase-2.**
   Keep geometry work as optional diagnostics until hidden-state access is
   stable in the serving stack.
3. **Keep paired-family discipline.**
   Continue implementing `compression_loss_bounded` together with
   `compression_recoverability` so memory wins require recoverable facts.
4. **Run the tight loop first, full suite second.**
   Use anchors -> mini holdout -> full gate to reduce token cost while keeping
   a reliable regression signal.
