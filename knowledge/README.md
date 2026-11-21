# Knowledge base

`concepts.yaml` is the concept taxonomy. `notes/<slug>.md` holds one short study note per concept.

**All notes are original writing.** None is copied or closely paraphrased from an editorial, blog
post, book or any LeetCode material, and none is tied to a specific LeetCode problem.

**They have not been reviewed by a human yet.** Every note starts with `reviewed: false`. Read a
note, check its claims, fix anything wrong, then mark it:

    cd apps/api && uv run python ../../scripts/mark_reviewed.py sliding-window
    cd apps/api && uv run python ../../scripts/mark_reviewed.py --list

Validate structure (frontmatter, sections, 250-400 words, every concept has a note):

    cd apps/api && uv run python ../../scripts/validate_knowledge.py

Ingestion into the database is `cd apps/api && uv run python -m app.rag.ingest`. Notes that are
still `reviewed: false` are ingested too in dev; set `APORIA_REQUIRE_REVIEWED_NOTES=1` to skip them.
