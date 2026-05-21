# M003: Dashboard Evaluation and Polish

**Gathered:** 2026-05-21
**Status:** Ready for planning

## Project Description

Pfizer SDF Intelligence System is an end-to-end AI-powered pharmaceutical document intelligence and compliance demo. It ingests a folder of supplier PDFs, extracts structured compliance metadata with citations, supports document-grounded Q&A with page-level citations, and presents results in a Streamlit dashboard with observability.

## Why This Milestone

M003 exists to make the system demo-ready and credible: add a real evaluation harness (not placeholder UI), show benchmark reporting for key capabilities (extraction + retrieval/RAG), and polish the Streamlit dashboard so a compliance-officer-style user can understand status, drill into evidence, and trust the system.

## User-Visible Outcome

### When this milestone is complete, the user can:

- Open the Streamlit app and use a populated **Eval** tab that reports evaluation results for extraction and RAG/retrieval (not placeholder text).
- Run evaluations against a **small hand-labeled gold set** and review results/history (stored in SQLite) directly in the dashboard.

### Entry point / environment

- Entry point: Streamlit app (local)
- Environment: local dev
- Live dependencies involved: SQLite (local DB), optional Langfuse connection for traces/metadata

## Completion Class

- Contract complete means: evaluation harness modules and DB persistence exist with real implementation; Streamlit Eval tab renders real computed metrics from stored runs.
- Integration complete means: end-to-end path works from persisted ingested/extracted/indexed data → eval computation → persisted run rows → dashboard rendering.
- Operational complete means: safe failure/empty states (missing tables, missing gold labels, missing index/provider config) show user-friendly messages instead of tracebacks.

## Final Integrated Acceptance

To call this milestone complete, we must prove:

- A user can run (or trigger) an evaluation over the small gold set and then see a new eval run row plus metrics in the Eval tab.
- A user can compare at least two runs (e.g., two extraction runs or two retrieval configs) in the dashboard.
- The demo journey does not crash when data is missing (no compliance rows, no index, no gold set) — the UI should guide the next action.

## Architectural Decisions

### Evaluation scope (Eval tab)

**Decision:** Implement evaluation outputs for both extraction and RAG/retrieval.

**Rationale:** The milestone is “Dashboard Evaluation and Polish”; credibility for stakeholders depends on reporting across core system capabilities.

**Alternatives Considered:**
- Extraction evals only — would under-represent Chat/RAG credibility.
- RAG evals only — would under-represent compliance extraction credibility.

---

### Run storage location

**Decision:** Persist evaluation run outputs in SQLite tables.

**Rationale:** Matches the existing SQLite-backed dashboard architecture and enables easy history/benchmark table rendering in Streamlit.

**Alternatives Considered:**
- Filesystem JSONL — easier manual inspection but weaker dashboard history integration.
- Langfuse-only — useful for observability but adds dependency and query complexity for benchmark tables.

---

### Gold set storage format

**Decision:** Store the small gold set in SQLite (a `gold_labels` table or equivalent).

**Rationale:** Simplifies evaluation joins/queries and keeps the demo self-contained inside the existing DB-backed architecture.

**Alternatives Considered:**
- YAML/JSON in repo — easy to author but adds file-path/config surface area.
- CSV per doc/page — simple, but less structured for richer eval queries.

---

### Polish priority

**Decision:** Focus polish work primarily on UI aesthetics.

**Rationale:** The dashboard should look presentation-ready (layout/typography/color coding/table presentation) for the demo.

**Alternatives Considered:**
- Narrative demo flow — valuable, but secondary to getting the UI feeling “done”.
- Performance/stability — important, but can be handled opportunistically while polishing.

---

### RAG/retrieval metrics to show

**Decision:** The Eval tab must show the following metrics:

- Retrieval **Recall@5/10**
- **RAGAS faithfulness**
- **Citation accuracy** (binary: do cited pages contain the answer span?)
- **Latency/cost** (p50/p95 latency and token/cost summaries per query/run)

**Rationale:** These are the minimum signals that demonstrate grounded quality and operational tradeoffs.

**Alternatives Considered:**
- Only recall — insufficient for grounding/faithfulness.
- Only RAGAS — insufficient for retrieval quality.

## Error Handling Strategy

At Streamlit/UI boundaries, treat missing DB tables/indexes/gold labels/provider config as expected states: display deterministic `st.info/st.warning/st.error` messages with “what to do next”. Avoid leaking raw exceptions; bound diagnostic metadata similarly to the Chat tab’s current approach.

## Risks and Unknowns

- Gold set schema details are not yet specified (what is labeled: extraction fields, retrieval queries, expected citations, etc.).
- Extraction metric definition needs alignment for credibility (field-level F1, strict vs normalized matching, how missing/unknown is scored).
- Citation accuracy implementation may require defining how to detect “answer span present” in cited pages.

## Existing Codebase / Prior Art

- `src/app.py` — Streamlit entry point; Eval tab is currently placeholder text.
- `src/dashboard/compliance.py` — pattern for SQLite-safe reads + user-friendly empty states + detail view.
- `src/dashboard/chat.py` — pattern for bounded diagnostics and safe provider/retrieval error surfacing.

## Relevant Requirements

- Eval harness: extraction F1, retrieval recall@5, answer faithfulness, citation accuracy, latency, cost — M003 makes these dashboard-visible with run history.

## Scope

### In Scope

- Real Streamlit Eval tab implementation.
- Eval run persistence in SQLite (schema + queries).
- Benchmark reporting for extraction + retrieval/RAG on a small gold set.
- UI polish focused on aesthetics (readability, spacing, labeling, color cues).

### Out of Scope / Non-Goals

- Production deployment.
- Multi-user auth.
- Full-corpus exhaustive benchmarking.

## Technical Constraints

- Python 3.11 runtime; Streamlit dashboard.
- Keep dashboard modules credential-free (render-only adapters should not call providers).
- Langfuse is optional/conditional (connected vs not connected should not break UI).

## Integration Points

- SQLite DB — source of persisted docs/pages/extractions and future eval run tables.
- Langfuse — optional trace IDs and run metadata surfaced for auditability.

## Testing Requirements

- Unit tests for evaluation metric computation and SQLite persistence (schema + query functions).
- At least one integration-ish test that builds a minimal fixture DB with gold labels and confirms the Eval data adapter returns expected metric rows.

## Acceptance Criteria

- Eval tab renders computed metrics (not placeholder) for extraction and RAG/retrieval.
- Eval runs can be stored and listed from SQLite.
- UI shows clear, non-crashing empty states for missing prerequisites.
- Dashboard polish improvements are visible (layout/labels/color cues improved vs baseline).

## Open Questions

- Exact schema for `gold_labels` (and any related tables like gold queries / expected citations).
- Which extraction fields are in-scope for F1 (the current extraction contract focuses on a fixed set of fields).
- How “citation accuracy” will be computed (definition of “answer span present” on cited pages).
