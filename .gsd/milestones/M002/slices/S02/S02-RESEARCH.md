# S02 Research: Hybrid Retriever and Evidence Gate

## Summary

S02 should build directly on the S01 retrieval-index boundary: `src/retrieval/indexer.py` persists one current run plus page metadata/snippets, and `src/retrieval/repository.py` already maintains optional SQLite FTS5 rows containing normalized page text. What is missing is a query-facing retriever API, query-focused snippet assembly, ranked result DTOs, and a deterministic evidence gate that classifies retrieval as strong enough or weak/off-topic before any generator exists.

Recommended first implementation: keep S02 provider-free and dependency-light. Implement a SQLite/lexical hybrid retriever under `src/retrieval/` using optional FTS5 BM25 when available plus deterministic token-overlap/phrase bonuses as the second signal, then gate evidence using explicit thresholds and reason codes. This satisfies the slice outcome with stable fixture proof and does not introduce `sentence-transformers`/model download risk before the service and UI seams exist. If strict semantic dense retrieval is later required, add it behind the same retriever interface in a later hardening slice.

## Active Requirements / Constraints

- **R005:** S02 owns the first page-level retrieval/citation proof for grounded Q&A. Results must include stable doc id, filename, 1-indexed page number, score, and short verbatim snippet.
- **R008:** Retrieval operations need diagnosable status and reason-coded failures without leaking secrets or raw corpus text through operator surfaces.
- **R009:** Verification should use the project Python 3.11 virtualenv. Current working command shape is `venv/Scripts/python.exe -m pytest ...`; a root `venv.bat` shim also exists.
- **R010:** S02 must stay provider-free: no Gemini/Claude credentials, provider responses, API keys, image blobs, or raw full pages in tests/CLI output.

## Memory / Prior Findings

- Retrieval health commands use compact one-line `key=value` output with reason codes and must not echo filenames/raw page text/image blobs/secrets.
- M002 is intentionally ordered as persisted index setup → retrieval/evidence gate → answer provider seam → Streamlit Chat → final operational proof.
- Text RAG is scoped for M002; visual ColQwen/Qdrant remains out of scope, but DTOs should allow later retriever replacement.
- S01 deliberately hides raw page text from public index DTOs; raw text is confined to repository/indexer/FTS synchronization boundaries.
- Windows gate invocations should prefer `venv/Scripts/python.exe` or `venv.bat` over POSIX-style `./venv/Scripts/python.exe`.

## Implementation Landscape

### Existing files and purpose

- `src/retrieval/models.py`
  - Current DTOs: `RetrievalIndexStatus`, `RetrievalIndexRun`, `RetrievalIndexPageRecord`, `RetrievalIndexStatusReport`.
  - Add S02 DTOs here or in a sibling module: likely `RetrievalHit`, `RetrievalResult`, `EvidenceDecision`/`EvidenceGateResult`, and reason-code enums.
- `src/retrieval/repository.py`
  - Current safe public methods list index rows but do not support search.
  - FTS table is already populated by `save_index_run_with_pages()`/`upsert_page_index_records()` if available.
  - Add internal query helpers here: FTS search, fallback candidate loading, page text/snippet extraction. Keep full page text out of public DTOs.
- `src/retrieval/indexer.py`
  - Current source of status/staleness: `get_retrieval_index_status()` and `load_indexable_pages()`.
  - Retriever should call status first and refuse missing/empty/stale indexes before scoring.
- `src/retrieval/cli.py`
  - Current commands: `build`, `status` only. S02 does not need a user-facing query CLI unless planners want a smoke surface; if added, preserve compact/sanitized output and do not print raw full text.
- `src/retrieval/__init__.py`
  - Exports S01 DTOs and repository helpers. Export S02 public service/DTOs after implementation.
- `src/db/schema.py`
  - Already has `retrieval_index_runs`, `retrieval_index_pages`, optional `retrieval_index_page_fts`.
  - No schema change is required for S02 unless choosing to persist dense embeddings or query logs; avoid that in this slice.
