# Phase 3 Research — Retrieval & RAG Chatbot

**Researched:** 2026-07-15  
**Requirements:** RETRIEVE-01, RETRIEVE-02, RETRIEVE-03, RAG-01, RAG-02  
**Primary contract:** [03-AI-SPEC.md](./03-AI-SPEC.md)

## Recommendation

Replace the current page-level SQLite FTS/lexical scorer and free-form answer path behind their existing public facades. Build deterministic ~500-token chunks, persist their provenance and index manifest in SQLite, and store named sparse and 1024-dimensional dense vectors in a versioned local Qdrant collection named `sdf_text_chunks`. Query sparse and dense candidates independently, fuse ranks with reciprocal-rank fusion (RRF), re-rank a bounded union with `cross-encoder/ms-marco-MiniLM-L-6-v2`, and map chunks back to unique citation-ready pages.

Keep `retrieve_evidence(...)` and `answer_question(...)` compatible for the Streamlit application and existing tests. Internally, use a fixed LangGraph state graph with deterministic routing: retrieve, quality gate, one rule-based refinement/retrieval retry, structured generation, literal quote/citation validation, then answer or canonical abstention. It is a graph implementation of the Phase 3 linear pipeline, not the open-ended agent planned by RAG-03.

The main runtime uses LangGraph 1.2.9 and LangChain Core 1.x. RAGAS 0.4.3 and its pre-1.0 LangChain dependencies move to an isolated `tools/ragas-eval` uv project and consume exported JSONL only.

## Existing Code: Reuse and Hazards

### Reusable seams

- `src/retrieval/indexer.py` already owns corpus loading, original/OCR text selection, normalization, stable corpus fingerprints, index status, deterministic run IDs, and redacted trace metadata.
- `src/retrieval/repository.py` and `src/db/schema.py` already persist retrieval runs/pages transactionally and protect raw page text from public DTOs.
- `src/retrieval/models.py` exposes immutable page-aware DTOs used by evaluation, RAG, visual fusion, and the dashboard.
- `src/retrieval/retriever.py::retrieve_evidence` is the compatibility facade and already fails closed for missing, empty, stale, and retrieval-error states.
- `src/retrieval/visual/*` supplies reusable page-key RRF and an optional GPU visual seam. Visual retrieval remains optional in Phase 3; text hybrid must be fully operational locally.
- `src/rag/providers.py` is a lazy, injectable provider boundary. Offline tests can continue to inject fakes.
- `src/rag/service.py::answer_question` owns the public no-hallucination boundary and dashboard DTO conversion.
- `src/dashboard/chat.py` persists bounded session messages and renders citations/diagnostics without owning retrieval logic.
- Existing eval tables and runners provide run/provenance patterns that the new benchmark scorer can reuse.

### Hazards to remove

- Current indexing is one row per page, not ~500-token chunks, and is stored only in SQLite FTS.
- Current “hybrid” retrieval is an FTS/substring heuristic; it has no BGE dense vectors, true sparse named vectors, Qdrant Query API, or cross-encoder.
- Score threshold `0.45` is on an ad-hoc scale and is not calibrated against answerability/decoys.
- OCR-only text can be lost when evidence is reloaded from `pages.page_text`; chunk text must be built from the exact normalized original+OCR source and hash-bound.
- Visual-only pages can currently become “strong” with empty text evidence. They must never authorize text generation without verified textual evidence.
- Gemini currently returns free-form text. The service then attaches every retrieved page as a citation without proving which claim each page supports.
- Document text is interpolated into the prompt without an evidence registry, typed claim schema, or deterministic quote validation.
- Provider retry plus graph retry can exceed the intended bound. Phase 3 allows one generation call and at most two retrieval calls.
- Current `pyproject.toml` installs RAGAS/LangChain 0.3 packages in the application environment; this blocks current LangGraph.

## Dependencies and Versions

Main application:

- `qdrant-client>=1.17,<2`
- `bm25s>=0.2,<1`
- `sentence-transformers>=5,<6`
- `langgraph==1.2.9`
- `langchain-core>=1.4.7,<2` only as LangGraph's low-level dependency; do not add high-level LangChain chains
- existing `google-genai>=2.7,<3`, `pydantic>=2.8,<3`, and `langfuse>=3,<4`

Move `ragas==0.4.3`, `langchain<1`, `langchain-core<1`, and judge adapters to `tools/ragas-eval/pyproject.toml`. The main runtime and isolated judge exchange a versioned JSONL schema.

Model revisions must be pinned in the index/run manifest, not addressed as “latest”:

