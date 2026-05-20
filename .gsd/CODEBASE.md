# Codebase Map

Generated: 2026-05-20T21:06:14Z | Files: 49 | Described: 0/49
<!-- gsd:codebase-meta {"generatedAt":"2026-05-20T21:06:14Z","fingerprint":"0e37985c6b673895ef0ca07028a8f2864cdf3e74","fileCount":49,"truncated":false} -->

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

### src/
- `src/__init__.py`
- `src/app.py`
- `src/config.py`
- `src/tracing.py`

### src/dashboard/
- `src/dashboard/__init__.py`
- `src/dashboard/compliance.py`

### src/db/
- `src/db/__init__.py`
- `src/db/queries.py`
- `src/db/schema.py`

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

### tests/
- `tests/__init__.py`
- `tests/conftest.py`
- `tests/test_app.py`
- `tests/test_compliance_dashboard.py`
- `tests/test_db.py`
- `tests/test_extraction_cli.py`
- `tests/test_extraction_models.py`
- `tests/test_extraction_persistence.py`
- `tests/test_extraction_pipeline.py`
- `tests/test_extraction_provider_gemini.py`
- `tests/test_extraction_risk.py`
- `tests/test_extraction_schema.py`
- `tests/test_ingest.py`
- `tests/test_rasterizer.py`
- `tests/test_s05_end_to_end_proof.py`
- `tests/test_tracing.py`

### tests/fixtures/
- `tests/fixtures/sample.pdf`
