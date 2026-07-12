# Phase 2: Extraction & Compliance - Pattern Map

**Mapped:** 2026-07-11
**Files classified:** 22 likely modified files, no new source module required
**Strong analogs:** 5 pattern families

## Scope Translation

Phase 2 should harden the existing extraction slice in place. The current module boundaries already match the desired architecture, so the planner should avoid introducing a second extraction package or generic workflow framework.

```text
src/extraction/cli.py            batch coordinator / resume entry point
  -> src/extraction/repository.py durable run + document state
  -> src/extraction/pipeline.py   provider -> validation -> risk -> persistence
       -> src/extraction/gemini.py     provider-specific schema/usage
       -> src/extraction/models.py     validated domain/run DTOs
       -> src/extraction/risk.py       pure deterministic policy
  -> src/eval/repository.py       bounded usage observations

src/db/schema.py                 additive tables/columns/indexes
src/eval/extraction_eval_runner.py terminal source-run gate
```

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match |
|-------------------|------|-----------|----------------|-------|
| `src/extraction/models.py` | model | transform/state | `src/retrieval/models.py` | role + safety match |
| `src/extraction/providers.py` | provider DTO | request-response | existing DTOs in same file; `src/eval/repository.py:71-95` | exact |
| `src/extraction/gemini.py` | provider | request-response | existing adapter; `src/rag/gemini.py:41-130` | exact |
| `src/extraction/pipeline.py` | service | transform/CRUD | existing pipeline; `src/retrieval/indexer.py:72-135` | role match |
| `src/extraction/risk.py` | utility | pure transform | existing `compute_fields_risk` | exact |
| `src/extraction/repository.py` | store | CRUD/batch | `src/retrieval/repository.py:90-170`; `src/eval/repository.py:98-156` | exact |
| `src/extraction/cli.py` | controller | batch | existing `extract_all_command`; `src/eval/extraction_eval_runner.py:44-146` | role match |
| `src/db/schema.py` | migration | CRUD | existing guarded migration helpers in same file | exact |
| `src/eval/repository.py` | store/telemetry | CRUD | existing `ExtractionUsageObservationRow` and insert/list pair | exact |
| `src/eval/extraction_eval_runner.py` | service | batch | existing eval lifecycle in same file | exact |
| `src/config.py` | config | request configuration | existing `Settings` fields | exact |
| `pyproject.toml` | config | dependency resolution | existing bounded dependency ranges | exact |
| `tests/test_extraction_models.py` | test | transform | current six-field/review-state tests | exact |
| `tests/test_extraction_provider_gemini.py` | test | request-response | current fake Gemini client tests | exact |
| `tests/test_extraction_gemini_usage.py` | test | request-response/telemetry | current usage/cost fake response tests | exact |
| `tests/test_extraction_pipeline.py` | test | transform/CRUD | current fake-provider grounding tests | exact |
| `tests/test_extraction_risk.py` | test | pure transform | current date-boundary table tests | exact |
| `tests/test_extraction_persistence.py` | test | CRUD | current run history/idempotency tests | exact |
| `tests/test_extraction_cli.py` | test | batch | current Typer fake-provider tests | exact |
| `tests/test_extraction_schema.py` | test | migration | current legacy DB migration fixtures | exact |
| `tests/test_extraction_run_history_schema.py` | test | migration/CRUD | current FK/no-content schema tests | exact |
| `tests/test_extraction_eval_runner.py` | test | batch | current eval terminal transition tests | exact |

## Strong Analog 1: Typed, Content-Free Run Models

**Source:** `src/retrieval/models.py:13-59`

Use the retrieval convention for extraction run/document statuses: a `StrEnum` plus frozen dataclasses containing identifiers, counts, hashes, statuses, timestamps, and reason codes only.

```python
class RetrievalIndexStatus(StrEnum):
    BUILT = "built"
    EMPTY = "empty"
    MISSING = "missing"
    STALE = "stale"
    ERROR = "error"

@dataclass(frozen=True)
class RetrievalIndexRun:
    run_id: str
    status: RetrievalIndexStatus
    built_at: str | None
    source_document_count: int
    source_page_count: int
    indexed_page_count: int
    content_hash: str | None = None
    error_reason: str | None = None
```

**Apply to:** `src/extraction/models.py` (or repository-local public DTOs if the planner keeps run DTOs outside the Pydantic field domain).

Recommended shapes:

```python
class ExtractionRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"

class ExtractionDocumentStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass(frozen=True)
class ExtractionRunDocument:
    run_id: str
    doc_id: str
    status: ExtractionDocumentStatus
    attempt_count: int
    trace_id: str | None = None
    error_reason: str | None = None
```

