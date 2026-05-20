# M002: Retrieval and RAG Chatbot

**Gathered:** 2026-05-20
**Status:** Ready for planning

## Project Description

The Pfizer SDF Intelligence System is an end-to-end pharmaceutical document intelligence and compliance demo for supplier documentation PDFs. The system already has a Phase 1/M001 foundation for ingesting PDFs into SQLite, extracting structured SDF metadata, calculating compliance risk, and displaying persisted compliance records in Streamlit. M002 adds the second primary user loop: grounded natural-language Q&A over the ingested supplier document corpus.

M002 should deliver the first working Streamlit Chat experience where a compliance officer can ask questions across the already-ingested SQLite corpus and receive concise, evidence-gated answers with citations. This milestone intentionally starts with CPU-friendly hybrid text retrieval rather than visual ColQwen/Qdrant retrieval, while preserving interfaces that can later be wrapped by LangGraph and upgraded with visual retrieval.

## Why This Milestone

M001 makes the corpus useful as structured compliance records, but it does not yet let a reviewer ask open-ended questions across supplier documentation. M002 exists so the demo can show a compliance officer moving from “which documents are risky?” to “why, where, and according to which document page?” without manually opening PDFs.

This needs to happen now because grounded Q&A is a core value promise of the project: answers must be tied to source pages and short verbatim snippets, and weak or off-topic questions must abstain instead of hallucinating. M002 also establishes the retrieval, citation, and generation service boundaries that later evaluation, LangGraph orchestration, visual retrieval, and dashboard polish can build on.

## User-Visible Outcome

### When this milestone is complete, the user can:

- Open the Streamlit app, use the Chat tab, ask a question about the ingested supplier documents, and receive a concise answer grounded in cited source evidence.
- See each answer cite the source filename, 1-indexed page number, and a short verbatim snippet from the retrieved page text.
- Ask a question that is off-topic or has weak corpus evidence and receive a clear refusal/abstention rather than an invented answer.
- Rebuild or refresh the retrieval index through a repeatable CLI/index command instead of relying on ephemeral in-memory startup state.

### Entry point / environment

- Entry point: Streamlit Chat tab in `src/app.py` for the user loop; a CLI/index command for repeatable retrieval setup.
- Environment: local development and demo environment using the project Python 3.11 virtual environment; Streamlit browser UI backed by local SQLite.
- Live dependencies involved: SQLite database is required; Gemini API is used for live answer generation when configured; Langfuse is optional/non-fatal for tracing; no auth, production service, or Qdrant dependency in the M002 baseline.

## Completion Class

- Contract complete means: retrieval, citation assembly, evidence gating, answer generation provider boundaries, and abstention behavior are proven with deterministic offline tests and fixture data.
- Integration complete means: ingested document/page records from SQLite can be indexed, retrieved, converted into cited contexts, passed through the RAG service, and displayed in the Streamlit Chat tab with correct citations.
- Operational complete means: missing indexes, empty corpora, missing Gemini credentials, retrieval setup errors, weak evidence, malformed provider output, and optional Langfuse configuration are handled loudly and explicitly without crashing unrelated app surfaces.

## Final Integrated Acceptance

To call this milestone complete, we must prove:

- A realistic ingested corpus can be indexed, queried from the Streamlit Chat tab, and answered with at least one cited source using filename, 1-indexed page number, and a short verbatim snippet.
- An off-topic or weak-evidence question produces an explicit abstention/refusal and does not fabricate document facts or citations.
- A repeatable CLI/index flow persists retrieval/index metadata and can be exercised in deterministic tests without live Gemini credentials.
- The milestone cannot be considered truly done if it only unit-tests pure retrieval functions; the end-to-end path from SQLite pages to Chat tab answer/citation rendering must be proven. Live Gemini can remain optional/manual, but the production provider seam must exist.

## Architectural Decisions

### Text RAG Baseline Before Visual Retrieval

**Decision:** Implement M002 as a hybrid text retrieval and grounded RAG baseline over SQLite page text; defer ColQwen/Qdrant visual retrieval unless later planning explicitly re-scopes it.

**Rationale:** The existing corpus already stores page text in SQLite, and a CPU-friendly text baseline can prove the core chatbot trust loop faster and more deterministically than GPU-dependent visual retrieval. Visual retrieval remains a project differentiator, but M002 should first establish answer grounding, citation shape, abstention, and testable service contracts.

