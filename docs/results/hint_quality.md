# Hint quality: RAG and memory on/off

Generated 2026-11-21 by `evals/retrieval/hint_quality.py`.

- Cases: 30 synthetic (invented problems, levels 1 to 3); 120 replies
- Hint model: `ollama_chat/qwen3.5:9b-q4_K_M`; judge model: `ollama_chat/qwen3.5:9b-q4_K_M`
- Scores are LLM-judge ratings from 1 to 5 (higher is better); no_leakage 5 means nothing of the solution was revealed. Small differences are within the noise of a single run.

| condition | correctness | socratic | specificity | no_leakage | with sources | scored / total |
|---|---|---|---|---|---|---|
| baseline (RAG off, memory off) | 5.00 | 4.73 | 4.83 | 4.93 | 0 | 30 / 30 |
| RAG only | 5.00 | 4.80 | 4.73 | 4.93 | 30 | 30 / 30 |
| memory only | 5.00 | 4.83 | 4.90 | 5.00 | 0 | 30 / 30 |
| RAG + memory | 5.00 | 4.77 | 4.90 | 4.97 | 30 | 30 / 30 |

Change from baseline to RAG + memory: correctness +0.00, socratic +0.03, specificity +0.07, no_leakage +0.03.
