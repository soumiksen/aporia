# Results index

Every number in this project comes from a script in the repository; this page links the tables and
says how each was produced and how far to trust it.

| Table | Produced by | Status |
|---|---|---|
| [Retrieval: precision, recall, MRR, latency](results/retrieval.md) | `evals/retrieval/run.py` | Real run, but the 115 relevance labels are **drafts awaiting human review** |
| [Hint quality: RAG and memory on/off](results/hint_quality.md) | `evals/retrieval/hint_quality.py` | Real run (30 cases); generator and judge are the same local 9B model, so weak evidence |
| [Guard: prompted vs classifier-only vs cascade](results/guard.md) | `evals/guard_compare/run.py` | **TODO**: needs the trained classifier (see `ml/README.md`) |
| Red-team leak rates | `pnpm eval:redteam`, `pnpm eval:gate` | Output is git-ignored (`evals/redteam/results/`); the last real run predates Stage 3 |
| Grounding (minimal failing inputs) | `evals/grounding/measure.py` | Synthetic problems with a local test runner; see `docs/GROUNDING.md` |

Offline checks that gate CI (no real models): the red-team suite against the real app with a
scripted model (`redteam-gate` job), the classifier wrapper and cascade with mocked sessions
(`classifier` job), and the unit tests of every metric.
