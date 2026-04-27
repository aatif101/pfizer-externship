# Phase 1: Foundation & Ingestion - Research

**Researched:** 2026-04-27
**Domain:** PDF ingestion pipeline, SQLite schema, Streamlit skeleton, Langfuse v3 observability
**Confidence:** HIGH (core stack verified against PyPI, official docs, and GitHub issues)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Three separate tables for documents, extractions, and evaluations with foreign key relationships
- **D-02:** Store image bytes directly in SQLite database as BLOBs
- **D-03:** Standard Streamlit tabs at the top (Compliance, Chat, Eval)
- **D-04:** Trace each major function: PDF ingestion, text extraction, storage, retrieval

### Claude's Discretion
None listed — all decisions were locked in discussion.

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INGEST-01 | User can point CLI at a folder of pharmaceutical PDFs and ingest them using Docling (v2.72+, Granite-Docling-258M), handling scanned/stamped/complex-table PDFs | VlmPipeline initialization pattern, memory-leak fix, C3 pitfall mitigation |
| INGEST-02 | System renders each page as 150 DPI PNG thumbnail and stores alongside extracted text | pypdfium2 rasterization pattern, SQLite BLOB storage, decoupled rasterization from VlmPipeline |
</phase_requirements>

---

## Summary

Phase 1 establishes the project skeleton: a CLI ingestion pipeline, SQLite compliance database, Streamlit UI with three empty tabs, and Langfuse v3 observability wiring. The heavy technical work is (1) running Docling's VlmPipeline with Granite-Docling-258M correctly, and (2) separately rasterizing each PDF page to 150 DPI PNG thumbnails and storing them as BLOBs in SQLite.

A critical insight from research: **page image export does not work reliably through VlmPipeline's `generate_page_images` option** (Docling GitHub issue #2416 is open and unresolved; `generate_picture_images` does not function with the VLM backend). The correct approach is to rasterize pages independently with pypdfium2 after Docling has extracted text — this keeps the two concerns cleanly separated and avoids the VlmPipeline image-extraction bug entirely.

The Langfuse version constraint is strict and consequential: `langfuse>=3.0,<4.0` maps to package versions like 3.14.6 (latest 3.x). The v3 SDK uses `from langfuse.decorators import langfuse_context, observe` and `from langfuse.callback import CallbackHandler` — these import paths changed in v4. Pinning at `<4.0` is mandatory.

**Primary recommendation:** Use VlmPipeline for text/structure extraction, pypdfium2 separately for page images, SQLite with `PRAGMA foreign_keys = ON` for the compliance database, and Langfuse v3 decorator-style tracing from day one.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| PDF text + structure extraction | CLI / Batch | — | Docling is a heavy offline process; must not run inside Streamlit callbacks |
| Page image rasterization (150 DPI PNG) | CLI / Batch | — | Runs alongside Docling extraction in the same batch loop |
| SQLite schema creation + migration | CLI / Batch (init) | — | One-time init script; database is then read by all tiers |
| Compliance database writes | CLI / Batch | — | Only the ingest pipeline writes; Streamlit is read-only over DB |
| Langfuse trace emission | CLI / Batch + Streamlit | — | Ingestion traces from CLI; Streamlit wraps future query calls |
| Streamlit UI skeleton | Streamlit | — | Three tabs rendered on startup; no LLM calls in Phase 1 |
| Langfuse connection verification | Streamlit startup | — | `auth_check()` on app load shows green/red status in sidebar |

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| docling | `>=2.72.0,<3.0` | PDF parsing with VlmPipeline + Granite-Docling-258M | CLAUDE.md locked; 2.91.0 is latest 2.x as of 2026-04-27 |
| pypdfium2 | `>=5.7.1` | Page rasterization to 150 DPI PNG | CLAUDE.md locked; cross-platform, no poppler dependency, current latest |
| langfuse | `>=3.0,<4.0` | Observability — `@observe` decorator, CallbackHandler | CLAUDE.md hard pin; v4 is breaking, 3.14.6 is latest v3 |
| streamlit | `>=1.56,<2.0` | UI skeleton — three tabs | CLAUDE.md locked; 1.56.0 is latest |
| pydantic | `>=2.8` | Data models for DocStore records | CLAUDE.md locked; 2.13.3 is latest |
| typer | `>=0.12` | CLI entry point for ingest command | CLAUDE.md implicit; 0.25.0 is latest |
| tqdm | `>=4.66` | Progress bars during batch ingest | CLAUDE.md explicit |
| loguru | `>=0.7` | Structured logging | CLAUDE.md explicit; 0.7.3 is latest |
| tenacity | `>=8.2` | Retry wrapper for transient failures | CLAUDE.md explicit; 9.1.4 is latest |

[VERIFIED: pip index versions 2026-04-27 for all packages listed above]

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-dateutil | latest | Pharma date format parsing | Needed in Phase 2; import in Phase 1 data models as dependency |
| pydantic-settings | latest | Env/config loading (API keys, DB paths) | Phase 1 needs `HF_HOME`, `LANGFUSE_*` vars loaded cleanly |
| gc + psutil | stdlib / latest | Memory monitoring after each Docling conversion | Critical for C3 pitfall mitigation |