Do not add page text, field values, spans, raw errors, provider payloads, paths, or keys to these DTOs.

## Strong Analog 2: Deterministic Manifest Identity

**Source:** `src/retrieval/visual/run.py:29-74`

The visual run planner already hashes a sorted, bounded identifier manifest and records model identity separately from content.

```python
def _compute_visual_content_hash(pages_meta: Sequence[PageMeta]) -> str:
    digest = hashlib.sha256()
    for doc_id, page_num, filename in sorted(
        pages_meta, key=lambda m: (m[0], m[1], m[2])
    ):
        for value in (doc_id, page_num, filename):
            digest.update(str(value).encode("utf-8"))
            digest.update(b"\x1f")
        digest.update(b"\x1e")
    return digest.hexdigest()
```

**Apply to:** `src/extraction/repository.py` or a private helper in `src/extraction/cli.py`.

Hash the ordered target document identifiers plus a corpus-version value; persist `requested_model`, resolved model, provider, and manifest hash as separate columns. On resume, compare persisted identity before processing anything. Keep the user-supplied run ID independent from the manifest hash, but reject reuse with a mismatched manifest/model/provider/corpus version.

**Test analog:** `tests/retrieval/visual/test_run_versioning.py:109-133` asserts identical corpus -> identical ID/hash and changed corpus -> changed identity. Copy this two-case structure for extraction manifest mismatch tests.

## Strong Analog 3: Transactional Parent + Child Persistence

**Source:** `src/retrieval/repository.py:136-170`

```python
def save_index_run_with_pages(db_path, run, pages, *, snippets=None):
    conn = _connect(db_path)
    try:
        _insert_index_run(conn, run)
        conn.execute("DELETE FROM retrieval_index_pages")
        for page in page_inputs:
            _upsert_page_index_record(conn, run.run_id, page, ...)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

**Apply to:** `src/extraction/repository.py`.

Keep every lifecycle mutation behind explicit repository functions using one connection, parameterized SQL, `commit` on success, `rollback` on failure, and `close` in `finally`:

```python
begin_or_resume_extraction_run(...)
list_resume_candidates(db_path, run_id)
mark_run_document_running(...)
mark_run_document_completed(...)
mark_run_document_failed(..., reason_code)
finalize_extraction_run(db_path, run_id)
get_complete_extraction_run(db_path, run_id)
```

Use `ON CONFLICT(run_id, doc_id) DO UPDATE` for document attempts/status, mirroring `src/retrieval/repository.py:313-346` and current extraction history upserts. Compute run counts from `extraction_run_documents` in SQL; do not trust CLI-local counters as durable truth.

## Strong Analog 4: Explicit Lifecycle Transitions

**Source:** `src/eval/repository.py:98-156`

```python
def create_eval_run(...):
    conn.execute(
        """INSERT OR IGNORE INTO eval_runs
           (run_id, eval_type, status, pipeline_label, params_json)
           VALUES (?, ?, ?, ?, ?)""",
        (run_id, eval_type, "running", pipeline_label, ...),
    )

def mark_eval_run_complete(db_path: str, run_id: str) -> None:
    conn.execute(
        """UPDATE eval_runs
           SET status = ?, completed_at = strftime(...), error_reason = NULL
           WHERE run_id = ?""",
        ("complete", run_id),
    )

def mark_eval_run_error(db_path: str, run_id: str, error_reason: str) -> None:
    ...
```

**Apply to:** `src/extraction/repository.py`, `src/extraction/cli.py`, and the source-run gate in `src/eval/extraction_eval_runner.py`.

Improve on this analog by deriving the extraction terminal state once from child rows:

```text
all completed                         -> completed
some completed + one or more failed  -> partial
zero completed + one or more failed  -> failed
otherwise                            -> running, completed_at NULL
```

**Coordinator analog:** `src/eval/extraction_eval_runner.py:60-146` initializes bounded counters, creates a `running` row before work, marks complete only after work, and marks error in the exception path while updating allowlisted trace metadata. `extract-all` should follow the same outer shape, with per-document exceptions recorded and iteration continuing.

## Strong Analog 5: Lazy Provider Boundary and Fake Client Seam

**Source:** `src/rag/gemini.py:41-130`

```python
def __init__(
    self,
    *,
    api_key: str | None = None,
    model: str | None = None,
    client: Any | None = None,
    client_factory: Callable[[str], Any] | None = None,
    max_attempts: int = 2,
) -> None:
    ...

def _get_client(self) -> Any:
    if self._client is not None:
        return self._client
    if self._client_factory is not None:
        self._client = self._client_factory(self._api_key)
        return self._client
    from google import genai
    self._client = genai.Client(api_key=self._api_key)
    return self._client