- `src/app.py`
  - Chat tab remains placeholder. S02 should not wire Streamlit yet; S04 owns it.
- `tests/test_retrieval_index_repository.py`, `tests/test_retrieval_indexer.py`, `tests/test_retrieval_cli.py`
  - S01 coverage for index status/build/safety. Add new S02 tests rather than modifying these heavily.
- `tests/test_s05_end_to_end_proof.py`
  - Useful pattern for realistic fixture seeding and verbatim span proof; S02 can reuse the minimal supplier lines without live providers.

### Current dependency state

Local package availability from the project environment:

- `sqlite3`: available; FTS5 works in this environment.
- `numpy`: available transitively.
- `bm25s`: not installed.
- `sentence_transformers`: not installed.
- `sklearn`: not installed.

`pyproject.toml` currently has no BM25/dense retrieval dependencies. Adding `sentence-transformers` would bring a large model/download surface and likely slow/offline-fragile tests. `bm25s` would be lighter but still unnecessary if using SQLite FTS5 BM25 already populated by S01.

## Recommended Design

### Public API shape

Create `src/retrieval/retriever.py`:

- `retrieve_evidence(db_path: str, question: str, *, top_k: int = 5, min_score: float = ..., min_coverage: float = ...) -> EvidenceGateResult`
- Or split into:
  - `HybridTextRetriever.retrieve(question) -> RetrievalResult`
  - `EvidenceGate.evaluate(question, hits) -> EvidenceGateResult`

DTOs should be immutable dataclasses and safe to `repr()`:

- `RetrievalHit`
  - `doc_id: str`
  - `page_num: int` (persisted 0-indexed, for internal consistency)
  - `display_page_num: int` (1-indexed, for citations)
  - `filename: str`
  - `score: float`
  - `snippet: str` (short, query-focused, verbatim-order, whitespace-normalized)
  - optional `score_components: dict[str, float]` if helpful for tests/diagnostics; keep compact and non-secret.
- `EvidenceGateResult`
  - `is_strong: bool`
  - `reason_code: str` such as `strong_evidence`, `index_missing`, `index_empty`, `index_stale`, `empty_question`, `no_match`, `below_threshold`.
  - `hits: tuple[RetrievalHit, ...]`
  - `top_score`, `query_terms`, maybe `run_id`/`content_hash_prefix` for diagnostics.

### Retrieval algorithm

Recommended first pass:

1. Normalize question text with the same general whitespace/case discipline as `normalize_index_text()`.
2. Extract search tokens with a small stopword set and minimum token length. Keep pharma-like alphanumeric/date terms.
3. Check `get_retrieval_index_status(db_path)`:
   - `BUILT` only proceeds.
   - `MISSING`, `EMPTY`, `STALE`, `ERROR` return weak gate result with reason code.
4. Candidate generation:
   - If `retrieval_fts_available(db_path)`: query `retrieval_index_page_fts` with sanitized token OR query and SQLite `bm25()`; join to `retrieval_index_pages` for filename/display page/run metadata.
   - If FTS unavailable or no FTS matches: fallback to current indexed pages joined to `pages.page_text` and score all rows with token overlap.
5. Hybrid scoring:
   - Convert FTS BM25 to a positive score/rank component. SQLite BM25 returns lower/more-negative as better, so normalize rank rather than exposing raw BM25 directly.
   - Add lexical token coverage (`matched_query_terms / query_terms`) and optional phrase/proximity bonus when normalized question terms appear together.
   - Sort by combined score desc, then deterministic tie-breakers `(filename/doc_id, page_num)`.
6. Snippet assembly:
   - Produce a query-focused snippet from the source page text around the first/best matched token, capped around 180-240 chars.
   - Normalize whitespace but preserve verbatim order and exact words from the page. Do not include full page text.
   - If no token anchor, fall back to existing `retrieval_index_pages.snippet`.
7. De-duplicate by `(doc_id, page_num)` and return top-k hits.

### Evidence gate

Make the gate deterministic and conservative. Suggested starting rules for fixture tests:

