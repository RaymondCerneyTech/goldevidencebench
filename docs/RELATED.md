# Related work (links)

This list is intentionally short and curated (not exhaustive).
As of the time this project was created, these were the most relevant touchpoints.

## Long-context + positional sensitivity
- Lost in the Middle (position bias in long contexts): https://arxiv.org/abs/2307.03172
- StreamingLLM / Attention Sinks (long-context behavior + streaming tricks): https://arxiv.org/abs/2309.17453
- LongBench (long-context evaluation suite): https://arxiv.org/abs/2308.14508
- RULER (stress tests for long-context retrieval/selection): https://arxiv.org/abs/2404.06654
- L-Eval (long-context evaluation): https://arxiv.org/abs/2307.11088
- LooGLE (long dependency benchmark): https://arxiv.org/abs/2311.04939
  - LooGLE v2 (newer version): https://arxiv.org/abs/2510.22548
- Context length alone hurts reasoning (relevant to gold present but still fails): https://arxiv.org/abs/2510.05381

## State tracking / long-text motivation (what kicked this off)
- MIT News: PaTH Attention (state tracking / long text): https://news.mit.edu/2025/new-way-to-increase-large-language-model-capabilities-1217

## RAG evaluation toolkits (end-to-end pipelines)
- RAGAS: https://github.com/explodinggradients/ragas
- TruLens: https://www.trulens.org/
- LangSmith evals (practical eval workflows): https://docs.langchain.com/langsmith/evaluation-quickstart
- OpenAI Evals (general eval harness): https://github.com/openai/evals

## Grounded generation + citations / attribution
- KILT (knowledge-intensive tasks + provenance): https://arxiv.org/abs/2009.02252
- ALCE (Attributed LLMs / citation benchmark): https://arxiv.org/abs/2305.14627
- SelfCite (improving citation quality via context ablation): https://arxiv.org/abs/2502.09604
- FRONT (fine-grained grounded citations on ALCE): https://arxiv.org/abs/2408.04568
