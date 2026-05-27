---
estimated_steps: 15
estimated_files: 2
skills_used: []
---

# T01: Add deterministic UAT seed helper

---
estimated_steps: 7
estimated_files: 2
skills_used:
  - tdd
  - verify-before-complete
---
Why: S08 needs repeatable, sanitized data that visibly exercises R007 metric history without relying on the mutable local compliance.db or any raw document content. The helper must use existing schema and repository boundaries so the dashboard remains read-only and provider-free.

Do: Add a small Windows-safe Python script that accepts a db path, initializes the SQLite schema through src.db.schema.init_db, creates two complete synthetic evaluation runs through src.eval.repository helpers, and persists global metrics for retrieval.recall@5, retrieval.recall@10, retrieval.citation_accuracy@5, retrieval.citation_accuracy@10, rag.faithfulness.avg, rag.answer_relevancy.avg, rag.latency_ms.avg, rag.latency_ms.p50, rag.latency_ms.p95, rag.cost_usd.total, rag.cost_usd.avg, and rag.tokens.total. Use only synthetic run IDs, pipeline labels, and metric names. Do not write prompts, answers, snippets, provider payloads, file paths, source text, hashes, images, or secrets. Add a pytest file that runs the helper against tmp_path, lists rows via repository helpers, asserts exactly two complete runs, asserts expected metric families are present for each run, asserts metric values differ enough for comparison deltas, and asserts there are no raw-content columns or seeded string values matching forbidden terms.

Done when: The seed helper can be run repeatedly against the same temp DB without duplicate-run surprises, and the new test proves the populated DB contract without reading .gsd or any gitignored path.

Threat Surface Q3: Low but relevant because this writes a SQLite file. Inputs are a local db path only; keep the script limited to DB creation and synthetic constants. No user document data or network calls are permitted.

Requirement Impact Q4: Advances R007 by producing repeatable metric history data; preserves R010 by seeding synthetic values only; depends on but does not modify R008 tracing work.

Failure Modes Q5: If schema initialization fails, the script should exit nonzero with a concise error. If repository helper contracts change, pytest should fail at row or metric assertions. Malformed DB paths should fail before writing partial evidence.

Load Profile Q6: Trivial two-run seed. SQLite file writes are bounded and not representative of production load.

Negative Tests Q7: tmp_path test covers missing DB creation, repeated helper execution, expected metric names, and forbidden raw-content token absence.

## Inputs

- `src/db/schema.py`
- `src/eval/repository.py`
- `tests/test_dashboard_eval_tab.py`

## Expected Output

- `scripts/seed_s08_uat_eval_db.py`
- `tests/test_s08_uat_seed.py`

## Verification

venv/Scripts/python.exe -m pytest -q tests/test_s08_uat_seed.py tests/test_dashboard_eval_tab.py

## Observability Impact

Creates an inspectable synthetic UAT DB contract through repository rows, but does not add runtime observability hooks or provider tracing.