- Weak if no non-stopword query terms.
- Weak if no hits.
- Strong if top hit has sufficient combined score and token coverage, e.g. top coverage >= 0.35-0.45 for natural questions and at least one high-value term/date/vendor token matched.
- Weak if top score is below threshold even if FTS returns a token match.
- Optional: require either top score margin over the next hit or allow multiple corroborating hits. For S02 fixture proof, do not overfit to margin; off-topic abstention is more important.
- Return citations/hits only from the retriever. Later S03 generation must not fabricate citations beyond these hits.

## Natural Seams / Task Candidates

1. **DTO and reason-code layer**
   - Files: `src/retrieval/models.py`, `src/retrieval/__init__.py`.
   - Add retrieval hit/result/evidence DTOs. No DB access. Easy independent tests for repr safety and display page fields.

2. **Repository search helpers**
   - Files: `src/retrieval/repository.py`, new `tests/test_retrieval_search_repository.py`.
   - Add FTS search and fallback raw-text candidate loading. Keep internal raw text private. Test FTS search returns metadata/snippet only and SQL-like query terms are safely parameterized.

3. **Hybrid retriever scoring/snippets**
   - Files: new `src/retrieval/retriever.py`, new `tests/test_hybrid_retriever.py`.
   - Implement normalization, tokenization, combined scoring, snippet extraction, deterministic ordering.
   - This is the highest-risk functional seam.

4. **Evidence gate**
   - Files: new `src/retrieval/evidence.py` or same `retriever.py`, tests in `tests/test_evidence_gate.py`.
   - Implement status preflight and weak/strong reason codes. Tests should prove missing, empty, stale, off-topic, and positive supplier-document questions.

5. **Optional operator query CLI smoke**
   - Files: `src/retrieval/cli.py`, `tests/test_retrieval_cli.py`.
   - Only if planner wants a manual probe before S03/S04. Keep output compact; do not print full page text. A `query` command can print `status=strong/weak`, `reason=...`, `hit_count=N`, `top_doc=...`, `top_page=...`, `top_score=...`, and a short snippet. This may leak user-facing page snippets by design, so do not mix it with health/status output.

## First Proof / Highest Risk

First proof should be a fixture DB with at least two ingested documents and multiple pages, then build the S01 index and ask targeted/off-topic questions through the new retriever API.

Suggested fixture content:

- `acme-sdf.pdf` page 0:
  - `Supplier Declaration Form`
  - `Vendor Name: Acme Pharma Ltd.`
  - `Expiry Date: 2027-01-31`
  - `Quality Unit Approval: Pfizer supplier documentation controls apply.`
- `beta-certificate.pdf` page 1:
  - `Certificate of Analysis`
  - `Vendor Name: Beta Labs`
  - `Lot Number: BL-42`
  - `Expiry Date: 2025-06-30`

Expected proof:

- Question: `What is the expiry date for Acme Pharma?`
  - Strong evidence.
  - Top hit is `acme-sdf.pdf`, page display `1`.
  - Snippet contains verbatim `Expiry Date: 2027-01-31` or adjacent Acme/expiry text.
- Question: `Which document mentions lot BL-42?`
  - Strong evidence.
  - Top hit is `beta-certificate.pdf`, display page `2` if persisted `page_num=1`.
  - Snippet contains `Lot Number: BL-42`.
- Question: `What is the weather in Paris?`
  - Weak evidence, no fabricated citation requirement.
  - `is_strong=False`, reason `no_match` or `below_threshold`, hits empty or ignored by gate.
- Mutate page text after build.
  - Gate refuses with `index_stale` until rebuild.

## Verification Plan

Baseline already verified during scout:

`venv/Scripts/python.exe -m pytest tests/test_retrieval_index_repository.py tests/test_retrieval_indexer.py tests/test_retrieval_cli.py`

Result: 22 passed in 3.14s.

Recommended S02 verification commands after implementation:

1. Focused S02 tests:
   - `venv/Scripts/python.exe -m pytest tests/test_hybrid_retriever.py tests/test_evidence_gate.py`
