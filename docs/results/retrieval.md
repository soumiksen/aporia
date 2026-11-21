# Retrieval evaluation

Generated 2026-11-20 by `evals/retrieval/run.py`.

- Queries: 115 (0 human-labeled)
- Embedder: `ollama/nomic-embed-text`
- Corpus: concept study notes (chunked by section); concepts are ranked, a concept counts once however many of its chunks are retrieved

> **Provisional.** The relevance labels in `evals/retrieval/pairs.csv` are drafts (only 0 of 115 rows are `labeled`). Do not treat these numbers as final until the labels have been reviewed and corrected by a human.

| mode | P@3 | P@5 | R@5 | MRR | p50 ms | p95 ms |
|---|---|---|---|---|---|---|
| vector | 0.345 | 0.217 | 0.861 | 0.774 | 25 | 33 |
| fts | 0.310 | 0.212 | 0.848 | 0.800 | 4 | 5 |
| hybrid | 0.351 | 0.223 | 0.878 | 0.867 | 7 | 9 |
| hybrid_rerank | - | - | - | - | - | - |

`hybrid_rerank` skipped: APORIA_RERANK is not 1 (reranker disabled).

P@k is the share of the top k concepts that are relevant; R@5 is the share of the relevant concepts found in the top 5; MRR is the mean reciprocal rank of the first relevant concept. Latency includes embedding the query (cached embeddings make repeat runs faster).