**Alternatives Considered:**
- Build ColQwen/Qdrant first — better aligned with the long-term visual RAG vision, but adds GPU/model/index complexity before the user-facing trust loop is proven.
- Use only keyword search — simpler, but weaker for natural-language questions and not representative of the intended hybrid retrieval stack.

### Streamlit Chat With Concise Cited Answers

**Decision:** The primary user experience is a Streamlit Chat tab where the user asks a natural-language question and receives a concise answer plus citations.

**Rationale:** Streamlit is already the evaluator-facing dashboard surface, and the Chat tab already exists as a placeholder. A concise answer with explicit citations is the clearest demo of grounded document intelligence for a compliance officer.

**Alternatives Considered:**
- CLI-only Q&A — easier to test, but not the intended evaluator-facing experience.
- Separate web service/API first — cleaner layering for future deployment, but unnecessary for the local single-user demo and outside the milestone’s user-visible goal.

### Citation Shape for M002

**Decision:** A citation in M002 consists of filename, 1-indexed page number, and a short verbatim snippet from the cited page text.

**Rationale:** This is sufficient for the baseline trust story: a reviewer can see which document and page support the answer and can inspect the exact text that grounded it. Page image/PDF preview and bounding-box citation can wait for later dashboard or visual retrieval work.

**Alternatives Considered:**
- Page-only citation — too weak for compliance trust because it does not show the supporting text.
- Full page preview or bounding box citation — stronger evidence, but too much UI and visual extraction scope for the text RAG milestone.

### Strict Evidence Gate and Abstention

**Decision:** The RAG service must refuse to answer when retrieved evidence is weak, missing, or off-topic; it must not generate unsupported answers.

**Rationale:** The project’s core value is no hallucination in a pharmaceutical compliance workflow. A useful refusal is better than a polished but unsupported answer.

**Alternatives Considered:**
- Always answer with caveats — more conversational, but risks normalizing unsupported claims.
- Ask the model to self-police without deterministic retrieval thresholds — simpler to wire, but too brittle for deterministic smoke proof.

### Persisted Retrieval/Index Metadata

**Decision:** M002 should persist retrieval/index metadata rather than relying only on in-memory application startup state.

**Rationale:** Repeatable setup is required for demos, tests, and debugging. Persisted metadata lets developers rebuild, inspect, and validate what corpus state the Chat tab is answering from.

**Alternatives Considered:**
- Build the index in memory on every Streamlit startup — simple, but slow, implicit, and hard to test or diagnose.
- External vector database from the start — useful later, but overkill for a CPU-first SQLite text baseline.

### Service-First RAG Instead of LangGraph in M002

**Decision:** Implement the baseline as service modules with provider/retriever/generator interfaces that are wrap-ready for LangGraph later, rather than introducing LangGraph orchestration in M002.

**Rationale:** The milestone’s risk is proving grounded retrieval/citation/abstention, not agent orchestration. Service-first boundaries keep the code deterministic and easy to test while preserving a future LangGraph integration path.

**Alternatives Considered:**
- Introduce LangGraph immediately — aligned with the target stack, but adds orchestration overhead before the simple RAG contract is stable.
- Put all logic directly in Streamlit callbacks — fastest initially, but creates brittle UI-coupled code that is hard to test and reuse.

### Offline Deterministic Proof With Optional Live Gemini

**Decision:** Automated M002 proof must use deterministic fixtures/fake providers by default; live Gemini generation can be available as a manual or configured path.

**Rationale:** The project must remain testable without secrets, network access, or provider variability. This mirrors the M001 extraction provider pattern and keeps CI/local verification reliable.

**Alternatives Considered:**
- Require live Gemini in integration tests — proves the real provider path but is flaky, secret-dependent, and costly.
- Avoid a live provider seam entirely — easier for tests, but would not deliver the intended demo user loop.

## Error Handling Strategy

M002 should fail safe and fail loud. Developer/setup problems should be explicit rather than hidden behind friendly generic messages, while weak evidence should produce a user-facing abstention.

