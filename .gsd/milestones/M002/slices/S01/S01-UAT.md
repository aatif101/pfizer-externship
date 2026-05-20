# S01: Persisted Retrieval Index Setup — UAT

**Milestone:** M002
**Written:** 2026-05-20T21:06:11.938Z

## UAT: Persisted Retrieval Index Setup

### UAT Type
Developer/operator acceptance test for the offline retrieval indexing foundation.

### Preconditions
1. Use the project repository on Windows from `C:/Users/smati/VS Code Projects/pfizer-externship`.
2. Use the project Python 3.11 virtualenv via `venv/Scripts/python.exe` or `.\venv\Scripts\python.exe`.
3. Have either a fixture SQLite database initialized by tests or a local ingestion database with existing `documents` and `pages` tables.
4. Do not configure provider secrets; this slice must run without Gemini, Claude, Langfuse, GPU, Qdrant, or network access.

### Steps and Expected Outcomes
1. **Status before build**
   - Run: `venv/Scripts/python.exe -m src.retrieval status --db-path <fixture.db>` against a database with ingested pages but no retrieval index run.
   - Expected: command returns a safe missing-index diagnostic with `status=missing`, no raw page text, no provider output, and no secret values.

2. **Build index for an indexable corpus**
   - Run: `venv/Scripts/python.exe -m src.retrieval build --db-path <fixture.db>`.
   - Expected: command succeeds and prints key=value metadata including `status=built`, a `run_id`, indexed document/page counts, source counts, a content hash prefix, and `stale=false`. SQLite now contains persisted retrieval index run metadata and page-level index rows.

3. **Check built status**
   - Run: `venv/Scripts/python.exe -m src.retrieval status --db-path <fixture.db>`.
   - Expected: command reports `status=built`, matching hash prefix/run metadata, indexed page counts, and no raw page text.

4. **Empty corpus behavior**
   - Run build/status against a database with valid ingestion tables but no nonblank ingested page text.
   - Expected: command returns a clear `status=empty` or empty-corpus reason code without crashing and without requiring provider credentials.

5. **Stale corpus behavior**
   - After a successful build, mutate a source page text row or other fingerprinted corpus field.
   - Run: `venv/Scripts/python.exe -m src.retrieval status --db-path <fixture.db>`.
   - Expected: command reports stale state (`stale=true` / stale status) and includes safe comparison metadata so the operator knows a rebuild is needed.

6. **Missing or invalid database behavior**
   - Run status/build against a nonexistent path or a SQLite file without ingestion source tables.
   - Expected: command exits nonzero with a safe reason-coded message and does not silently create a misleading empty index.

7. **Safe-output adversarial text check**
   - Use a fixture with SQL-like filename/page text such as `Robert'); DROP TABLE pages;--`.
   - Expected: build/status succeeds or reports typed diagnostics using parameterized SQL; output does not echo unsanitized raw filename/page text, and ingestion tables remain intact.

### Edge Cases Covered by Automated Tests
- Repeated `init_db` calls are idempotent.
- SQLite without FTS5 remains usable because FTS5 creation is optional/guarded.
- Blank pages and non-ingested documents are excluded from the indexable corpus.
- Page snippets are short whitespace-normalized prefixes, not full raw text dumps.
- Failed page-index writes roll back rather than leaving partial page rows.
- 0-indexed internal page numbers are preserved while DTOs expose 1-indexed display page numbers.

### Operational Readiness
- **Health signal:** `python -m src.retrieval status --db-path <db>` reports missing/built/empty/stale plus counts and hash prefix.
- **Failure signal:** missing DB/table, empty corpus, and stale corpus produce clear status/reason codes and safe nonzero exits where appropriate.
- **Recovery procedure:** create/repair the ingestion database, ingest documents with nonblank page text, or rerun `python -m src.retrieval build --db-path <db>` after a stale status.
- **Monitoring gaps:** no Langfuse/RAG tracing is expected in S01; richer retrieval/generation observability is deferred to downstream M002 slices.

### Not Proven By This UAT
- Retrieval ranking quality, hybrid scoring, evidence thresholds, and weak-evidence abstention are deferred to S02.
- Grounded answer generation and live/fake provider behavior are deferred to S03.
- Streamlit Chat rendering and user chat state are deferred to S04.
- Visual retrieval with ColQwen/Qdrant is not part of this slice.
