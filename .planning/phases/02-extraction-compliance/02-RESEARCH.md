# Phase 2: Extraction & Compliance - Research

**Researched:** 2026-07-11
**Domain:** Gemini structured pharmaceutical extraction, deterministic compliance, resumable SQLite runs
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

### Structured extraction contract
- [D-02-01] Gemini requests use a strict response schema for exactly `doc_type`, `vendor_name`, `manufacturing_date`, `effective_date`, `revision_date`, and `expiry_date`; provider JSON is still treated as untrusted and revalidated with Pydantic.
- [D-02-02] A non-abstained field is accepted only when its page number is valid and its short verbatim span is present on that source page; unsupported, placeholder, or cross-packet values abstain instead of being guessed.
- [D-02-03] Dates normalize to ISO `YYYY-MM-DD` when parseable while preserving the raw printed value and evidence; printed `N/A` expiry remains an explicit supported no-expiry value.
- [D-02-04] The primary product/material certificate controls packet extraction; email, delivery, retest, handwritten, and unrelated attachment dates cannot silently populate compliance fields.

### Compliance and review behavior
- [D-02-05] Compliance risk is deterministic: expired expiry is red; otherwise age is based on the oldest usable manufacturing/effective/revision date, with green under 2 years, amber from 2 through 3 years, red over 3 years, and unknown evidence routed to review.
- [D-02-06] Fields below the configurable confidence threshold (default `0.75`) or any abstained field surface as `needs_review`; the baseline provider confidence is not presented as a calibrated probability.
- [D-02-07] Extraction writes are run-scoped and resumable: a batch has a terminal status, provider failures are counted safely, reruns are idempotent for the same run/document, and one failed document cannot leave the run falsely reported as complete.
- [D-02-08] Raw page text, images, provider payloads, filesystem paths, and secrets never enter logs or Langfuse metadata; traces carry only bounded identifiers, status, counts, model, latency, tokens, and cost.

### July 2026 runtime truth
- [D-02-09] The Gemini model remains environment-configurable. The project documents `gemini-2.5-flash` as the low-cost benchmark model through its announced October 16, 2026 shutdown and supports the stable `gemini-3.5-flash` quality profile without code changes.
- [D-02-10] Cost estimation uses a model-keyed July 2026 pricing table and returns unknown for unrecognized models rather than silently applying stale prices.
- [D-02-11] Provider response schemas, pricing metadata, retry bounds, and model IDs are covered by offline tests; live benchmark results must record model, date, corpus version, run ID, and actual provider usage.

### the agent's Discretion
- Exact Pydantic schema adapter shape for the Google GenAI SDK, as long as fake-client seams remain offline-safe.
- Whether resumability is implemented as document-level status rows or derived from run history, provided the behavior and audit trail are deterministic.
- Internal helper/module boundaries and migration mechanics that preserve compatibility with existing databases.

### Deferred Ideas (OUT OF SCOPE)
- Extraction critic, self-consistency, confidence ensemble, and reconciliation: Phase 5.
- Human correction UI and audit workflow: Phase 6.
- Held-out public/private benchmark reporting and model comparison: Phase 7.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EXTRACT-01 | Extract the six required fields into a Pydantic-validated model with a verbatim span and page per field. | Fixed-key Gemini response schema, second Pydantic validation, exact grounding, and abstention architecture below. |
| EXTRACT-02 | Persist deterministic green/amber/red compliance risk based on document age. | Existing pure risk function is retained and strengthened with terminal-run/review invariants and boundary tests below. |
</phase_requirements>

## Summary

Phase 2 is a hardening phase, not a greenfield build. The repository already has the six-field Pydantic domain model, grounding and abstention code, deterministic risk rules, run-scoped history, bounded telemetry, fake Gemini clients, and broad offline tests. The targeted current suite passed **87 tests in 19.61 seconds** on Python 3.11.9. `[VERIFIED: repo inspection and venv/Scripts/python.exe -m pytest, 2026-07-11]`

Four defects prevent the current implementation from satisfying its own Phase 2 contract: Gemini receives only `response_mime_type` rather than a response schema; a successful document marks the shared run `completed` before the batch is finished; the price constants are stale and omit billed thinking tokens; and a text-empty scanned packet fails before the visual path can make a conservative, review-forced decision. `[VERIFIED: src/extraction/gemini.py:130-136,402-451; src/extraction/repository.py:269-310; src/extraction/pipeline.py:522-526]`

