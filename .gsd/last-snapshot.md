# GSD context snapshot (2026-06-07T23:18:46.820Z)

## Active context
Active: M004 / S05 / T02 - Run real visual-fallback candidate extraction and populate eval runs

## Top project memories
- [MEM011] (pattern) Phase 2 extraction persistence uses `src.extraction.repository` as the SQLite boundary: validated `SDFExtractionRecord` models upsert exactly six `extractions` rows and one `compliance_records` row, with DB foreign keys enforcing parent-document existence and all model-derived values passed through SQL placeholders.
- [MEM041] (pattern) The M002 RAG answer boundary is service-owned: retrieval evidence is authoritative, providers receive only bounded snippets, and citations are derived from RetrievalHit data rather than provider output. Provider, retrieval, blank-answer, and weak-evidence failures are represented as typed AnswerResult statuses with sanitized diagnostics.
- [MEM016] (pattern) The SDF extraction pipeline keeps live VLM dependencies behind a small provider protocol; offline orchestration normalizes provider payloads into exactly six fields, abstains on missing/ungrounded facts, computes risk, and persists through the repository boundary without logging raw page text or provider responses.
- [MEM021] (pattern) Compliance dashboard UI code should remain credential-free and provider-free: load persisted SQLite compliance rows once per Streamlit rerun, format display-safe table fields, and lazily call get_page_image only for the selected source-detail row.
- [MEM038] (architecture) The RAG answer boundary in src/rag/service.py makes S02 retrieval evidence authoritative: providers are called only for strong evidence, receive bounded RetrievalHit snippets only, and citations/diagnostics are owned by the service rather than by provider output.
- [MEM009] (architecture) The SDF extraction contract is modeled as exact-six-field Pydantic v2 records under src/extraction: field names are enum-constrained, non-abstained fields require a value plus source verbatim_span, abstained fields requi
…[truncated]