- Dense: `BAAI/bge-large-en-v1.5`, 1024 dimensions, normalized passage vectors; queries use `Represent this sentence for searching relevant passages: ` as specified by the [official model card](https://huggingface.co/BAAI/bge-large-en-v1.5).
- Reranker: `cross-encoder/ms-marco-MiniLM-L-6-v2` through Sentence Transformers `CrossEncoder`.
- Sparse: BM25 k1/b parameters and tokenizer/stopword configuration are fixed in config and manifest. `bm25s` supplies deterministic tokenization/index semantics; document term-frequency weights are exported as sparse vectors with a stable vocabulary and Qdrant IDF modifier. The [bm25s project](https://github.com/xhluca/bm25s) documents its sparse-matrix index and stable corpus ordering requirement.

Qdrant stores both named representations on each chunk point and fuses their result sets using rank, not raw-score addition, because dense and BM25 scores have different scales. This follows Qdrant's [hybrid query guidance](https://qdrant.tech/documentation/search/hybrid-queries/) and [hybrid text-search model](https://qdrant.tech/documentation/search/text-search/hybrid-search/).

All heavyweight imports and model loads are lazy. Offline unit tests inject deterministic sparse/dense/reranker adapters. The real model cache is configurable and `local_files_only`/offline failure returns a typed configuration error; it never silently substitutes fake embeddings in a demo run.

## Index Architecture

### Chunking

1. Load the exact normalized original/OCR text already selected by `load_indexable_pages`.
2. Tokenize with a deterministic, dependency-light tokenizer for boundaries. Target 500 tokens, maximum 540, 50-token overlap, never cross a page, drop blank chunks, and preserve normalized character offsets.
3. Give each chunk a stable ID derived from `sha256(doc_id, page_num, start, end, text_sha256, chunker_version)` and a deterministic unsigned Qdrant point ID.
4. Persist metadata: chunk ID, document ID, zero-based page number, display page, filename, ordinal, offsets, text hash, bounded snippet, text source, OCR flag, retrieval run, corpus/index/config/model fingerprints.
5. Keep raw chunk text only at the repository/model boundary needed for embedding, reranking, and generation. Public DTOs and default traces expose hashes/IDs/snippets only.

### Collection

`sdf_text_chunks` is recreated atomically under a build-specific temporary name, populated and verified, then promoted through persisted manifest state. Required named vectors:

- `dense`: cosine, size 1024.
- `sparse`: `SparseVectorParams(modifier=Modifier.IDF)` with stable vocabulary indices.

Payload indexes cover `doc_id`, `page_num`, `run_id`, and `text_sha256`. Every query verifies the latest SQLite run, Qdrant collection/index fingerprint, point count, vector dimensions, model revisions, and corpus content hash. A mismatch is `INDEX_STALE`, never a best-effort query.

For local demo use `QdrantClient(path=<configured directory>)`; tests use `:memory:`. Only one client owns an embedded path at a time. Cloud/server URL support is configuration-only and not required for the demo.

### Sparse encoding

Build a vocabulary deterministically from the sorted chunk corpus. Token indices, stopwords, tokenizer version, BM25 k1/b, average document length, and vocabulary hash are persisted. Document values contain BM25 term-frequency length normalization; query values contain bounded query term frequency and rely on the collection IDF modifier. Unit tests compare the exported sparse ordering with a bm25s reference index on a fixed corpus. Unknown query terms are dropped and cannot mutate the vocabulary.

### Dense encoding and reranking

Passages are embedded without the query instruction; queries include the BGE instruction. Normalize both. Batch size and device are configured and recorded. Fetch at least 50 sparse and 50 dense candidates, fuse the unique union with RRF (`k=60`) using deterministic chunk-ID tie breaks, retain a bounded top 40, then score question/passage pairs with the MS-MARCO cross-encoder and return the top 10 chunks/top 5 unique pages.

Do not gate on a raw BGE cosine value alone; the BGE model card explicitly says absolute thresholds require dataset calibration. Calibrate the final reranker score, margin, entity/query coverage, hit count, and contradiction signals only on the public development split. Persist threshold version and calibration artifact.

## Retrieval Schemas and Invariants

Add immutable chunk/index/query DTOs without breaking existing page DTO fields:

- `TextChunk`: IDs, page provenance, offsets, hashes, text (internal only), snippet.
- `HybridIndexManifest`: collection/run/corpus/chunker/tokenizer/vocabulary/dense/reranker/config fingerprints and counts.
- `HybridCandidate`: chunk provenance plus sparse rank/score, dense rank/score, RRF score, rerank score.
- `RetrievalHit`: retain existing fields and add optional chunk/evidence ID, content hash, rerank score, and rank details with defaults.
- `EvidenceGateResult`: retain existing fields; add retry/calibration/index fingerprint diagnostics with safe defaults.

Invariants:

- Every accepted evidence item resolves to one current source page and exact normalized chunk text/hash.
- Candidate ordering is total and deterministic.
- Page citations are deduplicated after chunk reranking without losing the best supporting chunk.
- Weak/stale/contradictory evidence exposes no generation envelope.
- Visual hits without verified text may support a “review this page” result, never a factual answer.
- No model/provider can create display metadata; the server resolves evidence IDs to filename/page.

## Grounded RAG Architecture

### Structured contract

Use strict Pydantic v2 models with `extra="forbid"`:

- `EvidenceItem`: opaque request-local ID, source hash, normalized text, doc/page metadata held server-side.
- `GroundedClaim`: concise claim text, one or more supplied evidence IDs, and a verbatim supporting quote per evidence ID.
- `GroundedAnswer`: `status` (`answered` or `abstained`), bounded claims, concise display answer, and abstention reason. Answered requires at least one claim; abstained requires no claims/citations and the canonical public text.

Gemini receives only the question, fixed instructions, and a bounded immutable evidence envelope. Evidence is explicitly untrusted data; instructions inside it are ignored. The provider uses JSON structured output, temperature zero, one candidate, a fixed model/prompt/schema version, hard timeout, and one call.

### Deterministic graph

`START -> retrieve -> quality_gate`

- sufficient: `generate -> validate -> END`
- insufficient on round 0 and refinement is applicable: `refine -> retrieve`
- insufficient on round 1, contradiction, injection, or any operational failure: `abstain -> END`
- schema/quote/citation validation failure: `abstain -> END`

The quality gate is provider-free. Refinement only adds recognized entity/lot/date synonyms from the question; it cannot use provider output. LangGraph nodes return state deltas and are dependency-injected. In-memory checkpointing is test-only; the local demo uses SQLite checkpointing with a unique request ID and stores no raw PDFs, keys, or provider objects.

### Grounding validation

For every claim:

1. evidence IDs must be unique members of the supplied registry;
2. quotes must match normalized source text literally after conservative whitespace/Unicode normalization;
3. server-owned hashes/doc/page metadata must still match the current index;
4. a deterministic token/number/date/unit/polarity coverage check must support the claim;
5. contradictions, unknown scope, or any invalid claim reject the entire draft.

Only validated claim citations are rendered. The compatibility `AnswerResult.answer_text` is assembled from validated structured content; `AnswerCitation` remains dashboard-compatible and gains optional evidence/quote fields. The canonical abstention public text remains stable, with bounded internal reason codes.

## Observability, Cost, and Privacy

Record request/run ID, graph node/status/reason, corpus/index/model/prompt/schema/calibration versions, ranks/scores/counts, provider request ID, input/output/cached tokens, timings, price-table version, and cost. Disable automatic Langfuse input/output capture and omit question, answer, evidence text, PDF/image bytes, provider payloads, full hashes, and secrets by default. Provider error, timeout, budget breach, checkpoint failure, or missing usage/cost metadata fails closed.

## Dashboard Compatibility

Keep `answer_question(db_path, question, *, provider, ...) -> AnswerResult` as the synchronous facade and add `answer_question_async` for the graph. The facade may run the async graph only when no event loop is active; tests cover both paths. `src/dashboard/chat.py` continues to consume bounded answer text, citations, and diagnostics. Add a server-owned page locator/preview action to citations in the later dashboard/release phase; Phase 3 ensures the DTO has immutable `doc_id`, zero/display page, evidence ID, quote, snippet, and score.

## Implementation Order

1. Isolate RAGAS and add main-runtime dependencies; implement chunk/schema/migration/manifest primitives with provider-free tests.
2. Build transactional Qdrant sparse+dense indexing, lazy real model adapters, deterministic fake adapters, and stale/partial-build cleanup.
3. Implement hybrid query, RRF, cross-encoder reranking, page mapping, development-only sufficiency calibration, and compatibility facade.
4. Add strict structured provider models, Gemini adapter, literal claim validation, bounded LangGraph graph/checkpointing, sync facade, and dashboard-compatible citations.
5. Add deterministic adversarial tests and Phase 3 evaluation artifacts/commands. Do not publish holdout or live-provider metrics until the frozen public benchmark is implemented and sealed.

## Resolved Questions

- **Linear pipeline vs LangGraph:** use a fixed graph with no open-ended agent behavior. RAG-03's decomposition/self-critique loop remains Phase 6.
- **SQLite FTS:** retain only as a degraded diagnostic/legacy compatibility path; it cannot satisfy release/demonstration mode. Missing Qdrant/models yields typed abstention/configuration status.
- **Visual retrieval:** preserve the existing GPU seam but do not allow it to authorize answers without textual grounding.
- **Qdrant local vs server:** embedded local persistence is the demo default; configuration permits a server later.
- **Thresholds:** derive only on dev, version and hash them, and never tune against holdout.
- **Provider failure presentation:** return the canonical safe answer status/reason rather than a partially grounded or free-form result.

## Validation Architecture

### Test layers

| Layer | Purpose | Fixtures | Required behavior |
|---|---|---|---|
| Fast unit | Chunk boundaries/IDs, sparse math, schemas, routing, quote validation, RRF, page dedupe | Tiny strings, fake encoders/reranker/provider, in-memory Qdrant/checkpointer | Offline, deterministic, no model import/download/network/key |
| Medium integration | SQLite -> chunks -> Qdrant -> hybrid retrieval -> graph -> dashboard DTO | Synthetic multi-page PDFs/DB, deterministic embeddings, replay provider | Exact fingerprints/counts/ranks, stale failure, decoys/contradictions/injection/abstention |
| Full regression | Existing product surface plus Phase 3 gates | Existing test suite and frozen benchmark replay | Windows/Linux parity, coverage, privacy/provenance checks |
| Live release | Real BGE/reranker/Gemini, latency/cost/RAGAS | Frozen untouched holdout, immutable local Qdrant, explicit credentials/cache | Three sealed runs, no fallback to replay/fakes, all AI-SPEC thresholds |

### Requirement mapping

| Requirement | Verification |
|---|---|
| RETRIEVE-01 | Collection schema contains named sparse vector; 500-token chunk/overlap invariants; bm25s-reference rank test; manifest/vocabulary/hash/count checks; stale/atomic build tests. |
| RETRIEVE-02 | Named 1024-d dense vector; BGE query/passages instruction and normalization tests; pinned model revision; deterministic fake and optional real-model smoke. |
| RETRIEVE-03 | Sparse+dense prefetch, RRF `k=60`, bounded union, cross-encoder call/order/tie tests; dev calibration provenance; recall/nDCG scorer. |
| RAG-01 | Structured answer schema, request-local evidence registry, literal quote/source validation, server-owned filename/page citations, dashboard DTO rendering. |
| RAG-02 | No provider call on weak/stale/contradictory evidence; one retry maximum; malformed/unsupported/injection/provider/timeout/budget paths return canonical abstention. |

### Windows commands

Fast feedback after each task:

```powershell
venv\Scripts\python.exe -m pytest tests\retrieval\test_chunks.py tests\retrieval\test_hybrid.py tests\rag -q
```

Medium Phase 3 gate:

```powershell
venv\Scripts\python.exe -m pytest tests\retrieval tests\rag tests\test_answer_service.py tests\test_chat_dashboard.py -q
```

Full offline regression and coverage:

```powershell
venv\Scripts\python.exe -m pytest -q
venv\Scripts\python.exe -m pytest --cov=src --cov-report=term-missing --cov-fail-under=85 -q
venv\Scripts\python.exe -m pip check
```

Frozen replay/release gates once the benchmark artifact exists:

```powershell
venv\Scripts\python.exe -m src.eval.demo_gate verify-dataset --dataset benchmarks\sdf-synthetic-v1 --expected-manifest benchmarks\sdf-synthetic-v1\MANIFEST.sha256
venv\Scripts\python.exe -m src.eval.demo_gate run --mode offline-replay --dataset benchmarks\sdf-synthetic-v1 --split holdout --provider-replay benchmarks\sdf-synthetic-v1\replay\gemini-2.5-flash.jsonl --seeds 1729,2718,3141 --output .artifacts\eval\ci
venv\Scripts\python.exe -m src.eval.demo_gate run --mode live-release --dataset benchmarks\sdf-synthetic-v1 --split holdout --seeds 1729,2718,3141 --require-credentials --output .artifacts\eval\release
uv run --project tools\ragas-eval python -m ragas_eval score --input .artifacts\eval\release\ragas-input.jsonl --output .artifacts\eval\release\ragas-results.jsonl
```

### Nyquist rule

Each implementation task includes its test in the same commit. No two consecutive tasks may defer automated verification. Retrieval/generation tests must assert negative behavior and provider call counts, not merely output text. A Phase 3 plan cannot complete with unexecuted notebook cells, optional skips standing in for required behavior, synthetic scores labeled as live, or a benchmark result missing denominator/fingerprint/run-mode provenance.