**Primary recommendation:** implement one strict Pydantic provider envelope, one explicit batch/run state machine with per-document rows, one exact model-price registry including thinking tokens, and one Nyquist test matrix that proves every failure transition and legacy migration offline.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|--------------|----------------|-----------|
| Gemini request/response shape | Provider adapter (`src/extraction/gemini.py`) | Pydantic provider DTOs | Provider syntax stays outside domain and persistence code. |
| Semantic validation and grounding | Extraction pipeline | Domain models | The provider is untrusted; only local evidence gates may accept a value. |
| Risk band | Pure domain policy (`risk.py`) | Pipeline | Deterministic and independently testable. |
| Batch lifecycle/resume | CLI orchestration | Repository | The CLI owns the target manifest; SQLite owns durable state and counts. |
| Run/document persistence | Repository/schema | Eval runner | Transactions, idempotency, migrations, and terminal-state truth live here. |
| Usage/cost audit | Provider usage adapter | Repository/eval | Raw SDK counters are converted into bounded, model-keyed metadata. |

## Current-State Audit

| Area | Existing strength | Planning gap |
|------|-------------------|--------------|
| Provider schema | JSON-only response and safe malformed-output abstention. | No `response_schema`/`response_json_schema`; prompt duplicates a hand-written schema. `[VERIFIED: src/extraction/gemini.py]` |
| Grounding | Page membership, evidence, placeholder, Delivery Date, and Retest Date gates exist. | Span matching case-folds and collapses whitespace, so the persisted provider string is not necessarily verbatim; primary-packet scope is mainly prompt-enforced. `[VERIFIED: src/extraction/pipeline.py:554-683]` |
| Run history | `(run_id, doc_id, field_name)` and `(run_id, doc_id)` upserts are idempotent. | No target manifest or per-document failure row; per-document success sets the entire run complete. `[VERIFIED: src/extraction/repository.py]` |
| Batch CLI | Continues after typed provider failures and reports safe totals. | An omitted `--run-id` creates a different run per document; failures are not durable run facts; resume cannot skip completed docs. `[VERIFIED: src/extraction/cli.py:153-210]` |
| Cost | Unknown models correctly return null cost. | 2.5 Flash constants are `$0.15/$0.60`; official July standard rates are `$0.30/$2.50`, and `thoughts_token_count` is ignored. `[CITED: https://ai.google.dev/gemini-api/docs/pricing]` |
| Migration | Guarded additive SQLite migrations and idempotency tests exist. | New run columns/table require legacy backfill and post-migration indexes; creating an index on a not-yet-migrated column inside `SCHEMA_SQL` would break old DBs. `[VERIFIED: src/db/schema.py:377-387,411-442]` |

## Standard Stack

| Library/service | July 2026 truth | Phase 2 use |
|-----------------|-----------------|-------------|
| Python | Repo runtime 3.11.9 | Preserve current runtime. `[VERIFIED: local environment]` |
| Pydantic | Repo runtime 2.13.3 | Strict provider envelope and domain revalidation with `extra="forbid"`. `[VERIFIED: local environment]` |
| `google-genai` | Repo runtime 2.7.0; PyPI current 2.10.0 | Existing 2.7 surface supports `response_schema`, `response_json_schema`, `response.parsed`, and `thoughts_token_count`; pin a tested 2.x range before the live benchmark rather than leaving `>=1.0` open-ended. `[VERIFIED: installed SDK introspection]` `[CITED: https://googleapis.github.io/python-genai/]` `[CITED: https://pypi.org/project/google-genai/]` |
| Gemini 2.5 Flash | Stable; earliest shutdown 2026-10-16; replacement `gemini-3.5-flash` | Low-cost frozen-corpus benchmark profile. `[CITED: https://ai.google.dev/gemini-api/docs/deprecations]` |
| Gemini 3.5 Flash | Stable since 2026-05-19; structured outputs, image/PDF input supported | Quality profile; exact same adapter contract. `[CITED: https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash]` |
| Docling | Repo runtime 2.91.0; PyPI current 2.108.0 | Keep Phase 2 behind persisted `DocumentPage` text/image DTOs; do not couple Gemini extraction to Docling's changing VLM runtime API. `[VERIFIED: local environment]` `[CITED: https://pypi.org/project/docling/]` |
| SQLite | Existing local database | Durable manifest, per-document states, idempotent history, and migration backfill. |
| pytest | Repo runtime 9.0.3 | Offline Nyquist gate; fake providers remain mandatory. `[VERIFIED: local environment]` |