### Version Verification

| Package | PyPI Latest | Pinned Range |
|---------|------------|--------------|
| docling | 2.91.0 | `>=2.72.0,<3.0` |
| pypdfium2 | 5.7.1 | `>=5.0` |
| langfuse | 4.5.1 (latest overall) | `>=3.0,<4.0` → pins to 3.14.6 |
| streamlit | 1.56.0 | `>=1.56,<2.0` |
| pydantic | 2.13.3 | `>=2.8` |
| typer | 0.25.0 | `>=0.12` |
| tqdm | 4.67.3 | `>=4.66` |
| loguru | 0.7.3 | `>=0.7` |
| tenacity | 9.1.4 | `>=8.2` |

[VERIFIED: PyPI registry 2026-04-27]

**Installation:**
```bash
pip install \
  "docling>=2.72.0,<3.0" \
  "pypdfium2>=5.0" \
  "langfuse>=3.0,<4.0" \
  "streamlit>=1.56,<2.0" \
  "pydantic>=2.8" \
  "pydantic-settings" \
  "typer>=0.12" \
  "tqdm>=4.66" \
  "loguru>=0.7" \
  "tenacity>=8.2" \
  "python-dateutil" \
  "psutil"
```

---

## Architecture Patterns

### System Architecture Diagram

```
CLI: python -m pipeline.ingest <folder>
    │
    ├─[1] Discover PDFs (pathlib.Path.glob)
    │
    ▼
[2] Docling VlmPipeline (Granite-Docling-258M)
    │   converter.convert(pdf_path) → ConversionResult
    │   - Extracts text, tables, structure per page
    │   - Returns conv_res.document (DoclingDocument)
    │
    ├──▶ [3] pypdfium2 rasterizer (independent pass)
    │        - Open same PDF with pdfium.PdfDocument
    │        - page.render(scale=150/72) → PIL Image → PNG bytes
    │        - Stored as BLOB in SQLite pages table
    │
    ▼
[4] SQLite writer
    │   documents table  ← one row per PDF
    │   pages table      ← one row per page (text + image_blob)
    │   extractions table  ← empty in Phase 1, schema ready
    │   evaluations table  ← empty in Phase 1, schema ready
    │
    ▼
[5] Langfuse @observe spans
    ingest_document() → trace with doc_id, page_count, status
    rasterize_pages() → child span
    write_to_db()    → child span
    │
    ▼
Streamlit app.py (streamlit run src/app.py)
    │
    ├─ Sidebar: Langfuse connection status (auth_check())
    ├─ Tab "Compliance" → placeholder (Phase 2)
    ├─ Tab "Chat"        → placeholder (Phase 3)
    └─ Tab "Eval"        → placeholder (Phase 4)
```

### Recommended Project Structure

```
pfizer-externship/
├── src/
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── ingest.py          # CLI entry point (typer app)
│   │   ├── converter.py       # Docling VlmPipeline wrapper
│   │   ├── rasterizer.py      # pypdfium2 page image renderer
│   │   └── db_writer.py       # SQLite write layer
│   ├── db/
│   │   ├── __init__.py
│   │   ├── schema.py          # CREATE TABLE DDL + init_db()
│   │   └── queries.py         # Read helpers for Streamlit
│   ├── config.py              # pydantic-settings Config model
│   ├── tracing.py             # Langfuse client init + auth check
│   └── app.py                 # Streamlit entry point
├── data/
│   └── pdfs/                  # Input PDF folder (gitignored)
├── compliance.db              # SQLite database (gitignored)
├── pyproject.toml
├── .env.example
└── .streamlit/
    └── config.toml            # server.maxUploadSize = 1024
```

### Pattern 1: Docling VlmPipeline Initialization

**What:** Initialize DocumentConverter with VlmPipeline + Granite-Docling-258M preset.
**When to use:** For every PDF in the ingest batch.
**Key rule:** Recreate `DocumentConverter` per document to avoid the Docling memory leak (C3 pitfall).

```python
# Source: https://docling-project.github.io/docling/usage/vision_models/
import gc
import torch
from docling.datamodel.base_models import InputFormat
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.pipeline.vlm_pipeline import VlmPipeline
from docling.datamodel.pipeline_options import VlmPipelineOptions
from docling.datamodel import vlm_model_specs

def convert_pdf(pdf_path: str) -> "ConversionResult":
    """Create a fresh converter per doc to avoid memory leak (PITFALL C3)."""
    pipeline_options = VlmPipelineOptions(
        vlm_options=vlm_model_specs.GRANITEDOCLING_TRANSFORMERS,
        # NOTE: generate_page_images is unreliable in VlmPipeline (issue #2416)
        # Page images are rasterized separately via pypdfium2
    )
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_cls=VlmPipeline,
                pipeline_options=pipeline_options,
            ),
        }
    )
    try:
        return converter.convert(source=pdf_path)
    finally:
        del converter
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
```

