# Thread + Compaction Artifacts (Example)

Sample run folder layout (from any run that writes `summary.json`):

```
runs\example_run\
  summary.json
  diagnosis.json
  thread.jsonl
  compact_state.json
  report.md
```

If a run emits gate artifacts in the same folder (e.g., a wall sweep), they are listed under
`last_known_good.gate_artifacts` in `compact_state.json` and summarized in `report.md`.
