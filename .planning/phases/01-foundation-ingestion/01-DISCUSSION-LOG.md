# Phase 1: Foundation & Ingestion - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-21
**Phase:** 1-Foundation & Ingestion
**Areas discussed:** Database schema design, Page image storage, Streamlit skeleton layout, Langfuse tracing

---

## Database schema design

| Option | Description | Selected |
|--------|-------------|----------|
| Three separate tables | documents, extractions, evaluations tables with foreign key relationships | ✓ |
| Single JSON blob table | One table with document metadata and JSON fields for flexible schema | |
| Hybrid approach | Core tables for documents/extractions, JSON for evaluation results | |

**User's choice:** Three separate tables
**Notes:** User preferred clear relational structure for better queryability and data integrity

---

## Page image storage

| Option | Description | Selected |
|--------|-------------|----------|
| Files on disk | Store page images as PNG/JPEG files in a directory, with paths in DB | |
| BLOBs in SQLite | Store image bytes directly in SQLite database as BLOBs | ✓ |
| Hybrid with thumbnails | Store thumbnails as BLOBs, full images as files | |

**User's choice:** BLOBs in SQLite
**Notes:** User chose this for data consistency and simplified deployment

---

## Streamlit skeleton layout

| Option | Description | Selected |
|--------|-------------|----------|
| Horizontal tabs | Standard Streamlit tabs at the top (Compliance, Chat, Eval) | ✓ |
| Vertical sidebar | Navigation sidebar on left with page content on right | |
| Expandable sections | Each section expandable/collapsible in a single view | |

**User's choice:** Horizontal tabs
**Notes:** User preferred familiar navigation pattern

---

## Langfuse tracing

| Option | Description | Selected |
|--------|-------------|----------|
| Function-level tracing | Trace each major function: PDF ingestion, text extraction, storage, retrieval | ✓ |
| Step-level tracing | Trace each step in the pipeline: ingest -> extract -> store -> index | |
| Selective tracing | Trace only key operations: LLM calls, retrieval operations, evaluation runs | |

**User's choice:** Function-level tracing
**Notes:** User wanted good observability without excessive overhead

---

## Claude's Discretion

None — user provided clear preferences for all discussed areas

---

## Deferred Ideas

None — discussion stayed within phase scope