# Retrieval, learner model and memory (Stage 4)

How Aporia personalizes and grounds a hint beyond the problem and the student's code.

```
 knowledge/concepts.yaml ─┐                         ┌─ notes (top 3, concept-filtered)
 knowledge/notes/*.md ────┼─ ingest ─▶ concept_notes ┤
 problem seen first time ─┴─ summarize ▶ problem_summaries ─ analogous problems (level 4 only)
 failed run (grounded) ──▶ mistakes (1 sentence + embedding) ─ similar past mistakes (this device)
 submissions ────────────▶ concept_mastery (BKT p_known per concept) ─ weak concepts in the query
```

## Pieces

| Piece | Where | Notes |
|---|---|---|
| Taxonomy | `knowledge/concepts.yaml`, `app/rag/taxonomy.py` | 40 concepts; validator rejects duplicates, missing prerequisites, cycles |
| Notes | `knowledge/notes/<slug>.md` | original writing, 250-400 words, `reviewed: false` until a human checks them |
| Embedder | `app/rag/embedder.py` | `LiteLLMEmbedder` (batch 64, retries with backoff), `FakeEmbedder` (tests), Redis cache `sha256(model+text)` 30 days |
| Ingestion | `app/rag/ingest.py` | chunks by `##` section (short ones merge, long ones split), embeds only changed chunks |
| Summaries | `app/rag/summarize.py`, `summarize_problem_job` | own-words summary + 1 to 3 taxonomy tags; invalid slug retries once, then `needs_review` |
| Retrieval | `app/rag/retrieve.py` | `tsvector` GIN + pgvector HNSW (cosine), fused by RRF (k=60), optional cross-encoder rerank |
| Learner | `app/learner/` | hand-written BKT (`p_init=0.2, p_learn=0.15, p_guess=0.2, p_slip=0.1`), mistakes, weak concepts |
| Hint context | `app/hints/retrieval_context.py` | builds the `<notes>`, `<past_mistakes>`, `<analogous_problems>` blocks |

## What the model sees, and what it must not do
Prompts `hint_l*_v3.md` tell the model to treat notes as background and never quote them, to mention
a past mistake at most once and only if relevant, and (level 4) to invent a **new** small problem.
The guard enforces it: `quotes_source` (12 consecutive words from a retrieved note), `restates_problem`
(level 4, 8 consecutive words from the statement) and the judge prompt `guard_judge_v3`.
The `done` event carries `sources: [{type: "note", slug, heading}]` (empty when the safe hint was
served), shown as "Based on" chips.

## Privacy
Server-side learner data is keyed by the **device hash** and holds only concept ids, one-sentence
descriptions (for example "Returns a wrong answer when the array is empty."), mastery numbers and
embeddings. **No code and no problem statement text** is stored in `problem_summaries`, `mistakes`
or `events`. Mistake sentences are built deterministically from the failure kind and the minimal
failing input (`app/learner/describe.py`), never from code. See `docs/DECISIONS.md`.

## Switches
- `APORIA_EMBEDDING_MODEL` (provider model string; empty = RAG off, hints stay prompt-only).
  Vectors shorter than `EMBED_DIM = 1536` are zero-padded, which leaves cosine similarity unchanged.
- `APORIA_RERANK=1` enables `BgeReranker` (`uv sync --group rerank`; large download).
- Eval only (`APORIA_ENV=eval`): `X-Aporia-Disable-RAG: 1` and `X-Aporia-Disable-Memory: 1`.
- `APORIA_REQUIRE_REVIEWED_NOTES=1` ingests only notes marked `reviewed: true`.

## Commands
```
cd apps/api
uv run python ../../scripts/validate_knowledge.py        # structure of taxonomy + notes
uv run python ../../scripts/mark_reviewed.py --list      # review status
uv run python -m app.rag.ingest                          # notes -> database
uv run python ../../evals/retrieval/run.py               # docs/results/retrieval.md
uv run python ../../evals/retrieval/hint_quality.py --api http://localhost:8001  # needs eval API
```
