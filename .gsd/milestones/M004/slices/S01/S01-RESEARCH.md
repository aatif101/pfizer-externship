# S01 Research: Run scoped extraction history

## Summary

S01 is an additive SQLite/repository change around an already stable extraction persistence boundary. Current persistence is intentionally latest-write: `src/extraction/repository.py` upserts exactly six rows into `extractions` keyed by `UNIQUE(doc_id, field_name)` and one row into `compliance_records` keyed by `doc_id`. `SDFExtractionRecord.run_id` already exists and `extract_document(..., run_id=...)` already passes a run id through the provider, returned diagnostics, latest extraction rows, and latest compliance row. What is missing is historical storage keyed by `(run_id, doc_id, field_name)` and `(run_id, doc_id)` plus query helpers to reconstruct a record or dashboard-ready rows for a selected run.

Active requirements supported by this slice:
- R011: Preserve extraction and compliance results by run. This is the primary S01 requirement.
- R012: Compliance dashboard run selection depends on S01 producing run-scoped compliance rows and run summaries.
- R013/R014/R015: Later usage observations, visual fallback, and final comparison need stable extraction run identity and run-specific predicted extraction reads.
- R016/R017: Keep local confidential artifacts bounded and verify with Windows-native commands.

Prior memory constraints that matter:
- `src.extraction.repository` is the SQLite boundary; callers pass validated `SDFExtractionRecord` models and repository writes use SQL placeholders.
- The extraction pipeline/provider boundary must not log or return raw page text/provider payloads; diagnostics are run IDs, trace IDs, provider names/classes, and reason codes only.
- Compliance dashboard and future run selector should remain credential-free/provider-free and read persisted SQLite rows only.

## Recommendation

Implement S01 by adding additive history tables and repository helpers while preserving the current latest-write behavior unchanged:

1. Add new tables in `src/db/schema.py`:
   - `extraction_runs` for stable run summary metadata.
   - `extraction_history` for field-level historical rows keyed by `PRIMARY KEY(run_id, doc_id, field_name)`.
   - `compliance_record_history` for dashboard-ready historical rows keyed by `PRIMARY KEY(run_id, doc_id)`.
2. Keep existing `extractions` and `compliance_records` as compatibility/latest-write tables. `upsert_extraction_record()` should still write them exactly as today, then also write history when `record.run_id` is present.
3. Add run-scoped repository reads, probably in `src/extraction/repository.py`:
   - `get_extraction_record_for_run(db_path, run_id, doc_id) -> SDFExtractionRecord | None`
   - `list_compliance_records_for_run(db_path, run_id) -> list[dict[str, Any]]`
   - `list_extraction_run_summaries(db_path) -> list[ExtractionRunSummary]` or list of dicts for dashboard consumption.
   - Optional but useful for S05: `list_predicted_extractions_for_run(db_path, run_id)` in `src/eval/repository.py` or extraction repository.
4. Populate `extraction_runs` from `upsert_extraction_record()` with `INSERT ... ON CONFLICT DO UPDATE` using allowlisted metadata from the record/history only: `run_id`, first/last extracted timestamp, document count, maybe `status='complete'`, and no prompts/page text/provider payloads.
5. Treat `record.run_id is None` as latest-only compatibility: preserve legacy behavior and skip history rather than inventing a fake run id. The pipeline always creates an effective run id, so normal S01/S02/S05 flows will get history.

This is safer than modifying existing primary keys because many tests and adapters assume current latest tables. It aligns with D021: run-scoped history alongside latest-write tables, not a canonical rewrite.

## Implementation Landscape

### `src/db/schema.py`

Current schema:
- `extractions`: latest field rows, `UNIQUE(doc_id, field_name)`.
- `compliance_records`: latest dashboard row, `doc_id PRIMARY KEY`, already has a `run_id` column and index.
- Migration helpers only add nullable Phase 2 columns to old `extractions` and `snippet` to retrieval pages. New S01 tables can be plain `CREATE TABLE IF NOT EXISTS` because they do not pre-exist in legacy DBs.