### Model-keyed July 2026 standard pricing

| Exact model key | Input / 1M | Output + thinking / 1M | Lifecycle |
|-----------------|------------|------------------------|-----------|
| `gemini-2.5-flash` | $0.30 | $2.50 | Shutdown no earlier than 2026-10-16. `[CITED: https://ai.google.dev/gemini-api/docs/pricing]` |
| `gemini-3.5-flash` | $1.50 | $9.00 | No shutdown date announced. `[CITED: https://ai.google.dev/gemini-api/docs/pricing]` |

Use standard synchronous rates only; Batch/Flex/Priority rates are different products. Unknown or dynamic aliases return `None` unless the response exposes a recognized canonical `model_version`. Output cost is based on `candidates_token_count + thoughts_token_count`, because Google bills generated thoughts at the output rate. `[CITED: https://ai.google.dev/gemini-api/docs/generate-content/tokens]`

## Architecture Patterns

### End-to-end flow

```text
extract / extract-all
  -> create or resume durable run + immutable document manifest
  -> for each non-completed run document
       -> mark running / increment attempt
       -> Docling-derived persisted page DTOs
       -> Gemini request with strict response schema
       -> Pydantic revalidation
       -> exact page/span + packet-rule gates
       -> accepted field OR explicit abstention
       -> deterministic risk
       -> idempotent field/compliance history
       -> mark document completed OR failed (safe reason code only)
  -> aggregate once
       -> completed | partial | failed; interrupted remains running
  -> evaluation accepts only a complete, reproducible source run
```

### Pattern 1: Fixed-key response envelope

Use six required object properties instead of a list with `field_name`. A six-item list can still contain duplicates or omit one name; fixed keys plus `extra="forbid"` make exactly-six structural validity expressible in JSON Schema. Keep evidence compact (`page_num`, `verbatim_span`); bbox is not required by EXTRACT-01 and can remain null. Convert the validated mapping into existing `ProviderFieldPayload` DTOs. `[CITED: https://ai.google.dev/gemini-api/docs/generate-content/structured-output]`

```python
class ProviderEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page_num: int = Field(ge=0)
    verbatim_span: str = Field(min_length=1, max_length=500)

class ProviderField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    raw_value: str | None
    normalized_value: str | None
    normalized_date: date | None
    confidence: float = Field(ge=0, le=1)
    evidence: ProviderEvidence | None
    abstention_reason: str | None

class ProviderFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    doc_type: ProviderField
    vendor_name: ProviderField
    manufacturing_date: ProviderField
    effective_date: ProviderField
    revision_date: ProviderField
    expiry_date: ProviderField

class ProviderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: ProviderFields

config = {
    "response_mime_type": "application/json",
    "response_schema": ProviderResponse,
}
validated = ProviderResponse.model_validate_json(response.text)
```

Google explicitly says not to duplicate the schema in the prompt and to validate semantically after structured generation. Remove the hand-written `JSON schema:` prompt block but retain field definitions, packet exclusions, abstention policy, and 0-index page contract. `[CITED: https://googleapis.github.io/python-genai/]` `[CITED: https://ai.google.dev/gemini-api/docs/generate-content/structured-output]`

### Pattern 2: Durable run state machine

Add `extraction_run_documents(run_id, doc_id, status, attempt_count, trace_id, error_reason, started_at, completed_at, updated_at)` with a composite primary key. Extend `extraction_runs` additively with `expected_document_count`, `attempted_document_count`, `succeeded_document_count`, `failed_document_count`, `provider`, `requested_model`, `resolved_model`, `corpus_version`, and `manifest_hash`.

Run invariants:

