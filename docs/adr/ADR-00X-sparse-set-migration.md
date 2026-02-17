# ADR-00X: Sparse-Set State Store Migration (Planned)

## Status
Accepted (planning-phase only; no default cutover in this release cycle).

## Context
Runtime control and cross-app pack execution require stable entity identity, deterministic replay, and low-overhead state updates.  
Current state handling works functionally but does not yet expose a dedicated backend abstraction for comparing alternate storage strategies.

## Decision
Adopt an interface-first migration:

1. Introduce `StateStore` API and keep `current` backend as default.
2. Add `sparse_set` backend as experimental placeholder behind an explicit backend selector.
3. Defer production cutover until benchmark + invariants criteria are met.

## Why This Decision
This minimizes blast radius while enabling measurable backend comparison:

- no behavior break for existing paths,
- deterministic backend selection,
- explicit contract for replay/snapshot/invariants,
- benchmark-ready for later cutover.

## Risks and Blast Radius
- Risk of divergence between backends if invariants are weak.
- Risk of hidden runtime assumptions in code paths that bypass `StateStore`.
- Blast radius is currently contained because `current` remains the default.

## Benchmark Plan
Use `scripts/benchmark_state_store.py` to compare:

- throughput (`ops_per_s`),
- event volume,
- active state volume.

Run at multiple operation counts and key cardinalities for both:

- `--backend current`
- `--backend sparse_set`

## Cutover Criteria (Future v1.1/v2)
Sparse-set may become default only when all are true:

1. Invariants pass for both backends:
   - stable IDs,
   - deterministic replay,
   - reversible updates.
2. At least 20% decision-cycle latency improvement or clear memory reduction.
3. Zero regression in strict multi-outcome promotion tests.

## Non-Goals for This ADR
- No immediate replacement of current backend.
- No release-gate hard dependency on sparse-set benchmarks in this phase.