Recommended table shapes:

```sql
CREATE TABLE IF NOT EXISTS extraction_runs (
    run_id          TEXT PRIMARY KEY,
    status          TEXT NOT NULL DEFAULT 'complete',
    pipeline_label  TEXT,
    created_at      TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at      TIMESTAMP,
    document_count  INTEGER NOT NULL DEFAULT 0,
    field_count     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS extraction_history (
    run_id            TEXT NOT NULL REFERENCES extraction_runs(run_id) ON DELETE CASCADE,
    doc_id            TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    field_name        TEXT NOT NULL,
    field_value       TEXT,
    confidence        REAL,
    source_page       INTEGER,
    source_bbox       TEXT,
    verbatim_span     TEXT,
    trace_id          TEXT,
    created_at        TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    needs_review      BOOLEAN DEFAULT 0,
    review_state      TEXT,
    abstention_reason TEXT,
    normalized_value  TEXT,
    updated_at        TIMESTAMP,
    PRIMARY KEY (run_id, doc_id, field_name)
);

CREATE TABLE IF NOT EXISTS compliance_record_history (
    run_id                  TEXT NOT NULL REFERENCES extraction_runs(run_id) ON DELETE CASCADE,
    doc_id                  TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    doc_type                TEXT,
    vendor_name             TEXT,
    manufacturing_date      TEXT,
    effective_date          TEXT,
    revision_date           TEXT,
    expiry_date             TEXT,
    aggregate_confidence    REAL,
    review_state            TEXT,
    needs_review            BOOLEAN DEFAULT 0,
    trace_id                TEXT,
    extracted_at            TIMESTAMP,
    created_at              TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at              TIMESTAMP,
    risk_level              TEXT,
    risk_reason             TEXT,
    compliance_status       TEXT,
    age_days                INTEGER,
    source_page             INTEGER,
    source_bbox             TEXT,
    source_verbatim_span    TEXT,
    PRIMARY KEY (run_id, doc_id)
);
```

Index needs:
- `idx_extraction_runs_created_at` or `idx_extraction_runs_updated_at` for selector ordering.
- `idx_extraction_history_doc_id` and `idx_extraction_history_run_id`.
- `idx_compliance_history_run_id`, `idx_compliance_history_doc_id`, and risk/expiry indexes if S02 filters run-specific rows with same table semantics.

Watch-out: if `extraction_history` has FK to `extraction_runs`, the repository must create/upsert `extraction_runs` before inserting history rows. Keep this within the same transaction as current latest writes.

### `src/extraction/repository.py`

Current public functions:
- `upsert_extraction_field()` writes one latest field row.
- `upsert_extraction_record()` writes six latest fields and one latest compliance row transactionally.
- `get_extraction_record()` reconstructs a latest record from `documents`, `compliance_records`, and `extractions`.
- `list_compliance_records()` lists latest dashboard rows in deterministic expiry/vendor/doc order.

Natural implementation seams:
- Keep `_upsert_extraction_field()` and `_upsert_compliance_record()` untouched for latest compatibility.
- Add `_upsert_extraction_run(conn, record)`, `_upsert_extraction_history_field(conn, record.doc_id, field, record)`, and `_upsert_compliance_history_record(conn, record)`.
- Reuse `_field_from_row()`, `_json_or_none()`, `_scalar_to_db()`, `_preferred_document_evidence()`, and `_parse_datetime()` for both latest and history reads/writes.
- Consider an internal `_record_from_rows(document, compliance, field_rows)` helper to avoid duplicating reconstruction logic between latest and run-scoped reads.
- Use `_COMPLIANCE_COLUMNS` for both latest and history list outputs if possible. For history, select all `_COMPLIANCE_COLUMNS` from `compliance_record_history`; because `run_id` is part of the PK and also in the selected columns, the output shape can match dashboard rows exactly.

Potential dataclass:

