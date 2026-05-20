---
estimated_steps: 23
estimated_files: 5
skills_used: []
---

# T04: Wire extraction CLI and final regression proof

---
estimated_steps: 8
estimated_files: 4
skills_used:
  - tdd
  - observability
  - verify-before-complete
---

Why: The pipeline needs a concrete executor-facing entrypoint so S03 can truthfully claim baseline extraction can run against ingested documents, and S04 can rely on populated `compliance_records` rows.

Do:
1. Add `src/extraction/cli.py` with Typer commands for at least `extract --doc-id DOC --db-path PATH` and `extract-all --db-path PATH`.
2. Compose settings, optional Langfuse/no-op tracing, document listing, provider construction, and pipeline calls without requiring credentials at module import time.
3. Ensure `extract-all` filters or handles ingested documents from `list_documents()` deterministically and reports per-document success/failure counts without printing page text or secrets.
4. Decide CLI behavior for missing Gemini credentials: return a non-zero user-facing error for live provider mode, while tests can inject/mock fake provider behavior or use a test seam.
5. Add tests in `tests/test_extraction_cli.py` using a temp DB and mocked/fake provider path to verify one-doc and all-doc commands persist compliance rows and expose safe failure messages.
6. If a realistic SDF-like fixture is added, keep it small and non-secret; otherwise document that live Gemini smoke is opt-in and not part of default pytest.
7. Run targeted extraction tests and the full project regression using the Windows venv path with no leading `./`.

Threat Surface (Q3): CLI accepts doc IDs and DB paths. Use existing DB helpers and parameterized SQL, do not print raw page text/provider responses, and avoid exposing local secret values in errors.
Requirement Impact (Q4): Completes S03 coverage for R002, R003, R004 support, and R008. Re-verify full extraction, ingestion, app startup, and persistence regression.
Failure Modes (Q5): Missing DB/doc/pages, missing credentials, provider failure, validation failure, and SQLite write failure should produce clear exit/failure status and safe message.
Load Profile (Q6): Sequential per-document extraction; at 10x corpus size runtime/cost scales linearly and provider quota is first breakpoint. No hidden concurrency until rate limiting is designed.
Negative Tests (Q7): Unknown doc ID, no ingested docs for extract-all, missing credentials, provider failure, and malformed output through CLI seam.

Done when CLI commands are covered by executable tests, compliance rows are populated through the real entrypoint, and the full test suite passes offline.

## Inputs

- `src/extraction/pipeline.py`
- `src/extraction/providers.py`
- `src/extraction/gemini.py`
- `src/db/queries.py`
- `src/config.py`
- `tests/test_extraction_pipeline.py`
- `tests/test_extraction_provider_gemini.py`

## Expected Output

- `src/extraction/cli.py`
- `src/extraction/pipeline.py`
- `src/extraction/providers.py`
- `tests/test_extraction_cli.py`
- `tests/test_extraction_pipeline.py`

## Verification

venv/Scripts/python.exe -m pytest -q

## Observability Impact

Adds operator-visible extraction command results, per-document success/failure counts, generated run IDs, and safe error messages suitable for future debugging.