```

**Apply to:** `src/extraction/gemini.py`.

Preserve constructor injection and lazy SDK import. Define private Pydantic response-envelope classes in this provider module rather than adding a second public schema module. Pass the model class through the existing plain-dict fake-client-compatible `config`:

```python
config = {
    "response_mime_type": "application/json",
    "response_schema": _GeminiExtractionResponse,
}
```

Then use `_GeminiExtractionResponse.model_validate_json(response.text)` and adapt fixed keys to `ProviderFieldPayload`. Retain the current safe all-field malformed result. Remove the prompt's hand-written JSON example so the SDK schema is the single structural contract.

For retry hardening, keep exactly one retry owner. The injected client seam must remain usable without importing Google types, credentials, or network state.

## Per-File Pattern Assignments

### `src/extraction/gemini.py` and `src/extraction/providers.py`

- Extend existing provider DTOs; do not leak Google SDK types into `providers.py`.
- Add `thought_tokens`, requested/resolved model identity, and cost basis only as bounded scalar metadata.
- Replace the single-model constants near `gemini.py:32-36` with an exact-key immutable registry.
- Extend `_extract_usage_metadata` near `gemini.py:402-425`; price `candidates + thoughts`, return null for unknown canonical models.
- Keep `GeminiSDFVisualFallbackProvider` on the same response envelope, filtering fixed fields to the requested allowlist after validation.

### `src/extraction/pipeline.py` and `src/extraction/risk.py`

The existing pipeline order at `pipeline.py:337-385` is the pattern to preserve:

```text
provider call -> normalize/ground -> optional visual fallback
-> SDFExtractionRecord -> compute_record_risk -> repository -> telemetry
```

- Tighten `_span_matches_page_text` at `pipeline.py:678-683` to produce/persist an actual source substring rather than a case-folded provider string.
- Preserve `_abstained_field` at `pipeline.py:620-640` as the universal safe failure output.
- Change the preflight at `pipeline.py:522-526` so text-empty pages can reach an explicitly configured image path; otherwise return a typed abstention/failure.
- Keep `risk.py` pure. Add a post-risk review override without moving provider or DB access into `risk.py`.

### `src/extraction/cli.py`

Reuse the current deterministic document sort and per-document typed exception handling at `cli.py:168-210`.

- Generate one effective run ID before iteration.
- Call `begin_or_resume` before provider construction/work.
- Iterate repository-provided resume candidates, not every ingested document blindly.
- Mark running before `_extract_one`; mark completed/failed afterward with safe codes.
- Finalize in an outer `finally` only when the coordinator reached the end; an interrupt must leave the run nonterminal.
- Echo only IDs, statuses, and counts using the current `_safe_error_message` pattern.

### `src/db/schema.py`

Copy the guarded migration structure at `schema.py:411-442`:

```python
existing_columns = _table_columns(conn, "extraction_runs")
for column_name, column_type in _EXTRACTION_RUN_MIGRATION_COLUMNS:
    if column_name not in existing_columns:
        conn.execute(
            f"ALTER TABLE extraction_runs ADD COLUMN {column_name} {column_type}"
        )