[VERIFIED: Official Docling vision_models docs + GitHub issue #2416 confirms generate_page_images unreliable in VlmPipeline]

### Pattern 2: pypdfium2 Page Rasterization at 150 DPI

**What:** Render each PDF page to PNG bytes at 150 DPI independently of Docling.
**When to use:** After Docling text extraction, for every page.

```python
# Source: https://pypdfium2.readthedocs.io/en/stable/python_api.html
import io
import pypdfium2 as pdfium

DPI_TARGET = 150
SCALE = DPI_TARGET / 72  # ≈ 2.083; 1 PDF unit = 1/72 inch

def rasterize_pages(pdf_path: str) -> list[bytes]:
    """Render all pages to PNG bytes at 150 DPI."""
    png_blobs = []
    with pdfium.PdfDocument(pdf_path) as pdf:
        for page_idx in range(len(pdf)):
            page = pdf.get_page(page_idx)
            bitmap = page.render(scale=SCALE, rev_byteorder=True)
            pil_img = bitmap.to_pil()
            buf = io.BytesIO()
            pil_img.save(buf, format="PNG")
            png_blobs.append(buf.getvalue())
    return png_blobs
```

[VERIFIED: pypdfium2 official docs — scale = dpi/72, scale=1 ≈ 72 DPI]

### Pattern 3: SQLite Schema with BLOB Storage

**What:** Three-table schema aligned with D-01 and D-02 decisions.
**When to use:** Called once on first run via `init_db()`.

```python
# Source: https://docs.python.org/3/library/sqlite3.html
SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS documents (
    doc_id      TEXT PRIMARY KEY,          -- SHA-256 of file path
    filename    TEXT NOT NULL,
    file_path   TEXT NOT NULL,
    page_count  INTEGER NOT NULL,
    ingested_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    docling_json TEXT,                     -- DoclingDocument.export_to_json()
    status      TEXT DEFAULT 'pending'     -- pending | ingested | error
);

CREATE TABLE IF NOT EXISTS pages (
    page_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id      TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    page_num    INTEGER NOT NULL,          -- 0-indexed
    page_text   TEXT,                      -- Docling markdown export for this page
    image_blob  BLOB,                      -- 150 DPI PNG bytes (D-02)
    UNIQUE (doc_id, page_num)
);

CREATE TABLE IF NOT EXISTS extractions (
    extraction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id        TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    field_name    TEXT NOT NULL,
    field_value   TEXT,
    confidence    REAL,
    source_page   INTEGER,
    source_bbox   TEXT,                    -- JSON [x0,y0,x1,y1]
    verbatim_span TEXT,
    trace_id      TEXT,
    created_at    TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    needs_review  BOOLEAN DEFAULT 0,
    UNIQUE (doc_id, field_name)
);

CREATE TABLE IF NOT EXISTS evaluations (
    eval_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT NOT NULL,
    pipeline_label TEXT NOT NULL,          -- 'phase1' | 'phase2'
    metric_name   TEXT NOT NULL,
    metric_value  REAL,
    doc_id        TEXT,
    created_at    TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_pages_doc_id ON pages(doc_id);
CREATE INDEX IF NOT EXISTS idx_extractions_doc_id ON extractions(doc_id);
CREATE INDEX IF NOT EXISTS idx_evaluations_run_id ON evaluations(run_id);
"""

def init_db(db_path: str) -> None:
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()
```

[CITED: https://docs.python.org/3/library/sqlite3.html — PRAGMA foreign_keys, BLOB type]
[ASSUMED: Column selection and schema layout — no single canonical pharma schema source; aligned with ARCHITECTURE.md section 7]

### Pattern 4: Langfuse v3 Tracing for Non-LangChain Code

**What:** `@observe` decorator from `langfuse.decorators` for the ingestion pipeline.
**When to use:** Wrap `ingest_document()`, `rasterize_pages()`, `write_to_db()`.

**CRITICAL: Version 3 import paths (will break if upgraded to v4):**

```python
# Source: https://langfuse.com/docs/observability/sdk/python/decorators (v2/v3 style)
# langfuse package version: >=3.0,<4.0  (e.g., 3.14.6)
from langfuse.decorators import langfuse_context, observe
from langfuse import Langfuse

# Connection verification (blocking — use only at startup/health check)
def verify_langfuse_connection() -> bool:
    try:
        return langfuse_context.auth_check()
    except Exception:
        return False

# Decorate ingestion functions
@observe(name="ingest_document")
def ingest_document(pdf_path: str, db_path: str) -> dict:
    langfuse_context.update_current_trace(
        tags=["phase1", "ingestion"],
        metadata={"doc_path": pdf_path},
    )
    # ... ingestion logic ...
    return {"status": "ok", "page_count": n}

@observe(name="rasterize_pages")
def rasterize_and_store(pdf_path: str, doc_id: str, db_path: str) -> int:
    # child span automatically nested under parent @observe
    blobs = rasterize_pages(pdf_path)
    # ... write BLOBs to SQLite ...
    return len(blobs)
```

**v4 BREAKING changes to watch for (do NOT use):**
- v4 changes `from langfuse.callback import CallbackHandler` → `from langfuse.langchain import CallbackHandler`
- v4 changes `langfuse_context.update_current_trace(...)` → `langfuse.update_current_trace(...)`
- v4 changes `langfuse_context.auth_check()` API decomposed

[CITED: https://langfuse.com/docs/observability/sdk/upgrade-path/python-v3-to-v4]
[VERIFIED: PyPI langfuse 4.5.1 is v4; 3.14.6 is latest v3; hard pin `<4.0` is mandatory per CLAUDE.md]

### Pattern 5: Streamlit Skeleton with Langfuse Status

**What:** Three-tab layout with session state and Langfuse connection check on startup.

```python
# Source: https://docs.streamlit.io/develop/api-reference/layout/st.tabs
import streamlit as st
from src.tracing import verify_langfuse_connection

st.set_page_config(page_title="Pfizer SDF Intelligence", layout="wide")

# Langfuse connection status in sidebar (runs once per session)
if "langfuse_ok" not in st.session_state:
    st.session_state.langfuse_ok = verify_langfuse_connection()

with st.sidebar:
    status = "Connected" if st.session_state.langfuse_ok else "Not connected"
    color = "green" if st.session_state.langfuse_ok else "red"
    st.markdown(f"**Langfuse:** :{color}[{status}]")

# Three-tab layout (D-03)
tab_compliance, tab_chat, tab_eval = st.tabs(["Compliance", "Chat", "Eval"])

with tab_compliance:
    st.header("Compliance Dashboard")
    st.info("Phase 2 will populate this tab with extracted document metadata.")

with tab_chat:
    st.header("Document Q&A")
    st.info("Phase 3 will wire the RAG chatbot here.")

with tab_eval:
    st.header("Evaluation")
    st.info("Phase 4 will surface eval metrics here.")
```

[CITED: https://docs.streamlit.io/develop/api-reference/layout/st.tabs — st.tabs() returns sequence of TabContainer objects]

### Pattern 6: CLI Entry Point with typer and tqdm

**What:** `python -m pipeline.ingest <folder>` with progress bars and error handling.

```python
# Source: https://typer.tiangolo.com/ (implied standard pattern)
import typer
from pathlib import Path
from tqdm import tqdm
from loguru import logger

app = typer.Typer()

@app.command()
def ingest(
    folder: Path = typer.Argument(..., help="Folder containing PDF files"),
    db_path: str = typer.Option("compliance.db", help="SQLite database path"),
    skip_existing: bool = typer.Option(True, help="Skip already-ingested docs"),
):
    """Ingest all PDFs in a folder into the compliance database."""
    pdf_files = sorted(folder.glob("*.pdf"))
    if not pdf_files:
        typer.echo(f"No PDFs found in {folder}")
        raise typer.Exit(1)

    typer.echo(f"Found {len(pdf_files)} PDFs")
    errors = []

    for pdf_path in tqdm(pdf_files, desc="Ingesting PDFs", unit="doc"):
        try:
            ingest_document(str(pdf_path), db_path)
        except Exception as exc:
            logger.error(f"Failed: {pdf_path.name} — {exc}")
            errors.append((pdf_path.name, str(exc)))

    typer.echo(f"Done. {len(pdf_files) - len(errors)} succeeded, {len(errors)} failed.")
    if errors:
        for name, err in errors:
            typer.echo(f"  ERROR: {name}: {err}", err=True)

if __name__ == "__main__":
    app()
```

### Anti-Patterns to Avoid

- **Running Docling inside a Streamlit callback:** Heavy model inference blocks the UI thread and Streamlit's rerun model restarts it. Ingestion is a CLI-only operation.
- **Sharing one `DocumentConverter` instance across all PDFs:** Causes the Docling memory leak (C3). Recreate per document.
- **Using `generate_page_images=True` in VlmPipelineOptions for 150 DPI PNGs:** Broken for VLM pipeline (GitHub issue #2416). Use pypdfium2 separately.
- **Upgrading langfuse to v4:** The `langfuse.callback.CallbackHandler` and `langfuse_context.auth_check()` APIs changed. Pin strictly to `<4.0`.
- **Storing page images as files alongside the database:** Violates D-02 (BLOB storage). Creates deployment complexity.
- **`PRAGMA foreign_keys` omitted:** SQLite does NOT enforce FK constraints by default — must be set per connection.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| PDF text + layout extraction | Custom OCR pipeline | Docling VlmPipeline | Stamps, rotated scans, complex tables: hand-rolled OCR mangles them (M3 pitfall) |
| PDF page rasterization | PIL + subprocess poppler | pypdfium2 | No system deps, cross-platform, works in Colab without apt-get |
| LLM/pipeline tracing | Custom logging system | Langfuse `@observe` | Per-trace metadata, token cost, latency — free via decorator |
| CLI argument parsing | argparse + manual help | typer | Type-annotated, auto-generates help text, rich error messages |
| Progress bars | print() counters | tqdm | Thread-safe, ETA, works in Colab and terminal |
| Retry on API failures | manual try/except loops | tenacity | Handles exponential backoff, jitter, configurable stop conditions |
| Environment variable loading | os.environ.get() scattered | pydantic-settings | Validates types, raises clear errors for missing required vars |

**Key insight:** The ingestion stack is surprisingly complex under the hood — Docling handles 17+ PDF backend quirks. Never attempt to replicate that logic.

---

## Common Pitfalls

### Pitfall 1: Docling Memory Leak on Sequential Batch (C3)
**What goes wrong:** Processing a folder of 50+ PDFs with a single `DocumentConverter` instance leaks 3–4 GB RAM and OOMKills the Colab runtime around doc 30–50.
**Why it happens:** Docling's converter does not fully release memory between documents; the Granite-Docling VLM path holds GPU tensors.
**How to avoid:** Recreate `DocumentConverter` per document inside the loop; call `del converter; gc.collect(); torch.cuda.empty_cache()` after each conversion.
**Warning signs:** RAM monitor climbs monotonically; Colab "Too much RAM" banner; crash repeatable around same document index.

[VERIFIED: Docling GitHub issue #2829]

### Pitfall 2: VlmPipeline generate_page_images is Broken
**What goes wrong:** Setting `generate_picture_images=True` on `VlmPipelineOptions` does not produce page images; the option only works if the VLM output includes explicit image tokens (which Granite-Docling-258M does in DocTags format, but the pipeline integration has an open bug where `images_scale` causes positional errors).
**Why it happens:** VlmPipeline delegates image extraction to the VLM output; remote API VLMs can't return embedded images; Granite-Docling local path has open issue #2416.
**How to avoid:** Rasterize pages with pypdfium2 in a completely separate pass. This is actually cleaner — Docling owns text, pypdfium2 owns images.
**Warning signs:** `page.image.pil_image` returns `None`; no PNG files written; no error raised.

[VERIFIED: GitHub issue #2416 open 2025; GitHub discussion #2833]

### Pitfall 3: Langfuse v4 Import Paths Break v3 Code
**What goes wrong:** PyPI latest langfuse is 4.5.1. If `pip install langfuse` without the version pin installs v4, `from langfuse.callback import CallbackHandler` raises `ImportError`; `langfuse_context.auth_check()` raises `AttributeError`.
**Why it happens:** Langfuse published v4 as a major breaking release; package managers install latest by default.
**How to avoid:** Hard pin `langfuse>=3.0,<4.0` in `pyproject.toml`; validate pin at the top of `tracing.py` with `import langfuse; assert langfuse.__version__.startswith('3.')`.
**Warning signs:** `ImportError: cannot import name 'CallbackHandler' from 'langfuse.callback'`.

[VERIFIED: PyPI shows langfuse 4.5.1 as latest; v3→v4 migration guide confirms breaking changes]

### Pitfall 4: SQLite Foreign Keys Not Enforced by Default
**What goes wrong:** `DELETE FROM documents` leaves orphaned rows in `pages`, `extractions`, `evaluations` silently because SQLite's FK enforcement is OFF unless explicitly enabled per connection.
**Why it happens:** SQLite legacy behavior — FK enforcement opt-in.
**How to avoid:** Run `PRAGMA foreign_keys = ON;` on every new connection. Use a connection factory function that always sets this pragma.
**Warning signs:** Row counts in child tables grow unboundedly; deleting a document doesn't cascade.

[CITED: https://www.sqlite.org/foreignkeys.html]

### Pitfall 5: Streamlit Reruns Resetting Session State
**What goes wrong:** Langfuse connection status, loaded data, and any expensive initialization is recomputed on every widget interaction because Streamlit reruns the full script.
**Why it happens:** Streamlit's execution model reruns the script top-to-bottom on every interaction.
**How to avoid:** Guard all initialization with `if "key" not in st.session_state: ...`; use `@st.cache_resource` for objects that are expensive to create (like DB connections).
**Warning signs:** Langfuse `auth_check()` called on every button click; slow UI; repeated log entries.

[CITED: https://docs.streamlit.io/develop/concepts/architecture/session-state]

### Pitfall 6: pypdfium2 Scale Calculation Confusion
**What goes wrong:** `page.render(scale=1.5)` produces ~108 DPI (not 150), because the documentation `render_topil(scale=1.5)` tutorial uses an informal approximation. The correct formula is `scale = DPI / 72`.
**Why it happens:** pypdfium2 scale=1 renders at native PDF resolution (72 DPI for a standard page). 150 DPI requires scale = 150/72 ≈ 2.083.
**How to avoid:** Always use `scale = TARGET_DPI / 72` as a named constant. Set `DPI_TARGET = 150` in config.
**Warning signs:** Page thumbnails are noticeably low-resolution; file sizes unexpectedly small.

[VERIFIED: pypdfium2 official docs — "to convert DPI to scale, multiply by 1/72"]

---

## Code Examples

### Complete Ingest Loop (combining all patterns)

```python
# Source: Synthesized from Docling docs + pypdfium2 docs + pitfall C3 mitigation
import hashlib
import sqlite3
from pathlib import Path
from langfuse.decorators import observe, langfuse_context
from loguru import logger

@observe(name="ingest_document")
def ingest_document(pdf_path: str, db_path: str) -> dict:
    """Full ingestion: Docling text + pypdfium2 images + SQLite write."""
    doc_id = hashlib.sha256(pdf_path.encode()).hexdigest()[:16]
    langfuse_context.update_current_trace(
        tags=["phase1", "ingestion"],
        metadata={"doc_id": doc_id, "filename": Path(pdf_path).name},
    )

    # Step 1: Docling text extraction (recreate converter each time — C3 mitigation)
    conv_result = convert_pdf(pdf_path)
    doc = conv_result.document
    page_count = len(doc.pages) if doc.pages else 0

    # Step 2: pypdfium2 rasterization (independent of Docling)
    png_blobs = rasterize_pages(pdf_path)  # returns list[bytes]

    # Step 3: SQLite writes
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "INSERT OR REPLACE INTO documents (doc_id, filename, file_path, page_count, docling_json) VALUES (?,?,?,?,?)",
            (doc_id, Path(pdf_path).name, pdf_path, page_count, doc.export_to_json()),
        )
        for page_num, (page_key, page_obj) in enumerate(doc.pages.items()):
            page_text = page_obj.export_to_markdown() if hasattr(page_obj, 'export_to_markdown') else ""
            blob = png_blobs[page_num] if page_num < len(png_blobs) else None
            conn.execute(
                "INSERT OR REPLACE INTO pages (doc_id, page_num, page_text, image_blob) VALUES (?,?,?,?)",
                (doc_id, page_num, page_text, sqlite3.Binary(blob) if blob else None),
            )
        conn.execute(
            "UPDATE documents SET status='ingested' WHERE doc_id=?", (doc_id,)
        )
    logger.info(f"Ingested {Path(pdf_path).name}: {page_count} pages, {len(png_blobs)} images")
    return {"doc_id": doc_id, "page_count": page_count, "image_count": len(png_blobs)}
```

### DoclingDocument Page Text Extraction

```python
# Source: https://docling-project.github.io/docling/concepts/docling_document/
def extract_page_texts(conv_result) -> dict[int, str]:
    """Extract markdown text per page from DoclingDocument."""
    page_texts = {}
    doc = conv_result.document
    # Iterate document text items, group by source page
    for text_item in doc.texts:
        if text_item.prov:
            for prov in text_item.prov:
                page_no = prov.page_no
                if page_no not in page_texts:
                    page_texts[page_no] = []
                page_texts[page_no].append(text_item.text)
    return {pno: "\n".join(chunks) for pno, chunks in page_texts.items()}
```

[CITED: https://docling-project.github.io/docling/concepts/docling_document/ — texts items with .prov page provenance]

### Retrieve Page Image from SQLite as PIL

```python
# For Streamlit display and Phase 2 ColQwen embedding
import io
from PIL import Image
import sqlite3

def get_page_image(db_path: str, doc_id: str, page_num: int) -> Image.Image | None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        row = conn.execute(
            "SELECT image_blob FROM pages WHERE doc_id=? AND page_num=?",
            (doc_id, page_num)
        ).fetchone()
    if row and row[0]:
        return Image.open(io.BytesIO(row[0]))
    return None
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| PyMuPDF + Tesseract for PDFs | Docling VlmPipeline + Granite-Docling-258M | 2024–2025 | 97.9% table extraction accuracy; handles stamps and rotated scans |
| langfuse.decorators (v2) | langfuse.decorators still works in v3; v4 has new OTEL-based API | March 2026 (v4 GA) | Hard pin at <4.0; v4 breaks CallbackHandler import path |
| `from langfuse.callback import CallbackHandler` | Same in v3; changed to `from langfuse.langchain import CallbackHandler` in v4 | v4 release | Do NOT upgrade without explicit migration work |
| pdf2image (poppler) for rasterization | pypdfium2 (no system deps) | 2023 | Colab-compatible without apt-get; same API ergonomics |
| argparse for CLI | typer (type-annotated, rich help) | 2021–2025 | Less boilerplate; click-compatible under the hood |

**Deprecated / outdated:**
- `rank_bm25`: 10–100× slower than `bm25s`; relevant in Phase 3 but good to note now
- Langfuse Python SDK v2: EOL — v3 (3.14.x) is what `>=3.0,<4.0` resolves to
- Docling `PdfPipeline.VLM` enum: Use `pipeline_cls=VlmPipeline` directly (GitHub issue #1365 — enum path was broken)

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `doc.pages.items()` iterates pages in order; `page_obj.export_to_markdown()` returns page-level markdown | Code Examples | Must verify against actual DoclingDocument API at implementation time; may need to iterate `doc.texts` grouped by page prov instead |
| A2 | SQLite BLOB of 150 DPI PNGs for a 50-doc demo corpus (~5–10 pages/doc, ~200KB/image) will stay under 1 GB total | Architecture Patterns | If pages are high-res multipage docs the DB could balloon; mitigation: compress PNGs or cap resolution |
| A3 | `langfuse_context.update_current_trace(tags=[...], metadata={...})` is the correct v3 API | Pattern 4 | Confirmed from v3→v4 migration docs showing the v3 pattern; must test against pinned 3.14.6 |
| A4 | typer `0.25.0` is compatible with Python 3.11 without issues | Standard Stack | Typer is actively maintained; no known compatibility issues with 3.11 [ASSUMED] |

---

## Open Questions (RESOLVED)

1. **DoclingDocument page text extraction API** — RESOLVED
   - What we know: `doc.texts` contains text items with `.prov` page provenance; `doc.pages` is a dict keyed by page number
   - What's unclear: Whether `page.export_to_markdown()` exists or whether text must be aggregated from `doc.texts` filtered by `prov.page_no`
   - Recommendation: Check actual DoclingDocument at runtime; have both approaches ready (A1 assumption)

2. **Colab HF_HOME caching for Granite-Docling-258M** — RESOLVED
   - What we know: Weights are ~500 MB; downloaded on first `convert()` call; `HF_HOME` env var controls cache location
   - What's unclear: Whether `VlmPipelineOptions(vlm_options=vlm_model_specs.GRANITEDOCLING_TRANSFORMERS)` pulls from HF Hub or a Docling-specific location
   - Recommendation: Set `HF_HOME=/content/drive/MyDrive/hf_cache` in Colab; document that first ingest will take extra time

3. **SQLite BLOB size for production demo** — RESOLVED
   - What we know: 150 DPI PNG for a typical A4 page ≈ 150–300 KB; 50 docs × 10 pages = ~75–150 MB of image BLOBs
   - What's unclear: Whether SQLite performance degrades significantly at >500 MB total DB size for read-heavy Streamlit
   - Recommendation: Monitor DB file size during ingest; if >500 MB consider switching image storage to flat files with path stored in DB (but this contradicts D-02 — requires user confirmation)

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11+ | All | [ASSUMED] | — | Must be installed |
| CUDA GPU (L4 preferred) | Granite-Docling-258M inference | Unknown — depends on execution env | — | CPU fallback: 10–20× slower but functional |
| Langfuse Cloud account | Observability | Unknown — needs API keys | — | Run without tracing (set `LANGFUSE_ENABLED=false`) |
| Colab Pro L4 | Fast Docling inference | User-dependent | — | Local GPU or CPU fallback |
| HuggingFace Hub access | Granite-Docling weight download | Unknown — network | — | Pre-cache weights in Drive; offline mode via `HF_DATASETS_OFFLINE=1` |

**Missing dependencies with no hard fallback:**
- Active internet connection for first Granite-Docling-258M weight download (~500 MB)

**Missing dependencies with fallback:**
- GPU: CPU mode works, 10–20× slower for demo scale
- Langfuse: disable tracing with env flag; Phase 1 still fully functional without it

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (latest) |
| Config file | `pytest.ini` — Wave 0 gap |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INGEST-01 | Docling converts a sample PDF without errors; rows appear in `documents` and `pages` tables | integration | `pytest tests/test_ingest.py::test_ingest_single_pdf -x` | Wave 0 |
| INGEST-01 | Memory does not grow across 3 sequential PDF conversions | integration | `pytest tests/test_ingest.py::test_memory_no_leak -x` | Wave 0 |
| INGEST-01 | CLI command `python -m pipeline.ingest <folder>` exits 0 with valid folder | smoke | `pytest tests/test_cli.py::test_ingest_cli_smoke -x` | Wave 0 |
| INGEST-02 | Each page row in DB has a non-null `image_blob` of expected size | unit | `pytest tests/test_rasterizer.py::test_png_blob_stored -x` | Wave 0 |
| INGEST-02 | Rasterized PNG is valid 150 DPI PNG (check pixel dimensions vs known page size) | unit | `pytest tests/test_rasterizer.py::test_150dpi_dimensions -x` | Wave 0 |
| Phase 1 SC-4 | SQLite schema has three tables with correct columns and FK constraints | unit | `pytest tests/test_db.py::test_schema_exists -x` | Wave 0 |
| Phase 1 SC-5 | Streamlit app starts without errors (`streamlit run` exits cleanly with `--headless`) | smoke | `pytest tests/test_app.py::test_streamlit_starts -x` | Wave 0 |
| Phase 1 SC-5 | Langfuse auth_check() returns True with valid env vars | integration | `pytest tests/test_tracing.py::test_langfuse_auth -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/ -x -q --tb=short` (< 30 seconds)
- **Per wave merge:** `pytest tests/ -v` (full suite)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/__init__.py`
- [ ] `tests/conftest.py` — shared fixtures: `tmp_db_path`, `sample_pdf_path` (1-page test PDF)
- [ ] `tests/test_ingest.py` — covers INGEST-01 (integration)
- [ ] `tests/test_rasterizer.py` — covers INGEST-02 (unit)
- [ ] `tests/test_db.py` — covers schema existence and FK enforcement
- [ ] `tests/test_cli.py` — covers CLI smoke test
- [ ] `tests/test_app.py` — covers Streamlit startup smoke
- [ ] `tests/test_tracing.py` — covers Langfuse auth check
- [ ] `pytest.ini` — configure `testpaths = tests`, `addopts = -x`
- [ ] A 1-page sample PDF for tests (or use a small public domain PDF)

---

## Security Domain

> `security_enforcement` not set in config.json — treated as enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Single-user demo; no auth in Phase 1 |
| V3 Session Management | No | No user sessions |
| V4 Access Control | No | Single-user demo |
| V5 Input Validation | Yes | Validate PDF paths (no path traversal); check file size before Docling ingest |
| V6 Cryptography | No | No encryption required for demo |
| V8 Data Protection | Yes | Pharma PDFs may contain sensitive data; store only in local SQLite, never log content |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal via CLI `--folder` arg | Tampering | Resolve path with `Path(folder).resolve()`, assert it is within expected base dir |
| Oversized PDF causing OOM/crash | DoS | Check file size before ingest (`pdf_path.stat().st_size < MAX_PDF_MB * 1024**2`) |
| SQL injection via filename stored in DB | Tampering | Always use parameterized queries (`?` placeholders) — never f-string SQL |
| Sensitive pharma data in logs | Information Disclosure | Use loguru with redaction patterns; never log page text content at INFO level |

---

## Sources

### Primary (HIGH confidence)
- [Docling official — VlmPipeline vision models](https://docling-project.github.io/docling/usage/vision_models/) — VlmPipeline initialization pattern
- [Docling official — Figure export / page images](https://docling-project.github.io/docling/examples/export_figures/) — `generate_page_images`, `images_scale`, `page.image.pil_image`
- [Docling official — DoclingDocument concepts](https://docling-project.github.io/docling/concepts/docling_document/) — `doc.texts`, `doc.pages`, provenance
- [pypdfium2 official docs](https://pypdfium2.readthedocs.io/en/stable/python_api.html) — `page.render(scale=dpi/72)`, `bitmap.to_pil()`
- [Langfuse v3→v4 migration guide](https://langfuse.com/docs/observability/sdk/upgrade-path/python-v3-to-v4) — confirmed v3 import paths and breaking changes
- [Langfuse LangGraph integration cookbook](https://langfuse.com/guides/cookbook/integration_langgraph) — `CallbackHandler` invocation pattern
- [Streamlit st.tabs docs](https://docs.streamlit.io/develop/api-reference/layout/st.tabs) — tab layout API
- [Streamlit session state docs](https://docs.streamlit.io/develop/concepts/architecture/session-state) — `st.session_state` pattern
- [Python sqlite3 docs](https://docs.python.org/3/library/sqlite3.html) — BLOB, PRAGMA foreign_keys, parameterized queries

### Secondary (MEDIUM confidence)
- [Docling GitHub issue #2416](https://github.com/docling-project/docling/issues/2416) — Confirmed VlmPipeline image extraction bug (open issue)
- [Docling GitHub discussion #2833](https://github.com/docling-project/docling/discussions/2833) — Confirmed `generate_picture_images` does not work with VLM pipeline
- [Docling GitHub issue #2829](https://github.com/docling-project/docling/issues/2829) — Confirmed Docling memory leak on sequential processing
- [Langfuse decorator docs (v2/v3 style)](https://langfuse.com/docs/observability/sdk/python/decorators) — `@observe`, `langfuse_context`
- [pypdfium2 CodersLegacy tutorial](https://coderslegacy.com/converting-pdf-to-images-using-pypdfium2/) — code examples

### Tertiary (LOW confidence — verify before use)
- [Langfuse Python SDK v3 overview snapshot](https://python-sdk-v3.docs-snapshot.langfuse.com/docs/observability/sdk/overview/) — v3 specific patterns; partially superseded by v4 docs on main site

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all package versions verified against PyPI 2026-04-27
- Architecture: HIGH — patterns from official Docling, pypdfium2, Langfuse, Streamlit docs
- VlmPipeline page images: HIGH (negative) — confirmed broken via GitHub issues; pypdfium2 workaround is standard
- Langfuse v3 vs v4: HIGH — PyPI confirms v4 is latest; v3→v4 migration guide confirms breaking changes; pin is mandatory
- SQLite schema: MEDIUM — column layout based on ARCHITECTURE.md; A1 assumption about DoclingDocument API needs runtime verification

**Research date:** 2026-04-27
**Valid until:** 2026-05-27 (Docling ships frequently; check issue #2416 status before Phase 5 visual work)