- Empty corpus: the Chat tab should explain that no ingested pages are available and point the developer/user to run ingestion and indexing.
- Missing or stale index: CLI and Chat should report that the retrieval index must be built/refreshed; tests should cover the stale/missing state.
- Missing Gemini credentials: live generation should fail with a sanitized, actionable setup error, but imports, offline tests, retrieval tests, and Streamlit startup should not require credentials.
- Weak retrieval evidence: the answer service should return a refusal/abstention with no fabricated citations.
- Provider failures/timeouts/malformed responses: the service should propagate a typed error or safe failure result with sanitized diagnostics; no secrets or full page text should be logged.
- SQLite errors: use parameterized access, preserve FK integrity, and surface non-successful setup/indexing states clearly.
- Langfuse failures: remain non-fatal, consistent with existing `src/tracing.py`; when configured, traces should include useful retrieval/generation metadata without leaking document text or secrets.

## Risks and Unknowns

- Retrieval quality over Docling page text — scanned/stamped/table-heavy documents may have imperfect text, which can reduce baseline recall before visual retrieval exists.
- Dense embedding dependency weight and startup cost — CPU-friendly embeddings must not make local demo setup brittle or slow.
- Fusion/reranking threshold calibration — evidence gating needs to be strict enough to prevent hallucination but not so strict that reasonable document questions always abstain.
- Citation snippet extraction — snippets must be short, verbatim, and actually present in page text to maintain trust.
- Streamlit state management — chat history, index availability, and error states need to remain clear without coupling core RAG logic to UI state.
- Live Gemini answer behavior — even with good context, model output may omit or misformat citations unless the service enforces citation assembly outside the model or validates outputs.

## Existing Codebase / Prior Art

- `src/app.py` — Existing Streamlit shell with Compliance, Chat, and Eval tabs; Chat is currently a placeholder and is the M002 user-facing entry point.
- `src/db/schema.py` — SQLite schema for `documents`, `pages`, `extractions`, `compliance_records`, and `evaluations`; M002 may need retrieval/index metadata tables or schema evolution.
- `src/db/queries.py` — Existing page/document query helpers, including ordered page loading and document listing; retrieval should build on these rather than duplicating database access patterns.
- `src/extraction/gemini.py` — Lazy, offline-safe Gemini provider pattern that M002 should mirror for live answer generation.
- `src/extraction/providers.py` — Provider abstraction precedent for deterministic fake providers in tests.
- `src/tracing.py` — Langfuse v3 helper designed to be non-fatal when credentials are absent; retrieval/generation tracing should follow this behavior.
- `tests/test_s05_end_to_end_proof.py` — M001-style final assembly proof pattern using realistic fixture flow and fake provider; M002 should use the same spirit for retrieval/chat proof.
- `.gsd/milestones/M001/M001-CONTEXT.md` and `.gsd/milestones/M001/M001-SUMMARY.md` — Prior milestone boundaries and validated extraction/compliance assumptions that M002 consumes.

## Relevant Requirements

- R005 — M002 directly advances grounded natural-language Q&A with page-level citations and abstention on insufficient evidence.
- R006 — M002 prepares for visual retrieval but does not fully validate ColQwen/Qdrant unless later re-scoped; visual retrieval remains a future enhancement after text RAG baseline.
- R008 — M002 contributes retrieval and generation observability while preserving non-fatal Langfuse behavior and avoiding secret/document text leakage.
- R009 — All development and verification should use the Python 3.11 project virtual environment, not global Python 3.14.
- R010 — Provider credentials and model settings must remain out of Git; tests and default imports must not require secrets.

## Scope

### In Scope

- CPU-friendly hybrid text retrieval over ingested SQLite page text.
- BM25 plus dense embedding retrieval baseline with lightweight fusion/reranking appropriate for local demo use.
- Persisted retrieval/index metadata and a repeatable CLI/index command.
- RAG answer service with strict evidence gating and abstention.
- Citation assembly using filename, 1-indexed page number, and short verbatim snippets.
- Streamlit Chat tab integration for the user-visible Q&A loop.
- Gemini 2.5 Flash answer generation path behind an offline-safe provider seam.
- Deterministic offline tests for retrieval, citation, abstention, indexing, and the integrated Chat/service path.
- Optional/non-fatal Langfuse tracing metadata for retrieval and generation.

### Out of Scope / Non-Goals

- ColQwen/Qdrant visual retrieval implementation for the baseline M002 deliverable unless future planning explicitly re-scopes it.
- Page image preview, PDF iframe preview, or bounding-box citations in the Chat tab.
- Full RAGAS evaluation, gold-set benchmark dashboards, latency/cost reports, and polished evaluation UI; these belong to M003.
- LangGraph orchestration as a required M002 implementation detail.
- Multi-user auth, production deployment, hosted vector database, or cloud infrastructure.
- Fine-tuning models or adding non-PDF ingestion support.