- `completed`: all manifest documents completed and failed count is zero.
- `partial`: terminal batch with both successes and failures.
- `failed`: terminal batch with failures and no successes.
- `running`: nonterminal, including process interruption; `completed_at IS NULL`.
- Resuming the same run skips completed documents and retries pending/running/failed documents idempotently.
- Reusing a run ID with a different manifest, model, provider, or corpus version is rejected rather than merged.
- A batch without `--run-id` generates one shared run ID before iteration and prints it.

Create the run before the first provider call so provider failures can be counted and usage/status rows retain valid foreign keys. Finalize once, after the loop, from SQL aggregates rather than caller counters.

### Pattern 3: Ground, then compute risk

For text-bearing pages, require a literal substring and persist the actual slice from stored page text; case-folded or whitespace-normalized containment is not a verbatim citation. For text-empty scanned pages, the only allowed non-abstained path is an image-backed page claim forced to `needs_review`; otherwise abstain. Any low-confidence/visual date that influences a nominal green band must keep document compliance status at `needs_review`, never present an unverified document as simply compliant. `[VERIFIED: docs/field-definitions.md]`

Prompt rules are defense-in-depth, not enforcement. Keep deterministic local guards for Delivery Date and Retest Date, add packet-scope fixtures for email/SDS/handwritten dates, and prefer abstention whenever the primary certificate boundary cannot be proven.

### Pattern 4: One retry layer

The official Python SDK already applies bounded exponential retry for transient 429/5xx failures. Do not silently multiply those attempts with a second no-wait Tenacity loop. Either configure the SDK's `HttpRetryOptions` explicitly or disable its retries and retain one bounded jittered adapter loop; persist only attempt count/status and sanitized reason codes. `[CITED: https://ai.google.dev/gemini-api/docs/troubleshooting]` `[CITED: https://googleapis.github.io/python-genai/]`

Also remove the unconditional `temperature=0` for the shared 2.5/3.5 path. Google's current troubleshooting guidance warns that lowering temperature below the default for Gemini 3.x can degrade behavior; structured output and local validation, not temperature, provide the contract. `[CITED: https://ai.google.dev/gemini-api/docs/troubleshooting]`

## Migration Safety

1. Add the new run-document table in `SCHEMA_SQL`; add legacy run columns through a guarded `_migrate_extraction_runs_table`.
2. Backfill existing completed runs with `expected=attempted=succeeded=document_count`, `failed=0`; derive completed run-document rows from distinct history rows when available.
3. Put indexes that reference newly added legacy-table columns in `POST_MIGRATION_INDEX_SQL`, after `ALTER TABLE` calls.
4. Preserve all current rows and nullable semantics; no table drop/rebuild is needed.
5. Test a realistic pre-hardening database, initialization twice, and data/foreign-key/index preservation.
6. Keep latest-value tables backward compatible while all benchmark/eval reads use run-scoped history.

## Don't Hand-Roll

| Problem | Do not build | Use instead |
|---------|--------------|-------------|
| JSON format compliance | Regex/markdown fence repair as primary parsing | Gemini response schema + Pydantic `model_validate_json` |
| Date parsing contract | Guessing locale dates after acceptance | Schema ISO date plus preserved raw value; abstain/review ambiguity |
| Retry scheduler | Nested immediate retries | One SDK-configured or Tenacity exponential-jitter policy |
| Resume truth | Infer completion from console counts | Per-document durable state and SQL aggregate finalization |
| Pricing fallback | Apply the 2.5 rate to unknown names | Exact allowlisted model registry; unknown cost is null |
| Citation correctness | Fuzzy string similarity | Valid page plus literal stored span or review-forced visual tier |

## Common Pitfalls

1. **Schema-valid is not fact-valid.** Structured output guarantees shape, not correct values; retain all local evidence and packet gates. `[CITED: https://ai.google.dev/gemini-api/docs/generate-content/structured-output]`
2. **A list of six is not six unique fields.** Use fixed keys, not only `minItems=maxItems=6`.
3. **Thinking tokens are billable.** Ignoring `thoughts_token_count` understates both 2.5 and 3.5 extraction cost. `[CITED: https://ai.google.dev/gemini-api/docs/generate-content/tokens]`
4. **Requested aliases are not audit identities.** Record requested and response-resolved model separately; price only a recognized canonical key.
5. **Finalizing from each document lies.** Only the batch coordinator may set a terminal run status.
6. **Crash recovery is a normal state.** A stale `running` document is resume-eligible; never label the whole run complete because history contains one row.
7. **Migration index ordering matters.** `CREATE INDEX` on a missing legacy column fails before a later migration can add it.
8. **Docling runtime churn is not a Phase 2 boundary.** Consume persisted page DTOs; Docling's current API model catalog is OpenAI-compatible/preset-specific and is not the Google GenAI structured extraction API. `[CITED: https://docling-project.github.io/docling/usage/model_catalog/]`

