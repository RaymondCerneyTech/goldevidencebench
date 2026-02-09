# Run Log

This file records representative runs with the model name and outcome. Use **relative** run paths and avoid absolute paths.
Keep the Summary section short and move older entries to [RUN_LOG_ARCHIVE.md](RUN_LOG_ARCHIVE.md).

## Summary entries

## 2026-02-08 - Unified reliability signal (strict + orthogonal families)

Run artifact: `runs\reliability_signal_latest.json`

- Status: PASS
- strict reference: `runs\rag_benchmark_20260206_111309_server_strict\summary_compact.json` (PASS)
- required family reliability files: all PASS
  - compression
  - novel continuity
  - novel continuity long horizon
  - authority under interference
  - authority under interference hardening
  - compression roundtrip generalization
  - myopic planning traps
  - referential indexing suite
  - epistemic calibration suite

Interpretation:

- Release gate is currently green for this branch.
- This is a bounded claim over defined trap families and thresholds, not a universal capability claim.
- Stage maturity is mixed: some families are already at target contracts, while others still pass at observe stage and should be hardened to ramp/target.

## 2026-01-29 - Case pack (qwen2.5-7b-instruct-q5_k_m-00001-of-00002.gguf)

Run dir: `runs/case_pack_20260129_110749`

- Status: PASS
- RAG closed-book strict: FAIL (value_acc 0.255, cite_f1 0.219)
- RAG open-book: PASS (value_acc 0.583, cite_f1 0.958, tokens/q 227)

## 2026-01-29T12:30:49.6270948-06:00 - Case pack (<MODEL_NAME>)

Run dir: `runs/case_pack_20260129_123049`

- Status: PASS
- RAG closed-book strict: FAIL (value_acc 0.495, cite_f1 0.458)
- RAG open-book: PASS (value_acc 0.583, cite_f1 0.958, tokens/q 227)

## 2026-01-29T19:51:12.3930994-06:00 - Case pack (deepseek-coder-6.7b-instruct.Q5_K_M.gguf)

Run dir: `runs/case_pack_20260129_195112`

- Status: PASS
- RAG closed-book strict: FAIL (value_acc 0.495, cite_f1 0.458)
- RAG open-book: PASS (value_acc 0.25, cite_f1 0.875, tokens/q 315.9)

## 2026-01-29T20:54:12.3912816-06:00 - Case pack (qwen2.5-7b-instruct-q5_k_m-00001-of-00002.gguf)

Run dir: `runs/case_pack_20260129_205412`

- Status: FAIL
- RAG closed-book strict: FAIL (value_acc 0.495, cite_f1 0.458)
- RAG open-book: PASS (value_acc 0.583, cite_f1 0.958, tokens/q 227)

## 2026-01-29T21:06:55.0348537-06:00 - Case pack (deepseek-coder-6.7b-instruct.Q5_K_M.gguf)

Run dir: `runs/case_pack_20260129_210655`

- Status: FAIL
- RAG closed-book strict: FAIL (value_acc 0.495, cite_f1 0.458)
- RAG open-book: PASS (value_acc 0.25, cite_f1 0.875, tokens/q 315.9)

## 2026-01-29T21:36:33.0324143-06:00 - Case pack (qwen2.5-7b-instruct-q5_k_m-00001-of-00002.gguf)

Run dir: `runs/case_pack_20260129_213633`

- Status: FAIL
- RAG closed-book strict: FAIL (value_acc 0.495, cite_f1 0.458)
- RAG open-book: PASS (value_acc 0.583, cite_f1 0.958, tokens/q 227)

## 2026-01-29T21:50:13.7627437-06:00 - Case pack (deepseek-coder-6.7b-instruct.Q5_K_M.gguf)

Run dir: `runs/case_pack_20260129_215013`

- Status: FAIL
- RAG closed-book strict: FAIL (value_acc 0.495, cite_f1 0.458)
- RAG open-book: PASS (value_acc 0.25, cite_f1 0.875, tokens/q 315.9)

---

Add new entries here when you run new models or change configs. Keep values short and link to the run directory.

## 2026-02-04 17:38 accuracy-first rerun
run_dir: runs\rag_benchmark_20260204_173339_acc
base_dir: runs\rag_benchmark_20260204_142802

| dataset | value_acc (before) | value_acc (after) | exact_acc (before) | exact_acc (after) | entailment (before) | entailment (after) | cite_f1 (before) | cite_f1 (after) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| KV commentary | 0.800 | 1.000 | 0.800 | 1.000 | 0.800 | 1.000 | 1.000 | 1.000 |
| KV commentary (large) | 0.700 | 1.000 | 0.600 | 1.000 | 0.600 | 1.000 | 0.800 | 1.000 |
| GoldEvidenceBench | 0.700 | 0.900 | 0.700 | 0.800 | 0.700 | 1.000 | 1.000 | 0.800 |

## 2026-02-06 00:32 accuracy-first rerun
run_dir: runs\rag_benchmark_20260205_194826_server_strict
base_dir: runs\rag_benchmark_20260204_183542_server_strict

| dataset | value_acc (before) | value_acc (after) | exact_acc (before) | exact_acc (after) | entailment (before) | entailment (after) | cite_f1 (before) | cite_f1 (after) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| KV commentary | 0.907 | na | 0.856 | na | 0.997 | na | 0.856 | na |
| KV commentary (large) | 0.903 | na | 0.897 | na | 0.996 | na | 0.901 | na |
| GoldEvidenceBench | 0.906 | na | 0.823 | na | 1.000 | na | 0.823 | na |

## 2026-02-06 03:35 accuracy-first rerun
run_dir: runs\rag_benchmark_20260206_010829_server_strict
base_dir: C:\AI\code\GoldEvidenceBench\runs\rag_benchmark_20260205_194826_server_strict

| dataset | value_acc (before) | value_acc (after) | exact_acc (before) | exact_acc (after) | entailment (before) | entailment (after) | cite_f1 (before) | cite_f1 (after) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| KV commentary | 0.992 | na | 0.934 | na | 1.000 | na | 0.930 | na |
| KV commentary (large) | 0.993 | na | 0.988 | na | 1.000 | na | 0.988 | na |
| GoldEvidenceBench | 0.994 | na | 0.908 | na | 1.000 | na | 0.908 | na |

## 2026-02-06 13:42 accuracy-first rerun
run_dir: runs\rag_benchmark_20260206_111309_server_strict
base_dir: runs\rag_benchmark_20260206_010829_server_strict

| dataset | value_acc (before) | value_acc (after) | exact_acc (before) | exact_acc (after) | entailment (before) | entailment (after) | cite_f1 (before) | cite_f1 (after) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| KV commentary | 0.992 | na | 0.934 | na | 1.000 | na | 0.930 | na |
| KV commentary (large) | 0.993 | na | 0.988 | na | 1.000 | na | 0.988 | na |
| GoldEvidenceBench | 0.994 | na | 0.908 | na | 1.000 | na | 0.908 | na |
