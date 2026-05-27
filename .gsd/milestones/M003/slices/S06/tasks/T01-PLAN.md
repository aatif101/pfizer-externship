---
estimated_steps: 15
estimated_files: 4
skills_used: []
---

# T01: Add bounded RAG evaluation observation storage

---
estimated_steps: 7
estimated_files: 4
skills_used:
  - tdd
  - observability
---

Why: R007 needs latency, cost, and faithfulness/relevancy metric sources, but S06 must not require Langfuse, RAGAS, providers, or secrets. A small SQLite-backed observation table gives offline fixtures and future tracing/RAGAS integrations a bounded numeric input contract without changing dashboard behavior.

Do: Extend `src/db/schema.py` with an idempotent table for bounded RAG/eval observations, for example `rag_eval_observations`, with only identifier/status and numeric columns such as source_run_id, query_id, latency_ms, input_tokens, output_tokens, total_tokens, cost_usd, faithfulness, answer_relevancy, cited_doc_id, and cited_page_num. Add indexes for source_run_id/query_id. Add repository dataclass/helpers in `src/eval/repository.py` to insert/list these rows using parameterized SQL and to coerce nullable numeric fields safely. Tests should prove schema initialization, insertion, listing, and absence of raw text columns.

Done when: a temporary DB initialized through the normal schema path can store and read multiple bounded observations, and tests assert the table does not include prompt/answer/context/snippet/page-text/provider-payload/blob columns.

Threat Surface (Q3): DB rows may be created from future provider or trace integrations, so only bounded identifiers and numeric metadata are accepted; no secrets or raw document/question/answer text may be persisted.
Requirement Impact (Q4): Owns R007 and preserves R008's provider-free/no-secrets dashboard boundary; re-test eval repository and schema contracts.
Failure Modes (Q5): Missing table after migration should be fixed by `init_db`; malformed numeric values should fail validation before persistence or be normalized predictably; missing optional observation rows must return an empty list.
Load Profile (Q6): Shared resource is SQLite; per-operation cost is one insert/list query per bounded observation; indexes prevent query-id/source-run-id scans from becoming the first 10x bottleneck.
Negative Tests (Q7): Empty DB after init, nullable numeric columns, missing observations, and raw-text column absence.

## Inputs

- `src/db/schema.py`
- `src/eval/repository.py`
- `tests/test_eval_db_schema.py`
- `tests/test_eval_repository.py`

## Expected Output

- `src/db/schema.py`
- `src/eval/repository.py`
- `tests/test_eval_db_schema.py`
- `tests/test_eval_repository.py`

## Verification

venv/Scripts/python.exe -m pytest -q tests/test_eval_db_schema.py tests/test_eval_repository.py

## Observability Impact

Creates the bounded SQLite inspection surface for optional RAG/eval operational and quality metrics while documenting the no-raw-text persistence boundary in tests.
