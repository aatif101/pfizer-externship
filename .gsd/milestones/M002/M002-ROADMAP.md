# M002: Retrieval and RAG Chatbot

**Vision:** Deliver the first grounded natural-language Q and A loop for the Pfizer SDF Intelligence System: a compliance officer can build a repeatable text retrieval index from ingested SQLite pages, ask questions in the Streamlit Chat tab, and receive concise answers with filename, page number, and verbatim snippet citations or a safe abstention when evidence is weak.

## Success Criteria

- SQLite-backed ingested document pages can be indexed through a repeatable command that records index metadata and reports empty, missing, or stale corpus states clearly.
- A CPU-friendly hybrid text retriever can return ranked page contexts with stable document identifiers, filenames, 1-indexed page numbers, scores, and short verbatim snippets.
- The RAG service refuses weak or off-topic questions deterministically and never fabricates citations when evidence is insufficient.
- A configured live Gemini path exists behind an offline-safe provider seam, while automated tests use fake providers and require no secrets.
- The Streamlit Chat tab exercises the real service path from local SQLite through retrieval, evidence gating, generation, citation rendering, and user-facing error states.
- Final verification proves the CLI indexing path, offline service path, Chat rendering path, and operational failure modes with deterministic tests.

## Slices

- [x] **S01: S01** `risk:Highest early risk: the Chat loop cannot be reliable until there is a repeatable way to transform existing SQLite pages into inspectable retrieval state and detect empty, missing, or stale indexes.` `depends:[]`
  > After this: After this, a developer can run a repeatable index command against a fixture or local database and see persisted index metadata plus clear output for built, empty, missing, and stale states.

- [ ] **S02: S02** `risk:Retrieval quality and abstention thresholds are the core no-hallucination risk, especially with noisy page text and a CPU-friendly baseline.` `depends:[]`
  > After this: After this, fixture questions retrieve expected supplier document pages with filename, 1-indexed page number, score, and verbatim snippet, while unrelated questions return a weak-evidence result.

- [ ] **S03: Grounded Answer Service and Provider Seam** `risk:Model generation must remain optional, testable, and citation-safe; provider variability must not compromise the deterministic evidence contract.` `depends:[S02]`
  > After this: After this, tests can ask corpus-backed and off-topic questions through one service API and receive either a concise cited answer from a fake provider or a safe abstention, with a lazy Gemini provider available when configured.

- [ ] **S04: Streamlit Chat User Loop** `risk:The user-visible milestone can fail even if services work if Streamlit reruns, chat state, setup errors, or citation rendering are unclear.` `depends:[S03]`
  > After this: After this, a compliance officer can open the Chat tab, ask a supplier-document question, see a concise answer with citations, ask an unrelated question, and see a clear abstention.

- [ ] **S05: Operational Proof and Evaluation Hooks** `risk:A demo-ready chatbot needs final proof across CLI, service, UI, tracing, and failure modes, not just isolated unit tests.` `depends:[S04]`
  > After this: After this, a single verification run proves indexing, retrieval, answer generation, Chat rendering, abstention, and operational failures with fixture data and no live secrets.

## Boundary Map

## Boundary Map

| Concern | Planning decision |
| --- | --- |
| Requirements | R005 drives the user loop; R006 visual retrieval is deferred; R007 is limited to retrieval and citation proof; R008 to R010 are treated as table stakes. |
| Decisions | Text RAG baseline, strict evidence gate, persisted index metadata, service-first RAG, and offline deterministic proof shape all slices. |
| Shutdown and failure | Missing index, empty corpus, weak evidence, provider failure, and missing credentials must return typed or user-actionable safe failures without crashing unrelated tabs. |
| Revenue and billing | Live Gemini can incur API cost only when explicitly configured; default tests and demos can run with fake providers. |
| Auth and secrets | No auth is introduced; Gemini and Langfuse secrets remain environment-only and sanitized in errors. |
| Shared resources | SQLite is the shared source of truth; index metadata must not corrupt M001 ingestion, extraction, or compliance tables. |
| Reconnection and reruns | Streamlit reruns must preserve chat state while making index availability and refresh actions explicit. |
