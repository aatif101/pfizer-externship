# Pfizer SDF Intelligence System

An AI-powered pharmaceutical supplier-document (SDF) compliance intelligence system. It takes a folder of supplier PDFs (certificates of analysis, vendor certificates, compliance forms — many scanned or stamped) and delivers an end-to-end pipeline: document ingestion, automated field extraction with grounded abstention, deterministic hybrid retrieval with evidence-gated RAG chat, a Streamlit compliance dashboard, and an evaluation harness.

**Core value:** a pharmaceutical compliance officer uploads supplier PDFs, immediately sees which documents are expired or at risk, asks natural language questions across the entire corpus, and trusts that every answer is grounded in a cited source page — no hallucination.

## Architecture

| Stage | What it does |
|-------|--------------|
| **Ingestion** | Docling (Granite-Docling VLM pipeline) parses PDFs — including scanned and stamped pages — into per-page text persisted in SQLite (`compliance.db`). |
| **Extraction** | Gemini 2.5 Flash extracts six SDF compliance fields with verbatim-span grounding: every extracted value must cite an exact text span on a source page, or the field abstains. An opt-in visual fallback re-runs low-yield documents with page images. |
| **Retrieval** | Tier 1: deterministic SQLite FTS5 plus lexical scoring over page text, including OCR-backfilled text for scanned pages. Tier 2: Qdrant plus ColQwen2.5 visual retrieval over page images, fused with the text tier by confidence-aware RRF. Both sit behind the same evidence gate. |
| **Answer service (RAG)** | Evidence-gated: the LLM provider is never called when retrieval evidence is weak; the service abstains instead. Citations are derived only from retrieval hits, never from model output. |
| **Dashboard** | Streamlit 3-tab app: compliance table with risk flagging, document/chat views, and eval history. |
| **Evaluation** | Run-scoped extraction/retrieval eval history persisted in `compliance.db`. |
| **Observability** | Langfuse v3 tracing across extraction, indexing, retrieval, and answering. Optional — a silent no-op when keys are absent. |

## Setup

Requires Python 3.11.

```
python -m venv venv
venv\Scripts\activate          # Windows (source venv/bin/activate on POSIX)
pip install -e .               # or: pip install -e ".[dev]" for pytest
```

Create a `.env` at the repo root:

```
GEMINI_API_KEY=...             # required for extraction and chat answers

# Optional — Langfuse v3 tracing (silent no-op when unset)
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
LANGFUSE_HOST=https://cloud.langfuse.com
```

On Windows, run tests with `venv\Scripts\python.exe -m pytest` (do not rely on bash).

## Demo flow

```
# 1. Ingest a folder of supplier PDFs into SQLite
python -m src.pipeline <pdf-folder> --db-path compliance.db

# 2. Build and inspect the retrieval index
python -m src.retrieval build --db-path compliance.db
python -m src.retrieval status --db-path compliance.db

# 3. Extract SDF compliance fields (Gemini)
python -m src.extraction.cli extract-all --db-path compliance.db
#    Re-run low-yield documents with page-image visual fallback:
python -m src.extraction.cli extract-all --db-path compliance.db --visual-fallback
#    Or extract a single document:
python -m src.extraction.cli extract --doc-id <id> --db-path compliance.db

# 4. Launch the compliance dashboard
streamlit run src/app.py
```

## Retrieval tiers

- **Tier 1 (text):** deterministic SQLite FTS5 plus lexical scoring over indexed page text, including OCR-backfilled text for scanned pages that have no extractable text. Fully offline and reproducible. Strong/weak evidence is decided by explicit score and coverage thresholds before any LLM is involved.
- **Tier 2 (visual):** Qdrant plus ColQwen2.5 (`vidore/colqwen2.5-v0.2`) late-interaction retrieval over rasterized page images, fused with the text tier by confidence-aware RRF behind the same evidence gate. It retrieves pages the text tier misses or ranks weakly, such as scanned certificate pages.

On the 17-query gold set: text-only recall@5 0.882, recall@10 0.941; visual-fused recall@5 1.000, recall@10 1.000. The visual tier runs on Colab L4 (`notebooks/visual_retrieval_colab.ipynb`); it needs a GPU for the ColQwen2.5 weights.

## Testing

```
venv\Scripts\python.exe -m pytest
```

394 tests, all fully offline. No API keys required; tracing, providers, and network boundaries are faked at module seams.

## Data hygiene

Confidential supplier PDFs and databases never leave the machine and are never committed: `*.db`, `private/`, and `local_data/` are gitignored.
