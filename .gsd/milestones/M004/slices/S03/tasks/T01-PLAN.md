---
estimated_steps: 7
estimated_files: 4
skills_used: []
---

# T01: Add bounded extraction usage observation repository

Expected executor skills: tdd, verify-before-complete.

Why: S03 needs a durable, run-scoped observation surface before any provider or eval wiring can safely record token/cost telemetry. This table must mirror the bounded RAG observation pattern while using extraction-specific keys: run_id, doc_id, stage, provider/model, status, latency, token counts, estimated cost, trace id, and sanitized error reason.

Do: Add an additive `extraction_usage_observations` table and indexes in `src/db/schema.py`. Do not alter existing latest-write extraction tables. Add a frozen repository row type plus `insert_extraction_usage_observation()` and `list_extraction_usage_observations()` helpers in `src/eval/repository.py` or a narrowly scoped repository module imported by eval code. Normalize nullable numeric fields before binding, reject bools for integer counts, reject non-finite floats, and keep all SQL parameterized. Add tests that initialize a DB twice, assert bounded columns and indexes, insert multiple observations for the same run/doc/stage, filter by run_id/doc_id/stage/status, and assert forbidden schema fragments are absent: prompt, page_text, raw_response, provider_payload, payload, image, blob, pdf, file_path, docling_json, secret, api_key.

Failure Modes (Q5): SQLite FK/schema errors should rollback the observation insert and surface as normal repository exceptions; malformed numeric inputs should raise `ValueError` before any row is written; missing optional values should persist as NULL rather than zero. No external provider dependency is involved.

Load Profile (Q6): Shared resource is SQLite. Per operation is one insert or one indexed select. At 10x document count the first bottleneck is unbounded listing, so list helpers must keep a default limit and deterministic ordering by observation_id.

Negative Tests (Q7): malformed numeric strings, bool token values, empty optional metrics, repeated run/doc/stage rows, missing filters, and forbidden raw/confidential column names.

Done when: schema/repository tests prove the observation surface is idempotent, bounded, indexed, filterable, and rejects malformed numeric telemetry without writing partial rows.

## Inputs

- `src/db/schema.py`
- `src/eval/repository.py`
- `tests/test_eval_db_schema.py`
- `tests/test_eval_repository.py`

## Expected Output

- `src/db/schema.py`
- `src/eval/repository.py`
- `tests/test_extraction_usage_observations.py`
- `tests/test_eval_db_schema.py`

## Verification

venv/Scripts/python.exe -m pytest -q tests/test_extraction_usage_observations.py tests/test_eval_db_schema.py

## Observability Impact

Creates the durable inspection surface for future agents: bounded usage rows queryable by run_id/doc_id/stage/status, with sanitized failure reason only.
