# Codebase Map

Generated: 2026-06-07T23:16:57Z | Files: 98 | Described: 0/98
<!-- gsd:codebase-meta {"generatedAt":"2026-06-07T23:16:57Z","fingerprint":"6bd36f10f8b81c61237b8a81bffcbf693e9b42a1","fileCount":98,"truncated":false} -->

### (root)/
- `.env.example`
- `.gitignore`
- `=2.72.0,`
- `CLAUDE.md`
- `create_sample_pdf.py`
- `pyproject.toml`
- `pytest.ini`
- `venv.bat`

### .streamlit/
- `.streamlit/config.toml`

### scripts/
- `scripts/seed_and_verify.py`
- `scripts/seed_s08_uat_eval_db.py`

### src/
- `src/__init__.py`
- `src/app.py`
- `src/config.py`
- `src/tracing.py`

### src/dashboard/
- `src/dashboard/__init__.py`
- `src/dashboard/chat.py`
- `src/dashboard/compliance.py`
- `src/dashboard/eval.py`
- `src/dashboard/ui.py`

### src/db/
- `src/db/__init__.py`
- `src/db/queries.py`
- `src/db/schema.py`

### src/eval/
- `src/eval/__init__.py`
- `src/eval/extraction_metrics.py`
- `src/eval/extraction_usage_eval.py`
- `src/eval/operational_metrics.py`
- `src/eval/repository.py`
- `src/eval/retrieval_eval_runner.py`
- `src/eval/retrieval_metrics.py`

### src/extraction/
- `src/extraction/__init__.py`
- `src/extraction/cli.py`
- `src/extraction/gemini.py`
- `src/extraction/models.py`
- `src/extraction/pipeline.py`
- `src/extraction/providers.py`
- `src/extraction/repository.py`
- `src/extraction/risk.py`

### src/pipeline/
- `src/pipeline/__init__.py`
- `src/pipeline/__main__.py`
- `src/pipeline/converter.py`
- `src/pipeline/db_writer.py`
- `src/pipeline/ingest.py`
- `src/pipeline/rasterizer.py`

### src/rag/
- `src/rag/__init__.py`
- `src/rag/gemini.py`
- `src/rag/models.py`
- `src/rag/providers.py`
- `src/rag/service.py`

### src/retrieval/
- `src/retrieval/__init__.py`
- `src/retrieval/__main__.py`
- `src/retrieval/cli.py`
- `src/retrieval/indexer.py`
- `src/retrieval/models.py`
- `src/retrieval/repository.py`
- `src/retrieval/retriever.py`

### tests/
- *(41 files: 41 .py)*

### tests/fixtures/
- `tests/fixtures/sample.pdf`