```python
@dataclass(frozen=True)
class ExtractionRunSummary:
    run_id: str
    status: str
    created_at: str | None
    updated_at: str | None
    pipeline_label: str | None
    document_count: int
    field_count: int
```

S02 needs labels baseline/candidate/latest. `pipeline_label` may not be known in S01, but having a nullable column and exposing `run_id`, timestamps, doc_count, and field_count is enough for a selector. Later code can map labels from run IDs/params if needed.

### `src/extraction/pipeline.py`

Current pipeline already accepts `run_id`, creates an effective run id, sends it to provider, writes it into `SDFExtractionRecord`, then persists with `upsert_extraction_record()`. If repository history write is hooked into `upsert_extraction_record()`, the pipeline probably needs no S01 code change.

Test implication: `test_extract_document_fake_provider_persists_fields_compliance_risk_and_run_metadata` can be extended or a new test can prove pipeline persistence writes both latest rows and history for `run-offline-001`.

### `src/extraction/cli.py`

Current CLI `extract-all` does not expose a shared candidate/baseline run id; it calls `extract_document()` without `run_id`, so each document receives its own generated `sdf-...` run id. S01 acceptance only requires two runs for the same document. However S02/S05 likely want a run selector where one candidate run spans 5 docs. Planner should decide whether S01 adds a CLI `--run-id` option to `extract` and `extract-all` or defers shared batch run identity to a later slice. If added now, `extract-all --run-id baseline-real-text` should pass the same run id to every document so `list_compliance_records_for_run()` returns all docs for that run.

Risk: Reusing a run id across multiple docs is compatible with the proposed PKs. Re-running the same run id and doc is an upsert into history, not duplicate rows.

### `src/eval/repository.py` and metrics

Current extraction eval reads latest predictions from `extractions` via `list_predicted_extractions()`. For final real comparisons, S05 needs run-specific predictions. S01 can optionally add:

```python
def list_predicted_extractions_for_run(db_path: str, run_id: str) -> list[dict[str, Any]]:
    SELECT doc_id, field_name, normalized_value, review_state
    FROM extraction_history
    WHERE run_id = ?
    ORDER BY doc_id ASC, field_name ASC
```

This is a low-cost addition that keeps latest eval compatibility while unblocking run-scoped candidate comparison.

### Tests to add or update

Best first proof / highest-risk unblocker:
- Add a repository test that prepares one document, writes `run-baseline` with Vendor A, writes `run-candidate` with Vendor B, then asserts:
  - latest `get_extraction_record(doc)` and `list_compliance_records()` show Vendor B / `run-candidate`.
  - `get_extraction_record_for_run(db, 'run-baseline', doc)` still shows Vendor A.
  - `get_extraction_record_for_run(db, 'run-candidate', doc)` shows Vendor B.
  - `list_compliance_records_for_run(db, 'run-baseline')` returns Vendor A.
  - latest table counts remain 6 extraction rows and 1 compliance row, while history has 12 field rows and 2 compliance rows.

Additional tests:
- Fresh schema includes S01 tables and indexes.
- Legacy Phase 1 DB migration creates S01 tables and preserves old rows.
- FK cascade deletes history rows when document is deleted.
- `upsert_extraction_record()` with `run_id=None` remains latest-only and does not crash.
- Optional eval test for `list_predicted_extractions_for_run()` proving latest and run-scoped predictions diverge safely.
- Optional CLI test for shared `--run-id` if implemented in S01.

## Skill Discovery

Installed skills directly relevant from the prompt:
- `observability`: relevant for bounded run metadata and avoiding raw prompts/page text/provider payloads in metadata. The key rule applied here is to keep operational records allowlisted and agent-readable without leaking secrets.
- `api-design`/`design-an-interface`: marginally relevant for shaping repository public functions, but this is an internal Python repository API rather than an HTTP/API surface.