```

The identifiers come only from a static tuple, never user input. Run backfill after columns exist, then create indexes in `POST_MIGRATION_INDEX_SQL`. Add `extraction_run_documents` directly with `CREATE TABLE IF NOT EXISTS` because it is new.

### `src/eval/repository.py` and `src/eval/extraction_eval_runner.py`

- Extend `ExtractionUsageObservationRow` and its insert/list pair in lockstep; preserve numeric coercion before opening the write transaction (`eval/repository.py:400-447`).
- Add a bounded extraction-run lookup in the extraction repository, then call it before `create_eval_run` or before loading predictions.
- Refuse any source run not exactly terminal-success (`completed`, expected=succeeded, failed=0); mark the eval run error with a safe reason code if an eval row has already been created.
- Preserve the trace allowlist at `extraction_eval_runner.py:28-40,167-198`.

### `src/config.py` and `pyproject.toml`

- Follow existing `pydantic-settings` `Field` declarations with bounds for any retry/model-profile settings.
- Keep `GEMINI_MODEL` as the common environment override.
- Bound `google-genai` to a tested 2.x range in the same style as the other major-version caps; do not perform a broad dependency upgrade inside the extraction implementation task.

## Test Patterns to Copy

### Provider request contract

**Source:** `tests/test_extraction_provider_gemini.py:113-140`

The fake client records `model`, `contents`, and `config`; assertions inspect the call without network access. Extend this test to inspect `response_schema.model_json_schema()`:

```python
call = client.models.calls[0]
assert call["model"] == "gemini-2.5-flash"
assert call["config"]["response_mime_type"] == "application/json"
schema = call["config"]["response_schema"].model_json_schema()
assert set(schema["$defs"][...]["properties"]) == EXPECTED_FIELD_NAMES
```

Add missing key, extra key, invalid confidence, malformed date, and contradictory abstention payload cases. All must become safe abstentions or a typed validation failure; no raw payload enters output.

### Run/resume and idempotency

**Sources:**

- `tests/test_extraction_persistence.py:323-416` — two-run history, same-run/doc upsert, bounded summaries.
- `tests/retrieval/visual/test_run_versioning.py:48-68` — resave keeps one row.
- `tests/test_extraction_cli.py:218-253,297-312` — deterministic order, shared explicit run, continued provider failure.

Extend these exact fixtures for all-success, partial, all-failed, interrupted, resumed, completed-skip, failed-retry, and manifest-mismatch cases. Assert both CLI summary and durable SQL rows.

### Migration safety

**Source:** `tests/test_extraction_schema.py:128-166,184-232`

Construct the pre-hardening schema explicitly, seed a completed run/history, call `init_db` twice, then assert:

- original rows survive;
- each new column exists once;
- backfilled counts/statuses are correct;
- one completed child row exists per historical run/document;
- foreign keys and post-migration indexes exist;
- forbidden raw-content columns do not exist.

### Safe telemetry

**Source:** `tests/test_extraction_gemini_usage.py:111-127` and `tests/test_eval_db_schema.py:45-99`.

Continue using a forbidden-fragment set against DTO/row representations and a schema column allowlist. Add `thought_tokens`, requested/resolved model, and pricing basis to the allowed scalar set; keep prompt/page/span/path/payload/secret fragments forbidden.

## Shared Patterns

### Imports and boundaries

- Use absolute `src.*` imports.
- Provider SDK imports stay inside `_get_client`/part factories.
- Domain/persistence/eval modules import no live provider SDK.
- Frozen dataclasses are used for narrow repository/diagnostic DTOs; Pydantic is used where untrusted shape validation or domain invariants matter.

### Errors

- Public provider/pipeline exceptions have stable `reason_code` attributes.
- Boundary exceptions expose class, provider, model, run ID, and document ID only.
- Repository errors roll back and re-raise.
- Persist reason codes, not raw provider exception strings.

### SQL

- Parameterize all data values.
- Static f-strings are acceptable only for allowlisted table/column fragments already used by repository helpers.
- Parent/child updates use one transaction where partial state would be misleading.
- `ON CONFLICT` defines idempotent rerun semantics explicitly.

### Tracing

- Keep a frozen allowed-key set near the module boundary.
- Trace statuses at start, completion, and error.
- Never add raw field values, spans, prompts, page text, images, paths, payloads, or exception messages.

## No Close Analog / Planner Must Specify

| Capability | Why no exact analog | Planning instruction |
|------------|---------------------|----------------------|
| Per-document resumable extraction state | Existing run tables track aggregate jobs but not a durable target manifest with individual attempts. | Specify the status transition table, resume eligibility, and terminal aggregate SQL explicitly in the plan. |
| Fixed-six Gemini response object | Current provider parses an array and no other provider has the same six-field constraint. | Use the Pydantic shape from `02-RESEARCH.md`; keep it private to `gemini.py`. |
| Model-keyed pricing with billed thoughts | Existing estimator knows one stale model and stores no thought count. | Specify exact rate registry, canonical model resolution, unknown behavior, and schema migration together. |

## Files Intentionally Not Modified

- `src/dashboard/compliance.py`: already consumes stable compliance/review columns; Phase 2 should preserve that shape.
- `src/pipeline/converter.py` and `src/pipeline/ingest.py`: Phase 2 consumes persisted `DocumentPage` DTOs and must not couple extraction hardening to Docling internals.
- Phase 5 critic/visual retrieval modules: explicitly deferred.
- Gold-set metric definitions: benchmark remediation remains Phase 7, except refusing a non-complete source run.

## Metadata

**Analog search scope:** `src/extraction`, `src/db`, `src/eval`, `src/retrieval`, `src/rag`, and corresponding tests.

**Primary analogs read:**

1. `src/retrieval/models.py`
2. `src/retrieval/visual/run.py` and `repository.py`
3. `src/retrieval/repository.py` and `indexer.py`
4. `src/eval/repository.py` and `extraction_eval_runner.py`
5. `src/rag/gemini.py`

**Pattern extraction date:** 2026-07-11