2. Retrieval regression suite:
   - `venv/Scripts/python.exe -m pytest tests/test_retrieval_index_repository.py tests/test_retrieval_indexer.py tests/test_retrieval_cli.py tests/test_hybrid_retriever.py tests/test_evidence_gate.py`
3. Broader smoke before slice closeout:
   - `venv/Scripts/python.exe -m pytest tests/test_db.py tests/test_extraction_cli.py tests/test_compliance_dashboard.py tests/test_app.py tests/test_retrieval_index_repository.py tests/test_retrieval_indexer.py tests/test_retrieval_cli.py tests/test_hybrid_retriever.py tests/test_evidence_gate.py`

Avoid global `python`/Python 3.14. Use `venv/Scripts/python.exe` or `venv.bat`.

## Security / Observability Watch-outs

- SQL: all query/search SQL must remain parameterized. FTS `MATCH` strings need sanitization/escaping and should be built from tokenized terms, not raw user question.
- Leakage: status/build CLI must remain raw-text-free. Retriever results may include short user-facing citation snippets, but never full page text, image blobs, API keys, raw provider outputs, or hidden FTS rows.
- DTO repr safety: do not expose internal candidate raw page text in dataclass reprs. If an internal candidate needs raw text, keep it local/private or set a custom repr/exclude pattern.
- Staleness: retriever should refuse stale indexes. Do not silently search an old index after source pages changed.
- Page numbering: persisted `pages.page_num` remains 0-indexed; citations use `display_page_num` from S01.
- FTS availability: S01 treats FTS5 as optional. S02 must have a fallback path for SQLite builds without FTS5.
- Determinism: tests should not rely on model downloads, network, provider credentials, clock-dependent scores, or non-deterministic ordering.

## Skill Discovery

Installed skills relevant to this slice: none specifically for Python retrieval/BM25/SQLite FTS. General installed skills that may be useful later are `observability` and `api-design`, but S02 is internal service code rather than an HTTP API.

External skill search results (not installed):

- `bm25s`: no skills found.
- `sentence-transformers`: promising but only relevant if adding dense embeddings now:
  - `npx skills add davila7/claude-code-templates@sentence-transformers` (363 installs)
  - `npx skills add orchestra-research/ai-research-skills@sentence-transformers` (214 installs)
- `sqlite fts5`:
  - `npx skills add martinholovsky/claude-skills-generator@sqlite-database-expert` (1.6K installs)
  - `npx skills add rodydavis/skills@how-to-do-full-text-search-with-sqlite` (57 installs)

Recommendation: do not install a skill for S02 unless executor decides to add true dense `sentence-transformers`. SQLite FTS usage is small enough to implement with local tests.

## Open Questions for Planner

- Does “hybrid” require a true dense embedding dependency in S02, or is deterministic FTS BM25 + lexical coverage acceptable for this baseline? Given current deps and offline test constraints, I recommend deterministic hybrid lexical now and a future optional dense adapter.
- Should S02 expose a `python -m src.retrieval query` smoke command, or keep query APIs internal until S03/S04? I recommend internal API only unless manual demo probing is needed.
- Should weak evidence return zero hits, or return low-scoring hits with `is_strong=False` for debugging? I recommend returning hits in the typed result for diagnostics but requiring consumers to ignore citations unless `is_strong=True`.

## Sources / Evidence Artifacts

- Code inspected: `src/retrieval/models.py`, `src/retrieval/repository.py`, `src/retrieval/indexer.py`, `src/retrieval/cli.py`, `src/db/schema.py`, `src/db/queries.py`, `src/app.py`, extraction provider/pipeline patterns, and relevant tests.
- Environment/dependency check: `.gsd/exec/64d0d9db-4feb-458f-8050-656fe684fd1c.stdout`.
- SQLite FTS behavior probe: `.gsd/exec/ea34eea3-bd0b-4932-a867-8612b311ef72.stdout`.
- Baseline verification: `.gsd/exec/2f5793fc-fa94-41f7-8738-53dfa0b33024.stdout`.
