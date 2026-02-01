# Run Log

This file records representative runs with the model name and outcome. Use **relative** run paths and avoid absolute paths.
Keep the Summary section short and move older entries to [RUN_LOG_ARCHIVE.md](RUN_LOG_ARCHIVE.md).

## Summary entries

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
