# Thread + Compaction Artifacts (Example)

Sample run folder layout (from any run that writes `summary.json`):

```
runs/<run_dir>/
  summary.json
  summary_compact.json
  summary_compact.csv
  diagnosis.json
  thread.jsonl
  compact_state.json
  report.md
```

If a run emits gate artifacts in the same folder (e.g., a wall sweep), they are listed under
`last_known_good.gate_artifacts` in `compact_state.json` and summarized in `report.md`.

Each event in `thread.jsonl` includes stable IDs (`case_id`, `step_id`, `candidate_id`, `selected_id`, `gold_id`)
so failures can be traced back to exact cases and decisions.

`thread.jsonl` entries are schema-validated against `schemas/thread_event.schema.json` during compaction.

## report.md (failure locator + decision audit)

`report.md` surfaces the `failure_case_id` from `diagnosis.json` and includes a short **Decision audit**
block (selected_id/gold_id/pred_value/gold_value) for that case. Use the case id to jump to the matching
decision event in `thread.jsonl`.

Note: `gold_value` can be `n/a` when the fixture does not provide `gold.value` (common in some holdouts).