## Runtime State Inventory

| Category | Items found | Action required |
|----------|-------------|-----------------|
| Stored data | Local SQLite DBs may already contain `extraction_runs` and history in the current schema. | Additive migration/backfill; preserve rows and current latest tables. |
| Live service config | Gemini key/model and Langfuse keys are environment-backed. | No secret rename; add model/profile metadata only. |
| OS-registered state | None found or required for Phase 2. | None. |
| Secrets/env vars | `GEMINI_API_KEY`, `GEMINI_MODEL`, Langfuse settings. | Never persist values; model ID is safe, key is not. |
| Build artifacts | Venv has google-genai 2.7.0 and Docling 2.91.0 while dependency ranges can resolve newer versions. | Freeze and record the benchmark environment; do not claim reproducibility from `>=` constraints alone. |

## Environment Availability

| Dependency | Available | Version | Phase 2 fallback |
|------------|-----------|---------|------------------|
| Python | Yes | 3.11.9 | None needed |
| pytest | Yes | 9.0.3 | None needed |
| Pydantic | Yes | 2.13.3 | None needed |
| google-genai | Yes | 2.7.0 | Fake clients for every offline test |
| Docling | Yes | 2.91.0 | Persisted page DTO seam; no live Docling needed in extraction tests |
| Gemini credentials/quota | Not required for planning/offline verification | Environment-dependent | Live benchmark is a separately recorded gate |

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 |
| Config | `pyproject.toml` and `pytest.ini` |
| Quick run | `venv/Scripts/python.exe -m pytest tests/test_extraction_provider_gemini.py tests/test_extraction_pipeline.py tests/test_extraction_risk.py -q` |
| Full Phase 2 run | `venv/Scripts/python.exe -m pytest tests/test_extraction_*.py tests/test_eval_db_schema.py -q` |
| Current evidence | 87 focused existing tests passed in 19.61s on 2026-07-11. |

### Requirements to test map

| Req/decision | Required automated behavior | File |
|--------------|-----------------------------|------|
| EXTRACT-01 / D-02-01 | Fake client receives strict fixed-six schema; missing/extra/type-invalid responses abstain; prompt contains no duplicate JSON schema. | `tests/test_extraction_provider_gemini.py` |
| D-02-02/03/04 | Literal span/page gate; raw + ISO date; N/A; email/SDS/delivery/retest/cross-packet abstentions; text-empty visual behavior. | `tests/test_extraction_pipeline.py`, new packet fixtures |
| EXTRACT-02 / D-02-05/06 | Calendar boundary table, expired precedence, unknown/review, no false-safe compliance from review-forced evidence. | `tests/test_extraction_risk.py` |
| D-02-07 | all-success/partial/all-failed/interrupted statuses; shared auto run; resume skip/retry; manifest mismatch; same-run idempotency. | `tests/test_extraction_cli.py`, `tests/test_extraction_persistence.py` |
| D-02-08 | Failure rows/traces contain identifiers, counts, model, tokens/cost only; forbidden corpus fragments absent. | `tests/test_extraction_usage_observations.py` |
| D-02-09/10/11 | 2.5 and 3.5 config; lifecycle docs; exact current rates; thought tokens; unknown model null; resolved model; retry bound. | `tests/test_extraction_gemini_usage.py` |
| Migration | Legacy current-schema DB upgrades twice, backfills safely, preserves history/FKs/indexes. | `tests/test_extraction_schema.py`, `tests/test_extraction_run_history_schema.py` |
| Eval integration | Nonterminal/partial source run is refused; complete run includes model/date/corpus/run/usage provenance. | `tests/test_extraction_eval_runner.py` |

### Sampling rate

