---
phase: 1
slug: 01-foundation-ingestion
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-27
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (latest) |
| **Config file** | `pytest.ini` — Wave 0 installs |
| **Quick run command** | `pytest tests/ -x -q --tb=short` |
| **Full suite command** | `pytest tests/ -v` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x -q --tb=short`
- **After every plan wave:** Run `pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 1-db-schema | TBD | 1 | Phase 1 SC-4 | T-1-04 (SQL injection) | Parameterized queries only; FK enforcement ON | unit | `pytest tests/test_db.py::test_schema_exists -x` | ❌ W0 | ⬜ pending |
| 1-ingest-single | TBD | 2 | INGEST-01 | T-1-01 (path traversal) | Resolve & validate input path before ingest | integration | `pytest tests/test_ingest.py::test_ingest_single_pdf -x` | ❌ W0 | ⬜ pending |
| 1-ingest-memory | TBD | 2 | INGEST-01 | T-1-03 (OOM/DoS) | File size check before Docling ingest | integration | `pytest tests/test_ingest.py::test_memory_no_leak -x` | ❌ W0 | ⬜ pending |
| 1-rasterize-stored | TBD | 2 | INGEST-02 | — | N/A | unit | `pytest tests/test_rasterizer.py::test_png_blob_stored -x` | ❌ W0 | ⬜ pending |
| 1-rasterize-dpi | TBD | 2 | INGEST-02 | — | N/A | unit | `pytest tests/test_rasterizer.py::test_150dpi_dimensions -x` | ❌ W0 | ⬜ pending |
| 1-cli-smoke | TBD | 2 | INGEST-01 | T-1-01 (path traversal) | CLI rejects paths outside expected base dir | smoke | `pytest tests/test_cli.py::test_ingest_cli_smoke -x` | ❌ W0 | ⬜ pending |
| 1-streamlit-starts | TBD | 3 | Phase 1 SC-5 | — | N/A | smoke | `pytest tests/test_app.py::test_streamlit_starts -x` | ❌ W0 | ⬜ pending |
| 1-langfuse-auth | TBD | 3 | Phase 1 SC-5 | T-1-04 (data disclosure) | Langfuse API keys not logged; stored only in env | integration | `pytest tests/test_tracing.py::test_langfuse_auth -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/__init__.py` — package init
- [ ] `tests/conftest.py` — shared fixtures: `tmp_db_path`, `sample_pdf_path` (1-page test PDF in tests/fixtures/)
- [ ] `tests/fixtures/sample.pdf` — a minimal 1-page PDF for integration tests
- [ ] `tests/test_db.py` — schema existence and FK enforcement tests
- [ ] `tests/test_ingest.py` — INGEST-01 integration tests (single PDF ingest, memory stability)
- [ ] `tests/test_rasterizer.py` — INGEST-02 unit tests (BLOB stored, DPI correct)
- [ ] `tests/test_cli.py` — CLI smoke test (exit 0 with valid folder)
- [ ] `tests/test_app.py` — Streamlit startup smoke test
- [ ] `tests/test_tracing.py` — Langfuse auth check test
- [ ] `pytest.ini` — `testpaths = tests`, `addopts = -x`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Docling correctly handles scanned/stamped PDFs without errors | INGEST-01 SC-3 | Requires real pharma PDFs; cannot automate without actual test corpus | Run `python -m pipeline.ingest data/pdfs/` against 3 scanned/stamped sample PDFs; verify no exceptions and rows appear in DB |
| Streamlit tabs display correctly in browser | Phase 1 SC-5 | Visual UI verification | Run `streamlit run src/app.py`; confirm 3 tabs visible and Langfuse status shows in sidebar |
| Langfuse traces visible in Langfuse dashboard | D-04 | Requires external service login | After ingest, check Langfuse UI for ingest_document traces with correct metadata |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