## Technical Constraints

- Use Python 3.11 project virtual environment commands such as `./venv/Scripts/python.exe`; do not rely on global Python 3.14.
- Keep Gemini and Langfuse credentials optional at import/test time and never log secret values.
- SQLite remains the baseline persistence layer for the local demo.
- Retrieval must operate over existing persisted `documents` and `pages` data and respect the existing page numbering convention: database `pages.page_num` is 0-indexed, while UI citations display 1-indexed page numbers.
- Text snippets used as citations must be verbatim substrings or defensibly normalized spans from source page text.
- Streamlit UI code should remain thin; core retrieval/RAG behavior should live in testable service modules.
- BM25/dense dependencies should be CPU-friendly and compatible with local development; GPU-only retrieval is not part of the baseline.
- Langfuse v3 behavior remains optional and non-fatal.

## Integration Points

- Streamlit — provides the Chat tab user loop and displays answers, abstentions, history, setup errors, and citations.
- SQLite — stores ingested documents/pages and any M002 retrieval/index metadata.
- Docling-ingested page text — the source corpus for baseline retrieval.
- Gemini API — live answer generation provider when configured; offline fake provider remains the default for tests.
- Langfuse — optional tracing for retrieval/generation metadata, following existing non-fatal guardrails.
- Existing extraction/compliance outputs — provide document metadata and compliance context that retrieval may cite or use for better answer framing.

## Testing Requirements

Required test coverage:

- Unit tests for text chunk/page indexing, tokenization/normalization, BM25 retrieval, dense retrieval adapter seams, fusion/reranking, and threshold/evidence gating.
- Citation tests proving filename, 1-indexed page number, and short verbatim snippets are assembled correctly from SQLite page records.
- Abstention tests for empty corpus, off-topic questions, low retrieval scores, and missing supporting snippets.
- Provider tests mirroring the M001 pattern: fake provider for default tests, lazy Gemini construction, sanitized failure when credentials are missing, and no secret/page-text leakage in logs.
- Persistence tests for retrieval/index metadata creation, refresh, and stale/missing index behavior.
- CLI tests for repeatable indexing over fixture documents/pages.
- Streamlit or dashboard adapter tests proving Chat tab state can render answers, citations, abstentions, and setup errors without requiring live Gemini.
- Integration proof using a small deterministic SQLite fixture or realistic ingested sample document where a known question retrieves the correct page and produces a cited answer.
- Regression test command should run through the Python 3.11 venv, e.g. `./venv/Scripts/python.exe -m pytest -q`.

Live Gemini smoke testing can be optional/manual and should not be required for routine automated verification.

## Acceptance Criteria

- A repeatable index command can build or refresh retrieval/index metadata from ingested SQLite pages.
- The retrieval service returns relevant candidate pages for known fixture questions and preserves document/page metadata needed for citations.
- The RAG service returns concise grounded answers only when evidence passes the configured gate.
- Every non-abstained answer includes at least one citation with filename, 1-indexed page number, and a short verbatim source snippet.
- Off-topic or weak-evidence questions return a clear abstention/refusal and no fabricated citations.
- The Streamlit Chat tab exposes the user loop and can display successful answers, citations, abstentions, and setup/index errors.
- Automated tests pass without live Gemini or Langfuse credentials.
- Missing Gemini credentials fail only the live generation path with a sanitized actionable error; they do not break imports, indexing, retrieval tests, or Streamlit startup.
- Langfuse tracing, when configured, enriches retrieval/generation observability without becoming a hard dependency.
- Visual retrieval, full benchmark reporting, and page preview UX remain explicitly deferred unless planning re-scopes the milestone.

## Open Questions

- Exact module names, task slices, and dependency pins — current thinking is to decide during planning while preserving service-first boundaries.
- Specific BM25/dense fusion formula and evidence thresholds — current thinking is to start conservative and calibrate against deterministic fixture questions.
- Whether snippets are selected before or after generation — current thinking is to assemble/validate citations outside the model so the answer cannot cite unsupported text.
- How much compliance metadata should be injected into retrieval contexts — current thinking is to retrieve from page text first and optionally enrich answer context with persisted document metadata.
