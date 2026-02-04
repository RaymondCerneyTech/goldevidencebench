# RAG Benchmark Report

Runs dir: runs\rag_open_book_demo_20260203_232122\rag_open_book_run
Config: runs\rag_open_book_demo_20260203_232122\rag_open_book_config.json
Generated: 2026-02-04T05:24:33.353190+00:00
Status: PASS

## Thresholds
- value_acc: 0.13
- cite_f1: 0.12

## Contract
PASS if all datasets meet: value_acc >= 0.13, cite_f1 >= 0.12.
FAIL otherwise.

## Runtime
- wall_s_total: 152.42624760000035
- wall_s_per_q: 30.48524952000007
- tokens_per_q: 222.4

## Means
- value_acc: 0.6
- cite_f1: 1.0
- retrieval_hit_rate: 1.0
- instruction_acc: None
- state_integrity_rate: None

## Datasets
| ID | Label | Failure mode | value_acc | cite_f1 | retrieval_hit | wall_s_per_q | tokens_per_q | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| open_book_fact | open_book_fact |  | 0.6000 | 1.0000 | 1.0000 | 30.4852 | 222.4000 | ok |