- **Per task:** the directly affected test file(s), under 30 seconds.
- **Per wave:** full Phase 2 command above.
- **Phase gate:** full repository suite plus one paid live frozen-corpus smoke run recording model, SDK version, date, corpus version, run ID, usage, terminal status, and sanitized failures.

### Wave 0 gaps

- [ ] Strict provider-envelope schema fixtures and schema-shape assertions.
- [ ] Per-document run-state/manifest migration fixture based on today's schema.
- [ ] Partial/interrupted/resume CLI scenarios.
- [ ] July 2026 2.5/3.5 price and thinking-token fixtures.
- [ ] Exact-verbatim, cross-packet, and scanned-page grounding fixtures.
- [ ] Eval refusal of non-complete extraction runs.

## Security Domain

| Threat | STRIDE | Control |
|--------|--------|---------|
| Prompt/document content leaks through errors or traces | Information disclosure | Existing allowlists plus forbidden-fragment tests; reason codes only. |
| Provider injects fields/extra keys/invalid page | Tampering | `extra="forbid"`, fixed keys, Pydantic revalidation, local page/span gates. |
| SQL injection through IDs/values | Tampering | Preserve parameterized SQL exclusively. |
| Run ID reused for another corpus/model | Spoofing/repudiation | Immutable manifest hash + provider/model/corpus identity check. |
| Retry storm or huge schema/output | Denial of service | One bounded retry layer, compact schema, bounded span/output length. |
| Secret persisted in provider payload/error | Information disclosure | Never store raw payload/message/key/path; sanitize at boundary. |

## Assumptions Log

No unverified external claims are required for planning. The product-specific compliance thresholds and field semantics are locked project decisions, not regulatory claims.

## Open Questions

None blocks planning. The only manual gate is the later paid live frozen-corpus run; offline implementation and verification can complete without credentials.

## Sources

### Primary official sources (HIGH confidence)

- Google structured outputs (Generate Content), updated 2026-06-23: https://ai.google.dev/gemini-api/docs/generate-content/structured-output
- Google Gen AI Python SDK (`response_schema`, Pydantic, parsed responses, retry/types): https://googleapis.github.io/python-genai/
- Google Gemini pricing (July 2026 current): https://ai.google.dev/gemini-api/docs/pricing
- Google Gemini deprecation schedule: https://ai.google.dev/gemini-api/docs/deprecations
- Google token counting/thinking billing: https://ai.google.dev/gemini-api/docs/generate-content/tokens
- Google Gemini troubleshooting/retry guidance: https://ai.google.dev/gemini-api/docs/troubleshooting
- Google Gemini 3.5 Flash model card: https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash
- Google Gen AI SDK registry: https://pypi.org/project/google-genai/
- Docling model/runtime catalog: https://docling-project.github.io/docling/usage/model_catalog/
- Docling VLM API runtime example: https://docling-project.github.io/docling/_generated/examples/vlm_pipeline_api_model/
- Docling pipeline/OCR options: https://docling-project.github.io/docling/reference/pipeline_options/
- Docling registry: https://pypi.org/project/docling/

## Project Constraints (from AGENTS.md)

- Python 3.11+, Docling, Google GenAI, Pydantic, SQLite, Streamlit, Langfuse, and the rest of the locked stack remain in place.
- Provider/API imports stay lazy and offline-safe; tests cannot require credentials or network access.
- Logs/traces exclude document contents, provider payloads, filesystem paths, and secrets.
- SQLite uses parameterized SQL and idempotent migrations.
- Windows verification uses `venv/Scripts/python.exe -m pytest`; never `/bin/bash`.
- Source edits must occur through the parent GSD execution workflow; this research makes no source change and no commit.

## Metadata

**Confidence breakdown:**
- Provider schema/model lifecycle/pricing: HIGH — official Google docs current through late June/July 2026 plus installed SDK introspection.
- Run/migration architecture: HIGH — derived directly from current schema/repository/CLI behavior and offline tests.
- Grounding/risk architecture: HIGH — derived from locked context, canonical field rules, and current code.
- Docling boundary: HIGH — official current Docling catalog/options plus persisted DTO inspection.

**Research date:** 2026-07-11
**Valid until:** 2026-08-10 for implementation patterns; re-check pricing and deprecations immediately before any published benchmark.