External skill search results (not installed):
- SQLite: `npx skills add martinholovsky/claude-skills-generator@sqlite-database-expert` (about 1.8K installs) looked most relevant if the team wants deeper SQLite migration/index design help. Other results were Postgres/SQLite or less directly relevant.
- Pydantic: results focused on Pydantic AI agents/logfire, not this project’s Pydantic v2 data-model use; no recommended install for S01.

## Verification

Windows-native verification only. Do not use `/bin/bash`; do not use `gsd_exec runtime=bash`.

Suggested focused command for executor evidence:

```powershell
venv/Scripts/python.exe -m pytest tests/test_extraction_schema.py tests/test_extraction_persistence.py tests/test_extraction_pipeline.py tests/test_extraction_eval_metrics.py tests/test_extraction_cli.py
```

If collecting GSD verification evidence, use `gsd_exec runtime=node` to spawn the same command, because project rules prefer node-spawned Windows Python for GSD evidence.

Useful narrower red/green sequence:
1. `venv/Scripts/python.exe -m pytest tests/test_extraction_schema.py tests/test_extraction_persistence.py`
2. `venv/Scripts/python.exe -m pytest tests/test_extraction_pipeline.py tests/test_extraction_eval_metrics.py`
3. `venv/Scripts/python.exe -m pytest tests/test_extraction_cli.py` only if CLI `--run-id` is touched.

## Risks and Constraints

- Do not alter existing `UNIQUE(doc_id, field_name)` or `doc_id PRIMARY KEY` latest tables in S01. Existing dashboard, eval, CLI, and tests depend on latest-write semantics.
- Ensure history writes happen in the same transaction as latest writes. A partial latest/history split would make run comparison untrustworthy.
- If history writes are keyed by nullable `run_id`, SQLite PK semantics can get awkward. Prefer: when `record.run_id` is missing, skip history and preserve latest compatibility; when present, require non-empty run id.
- Avoid storing new confidential payloads. Existing extraction tables already store bounded field values/source spans for local DB use. New run metadata should not add page text, prompts, provider payloads, image bytes, file paths beyond existing document table, Docling JSON, full provider responses, or secrets.
- Current page/source numbering is 0-indexed in extraction models and DB; do not convert in repository history.
- `compliance_record_history` should return the same dict keys as `list_compliance_records()` so S02 can reuse formatting with minimal adapter changes.
- Run summaries cannot infer a human-friendly baseline/candidate label from current data. Provide stable run IDs and optional nullable `pipeline_label`; S02 can layer labeling/selector behavior.

## Natural Seams for Planner

1. Schema seam: add S01 tables/indexes and schema tests.
2. Repository write seam: extend `upsert_extraction_record()` transaction to write run metadata + history while preserving latest table behavior.
3. Repository read seam: add run-scoped record/compliance/summaries reads and tests.
4. Eval compatibility seam: optionally add `list_predicted_extractions_for_run()` for later S05; this can be independent once history table exists.
5. CLI seam: optional shared `--run-id` for `extract`/`extract-all`; useful for multi-document candidate runs but not strictly necessary for the narrow S01 acceptance test.

## Forward Intelligence

- S02 will be much easier if `list_compliance_records_for_run()` returns exactly the same row shape as `list_compliance_records()` and if `list_extraction_run_summaries()` has deterministic ordering (`updated_at DESC`, then `run_id ASC`).
- S03 usage observations should reference the same `run_id`; if S01 creates `extraction_runs`, S03 can FK or soft-reference it. Avoid overfitting S01 schema to unknown Gemini usage fields.
- S04 visual fallback must preserve good grounded text values. The run-scoped history design means a visual candidate can be stored under a new run id while latest compatibility updates remain visible, but baseline history stays recoverable.
- S05 final comparison likely needs run-scoped predictions; adding `list_predicted_extractions_for_run()` now prevents re-exploration later.
- Watch for generated `extract-all` per-document run ids. If a final candidate run should cover all 5 docs under one selector option, the CLI/runner must pass a shared run id across documents at some point.
