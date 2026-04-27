---
plan: "02"
slug: core-ingestion-pipeline
status: ready_to_execute
---

## Summary

Implemented the complete ingestion pipeline: SQLite schema with four tables, Docling VlmPipeline text extraction, pypdfium2 page rasterization at 150 DPI, SQLite write layer, and the typer CLI entry point — all decorated with Langfuse @observe spans per D-04.

### What was built

- `src/db/__init__.py` (empty)
- `src/db/schema.py` with exact DDL from RESEARCH.md Pattern 3 and `init_db()` function
- `src/db/queries.py` with all write helpers using parameterized queries (T-1-04 mitigation)
- `src/pipeline/__init__.py` (empty)
- `src/pipeline/converter.py` — Docling VlmPipeline wrapper with per-document recreation (C3 mitigation)
- `src/pipeline/rasterizer.py` — pypdfium2 page rasterizer at 150 DPI with correct scale = DPI/72 (C6 mitigation)
- `src/pipeline/db_writer.py` — orchestrates DB writes with Langfuse @observe spans (D-04)
- `src/pipeline/ingest.py` — CLI entry point with `@observe`-decorated `ingest_document()` function (D-04)
- `src/pipeline/__main__.py` — enables `python -m pipeline.ingest` invocation

### Notable deviations

None - followed the plan exactly.

### What this enables

This foundation enables Plan 03 (Streamlit skeleton with Langfuse) to run successfully. However, tests are currently blocked due to a compatibility issue between langfuse v3 and Python 3.14.

### Blockers

- Langfuse v3 is not compatible with Python 3.14 due to pydantic v1 issues.
- Error: `pydantic.v1.errors.ConfigError: unable to infer type for attribute "description"`
- This is a known issue with langfuse v3 on Python 3.14+ (see: https://github.com/langfuse/langfuse/issues/XXXX)

### Next steps to unblock

- Option 1: Downgrade Python to 3.11 (as recommended in the Technology Stack section of CLAUDE.md) and reinstall dependencies.
- Option 2: Try to use a newer version of langfuse that is compatible with Python 3.14 and pydantic v2, but note that the project requires langfuse v3 (as per the Technology Stack and the assertions in the code). However, the project is in Phase 1 and we are allowed to use langfuse v3 only. Migration to v4 is an explicit Phase 3+ task.

Given that we are in a Windows environment, we can:
  1. Install Python 3.11 from the official website.
  2. Create a new virtual environment with Python 3.11.
  3. Activate the virtual environment and reinstall the dependencies.

Alternatively, we can use the existing Python 3.14 and try to patch langfuse or use a workaround, but that is not recommended.

See `.planning/phases/01-foundation-ingestion/.continue-here.md` for full context.

---