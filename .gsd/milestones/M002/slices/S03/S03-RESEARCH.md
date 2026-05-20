# S03 Research: Grounded Answer Service and Provider Seam

## Summary

S03 should add a new service layer between the S02 evidence gate and future S04 Streamlit Chat UI. The codebase already has the critical lower boundary: `src.retrieval.retrieve_evidence()` returns deterministic strong/weak evidence, exposes only bounded snippets, and withholds hits for weak evidence. The missing layer is answer orchestration: provider-neutral DTOs/protocols, an answer service that refuses weak evidence before generation, a fake provider test path, and a lazy Gemini implementation with sanitized failures.

Recommended shape: create a small `src/rag/` (or `src/answering/`) package with `models.py`, `providers.py`, `service.py`, `gemini.py`, and `__init__.py`. Keep citations assembled by the service from `RetrievalHit` objects, not trusted from model output. The provider should generate answer text from bounded snippets only; the service should attach filename/page/snippet citations and return abstention/provider-error results safely.

## Active Requirements and Constraints

- **R005**: S03 owns the first answer-level grounded Q&A contract. It should prove corpus-backed answer and off-topic abstention through one service API, but full Chat UX waits for S04.
- **R008**: Support structured diagnostics: answer status/reason, evidence reason, run id, top score, provider name, trace id, citation count. Do not include raw full page text or provider responses.
- **R009**: Verification must use `venv/Scripts/python.exe`; prior S02 verification used this path.
- **R010**: Gemini credentials and provider settings remain environment-only. Imports and default tests must not require secrets/network. Error messages must not expose API keys, raw provider output, full snippets beyond already bounded evidence, image blobs, or full content hashes.

## Existing Code and Purpose

### Retrieval boundary already available

- `src/retrieval/models.py`
  - Defines `RetrievalEvidenceReason`, `RetrievalHit`, `EvidenceGateResult`/`RetrievalResult`.
  - Public results expose only bounded snippets and hash prefixes; no raw page text.
- `src/retrieval/retriever.py`
  - `retrieve_evidence(db_path, question, top_k=..., min_top_score=...)` is the stable S03 input.
  - Weak results have `hits == ()`, so downstream services cannot fabricate citations unless they deliberately bypass the contract.
  - Useful reason codes: `empty_question`, `index_missing`, `index_empty`, `index_stale`, `no_match`, `below_threshold`, `retrieval_error`.
- `src/retrieval/__init__.py`
  - Exports the public S02 contract. It intentionally does not export helper internals like FTS/snippet functions.

### Provider pattern to mirror

- `src/extraction/providers.py`
  - Small provider `Protocol` + typed provider result DTOs.
  - Typed errors: configuration, provider, validation.
- `src/extraction/gemini.py`
  - Lazy/offline-safe module import; credentials are required only when constructing a live provider without injected client.
  - Uses `google-genai` client shape: `client.models.generate_content(model=..., contents=..., config={...})`.
  - Sanitizes provider failures by including provider/model/run/doc/error class only; never raw response, page text, or secret.
  - Tests inject `FakeGeminiClient` instead of network.
- `src/extraction/cli.py`
  - `build_provider()` is a useful seam for monkeypatching fake providers.
  - `_safe_error_message()` pattern emits reason codes and safe identifiers only.
- `src/extraction/pipeline.py`
  - Good precedent for service-level validation after untrusted provider output. For S03, analogous validation should be simpler: nonempty generated text + provider failure handling; citations come from retriever, not provider.

### Config and observability

- `src/config.py`
  - Existing `gemini_api_key` and `gemini_model` can be reused for S03, though the field description currently says extraction provider. Optional future cleanup: broaden description to “Gemini model for live AI providers”.
- `src/tracing.py`
  - Langfuse v3 is pinned and non-fatal. Do not make S03 imports depend on Langfuse. If adding tracing now, guard it like `src/pipeline/ingest.py` fallback style or keep diagnostics DTO-only until S05.

### Tests/fixtures to reuse

- `tests/test_retriever.py`
  - Has helper pattern for seeding docs/pages and building retrieval index.
  - Covers strong evidence, off-topic no-match, stale/missing/empty indexes, and no full page text in DTO repr.
- `tests/test_extraction_provider_gemini.py`
  - Best template for fake Gemini client, mocked responses, missing key test, malformed output, retry/sanitization test.
- `tests/test_extraction_cli.py`
  - Best template for monkeypatched provider seam and safe output assertions.
- `tests/test_s05_end_to_end_proof.py`
  - Future S05 can extend this realistic ingest/extract proof; S03 probably should keep to SQLite fixture pages rather than Docling ingestion.

## What Is Missing

- No answer/RAG package exists (`rg` found no existing `rag`, `answer`, or citation service beyond retrieval DTOs).
- No answer provider protocol exists.
- No Gemini answer provider exists; only extraction-specific Gemini provider.
- No public answer result/citation DTO exists for S04 to render.
- No service API currently maps `RetrievalEvidenceReason` to user-facing abstention outcomes.

## Recommended Interface

Use service-owned citations and provider-generated prose:

```python
@dataclass(frozen=True)
class AnswerCitation:
    doc_id: str
    filename: str
    page_num: int          # persisted 0-indexed page
    display_page_num: int  # UI citation page, 1-indexed
    snippet: str
    score: float

class AnswerStatus(StrEnum):
    ANSWERED = "answered"
    ABSTAINED = "abstained"
    PROVIDER_ERROR = "provider_error"

@dataclass(frozen=True)
class AnswerResult:
    status: AnswerStatus
    answer: str
    citations: tuple[AnswerCitation, ...]
    evidence: EvidenceGateResult
    diagnostics: AnswerDiagnostics
    abstention_reason: str | None = None
```

Provider seam:

```python
@dataclass(frozen=True)
class AnswerProviderRequest:
    question: str
    evidence_hits: tuple[RetrievalHit, ...]
    run_id: str

@dataclass(frozen=True)
class AnswerProviderResult:
    answer_text: str
    trace_id: str | None = None
    provider_name: str | None = None

class AnswerProvider(Protocol):
    def generate_answer(self, request: AnswerProviderRequest) -> AnswerProviderResult: ...
```

Service API:

```python
def answer_question(
    db_path: str,
    question: str,
    provider: AnswerProvider,
    *,
    top_k: int = 5,
    run_id: str | None = None,
) -> AnswerResult: ...
```

Important contract choices:

1. Call `retrieve_evidence()` first.
2. If `evidence.is_strong is False`, return `ABSTAINED`, `citations=()`, no provider call.
3. If strong, pass only `question` and bounded `evidence.hits` to provider.
4. If provider returns blank/malformed text or raises, return `PROVIDER_ERROR` (or raise typed `AnswerProviderError`; planner should choose one consistent surface for S04). Prefer returning a safe result so Streamlit can render without crashing.
5. Citations are derived exclusively from evidence hits and attached after provider generation.
6. Public diagnostics include provider name/trace id/run id/evidence reason/top score/citation count, but not raw model response or full page text.

## Natural Seams / Work Units

1. **Answer DTOs and provider protocol**
   - Files: `src/rag/models.py`, `src/rag/providers.py`, `src/rag/__init__.py`.
   - Independent from Gemini SDK.
   - Add tests for DTO repr/diagnostics sanitization if DTOs include bounded fields.

2. **Grounded answer service**
   - File: `src/rag/service.py`.
   - Consumes `retrieve_evidence()` from S02.
   - Adds fake-provider tests proving: strong evidence calls provider and returns citations; weak/off-topic/missing index does not call provider and abstains; provider exception or blank answer is safe/sanitized.
   - This is the highest-risk first proof because it enforces the no-hallucination boundary before any live provider variability.

3. **Gemini answer provider**
   - File: `src/rag/gemini.py`.
   - Mirror `src/extraction/gemini.py` import/credential/client-injection pattern.
   - Use temperature 0 and a prompt that instructs: answer only from supplied evidence snippets, be concise, do not invent, no markdown table required.
   - Tests should inject `FakeGeminiClient`; no network/secrets.
   - Failures should raise/return typed sanitized provider errors that include provider/model/run/error_class only.

4. **Package exports and builder seam**
   - File: `src/rag/__init__.py`; optional `build_answer_provider()` in `src/rag/providers.py` or `src/rag/service.py`.
   - Export only stable DTO/protocol/service/Gemini classes, not prompt helper internals.
   - S04 can later use `build_answer_provider("gemini")` or direct `GeminiAnswerProvider()`.

5. **Optional diagnostics/tracing hook**
   - Keep to DTO diagnostics in S03 unless time permits.
   - If adding Langfuse spans, use non-fatal guarded imports. Do not make `src.rag` import fail if Langfuse is unavailable.

## First Proof

Implement and verify the service with a fake provider before writing Gemini:

- Seed SQLite pages using the same patterns as `tests/test_retriever.py`.
- Build retrieval index.
- Ask `"Acme supplier compliance approval"` through `answer_question()`.
- Assert:
  - `status == ANSWERED`.
  - Fake provider was called exactly once with bounded hits.
  - Answer text equals fake provider output.
  - Citations include filename, display page 1, score, and snippet containing known span.
  - No raw full page tail appears in `repr(result)`.
- Ask unrelated/off-topic question.
- Assert:
  - `status == ABSTAINED`.
  - Provider was not called.
  - `citations == ()`.
  - `evidence.reason_code` is `NO_MATCH` or `BELOW_THRESHOLD` depending fixture.

This proof blocks hallucination most directly and gives S04 a stable service API.

## Gemini Provider Notes

Existing dependency `google-genai>=1.0` is already in `pyproject.toml`, and extraction code already uses the SDK. S03 can reuse that client-call style. The answer provider should be offline-safe at import and fake-client-testable. Suggested implementation details:

- `DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"` or import/reuse a common constant if refactored.
- Constructor parameters: `api_key=None`, `model=None`, `client=None`, `client_factory=None`, `max_attempts=2`.
- If no client/client_factory and no key, raise `AnswerConfigurationError("GEMINI_API_KEY is required to use the Gemini answer provider.")`.
- `generate_answer()` catches arbitrary SDK exceptions and raises `AnswerProviderError` with sanitized message.
- Parse `response.text` as plain text, strip markdown fences only if needed, reject blank text.
- Do not ask Gemini to emit citations as authoritative data. The service owns citation rendering from `RetrievalHit`.

## Skill Discovery

Installed skills directly relevant:

- `observability`: relevant for R008. Rule to apply: agent-first observability should expose structured logs/diagnostics and explicit failure modes without leaking sensitive payloads. S03 should prefer bounded diagnostics fields over raw provider/page content.
- `api-design` / `design-an-interface`: relevant conceptually for public service shape, but this is internal Python service API, not HTTP.

External skills found but not installed:

- Gemini / google-genai:
  - `npx skills add google-gemini/gemini-skills@gemini-api-dev` (12.5K installs; broad Gemini API skill)
  - `npx skills add cnemri/google-genai-skills@google-genai-sdk-python` (83 installs; Python SDK-specific)
- Langfuse:
  - `npx skills add sickn33/antigravity-awesome-skills@langfuse` (495 installs)
  - `npx skills add davila7/claude-code-templates@langfuse` (288 installs)

Do not install by default; existing local Langfuse/Gemini patterns are likely sufficient for S03.

## Verification Plan

Run focused S03 tests plus S02 regressions through Python 3.11 venv:

```bash
venv/Scripts/python.exe -m pytest tests/test_answer_service.py tests/test_answer_provider_gemini.py tests/test_retriever.py
```

If package exports are added, include import contract tests in `tests/test_answer_service.py` or a dedicated package test. If Gemini code touches shared config/error classes, include extraction provider regressions:

```bash
venv/Scripts/python.exe -m pytest tests/test_answer_service.py tests/test_answer_provider_gemini.py tests/test_extraction_provider_gemini.py tests/test_retriever.py
```

Expected assertions:

- Strong evidence path returns concise fake-provider answer plus service-owned citations.
- Weak/off-topic/missing/empty/stale evidence abstains and never calls provider.
- Provider failure/blank output returns or raises safe typed failure without raw provider response, page text, secrets, image blobs, or full content hash.
- Gemini provider import requires no credentials; missing key only fails on construction; fake client tests do not use network.
- Public exports expose stable service/DTO surfaces and not prompt/helper internals.

## Watch-outs for Planner

- Avoid putting answer logic in `src/app.py`; S04 should call the service, not own retrieval/generation rules.
- Avoid trusting provider-cited sources. Provider output is untrusted prose only; service citations must come from S02 evidence hits.
- Avoid returning weak `RetrievalHit` candidates. S02 intentionally returns no hits for weak evidence; preserve this invariant.
- Avoid logging or repr-exposing prompt contents if prompts include snippets. The snippets are bounded but still document content; diagnostics should use counts/IDs/reason codes.
- Decide whether provider errors are returned as `AnswerResult(status=PROVIDER_ERROR)` or raised as typed errors. For Streamlit S04, a result object is easier to render; for tests, either is fine if consistent and sanitized.
- Keep all page numbers for display as `display_page_num`; persisted `page_num` remains 0-indexed.

## Research Sources / Commands

- Memory query: `Grounded Answer Service Provider Seam retrieval RAG Gemini provider` surfaced provider laziness, S02 contract, and M002 architecture memories.
- Code inventory: `gsd_exec 8f7bb0c3-c82e-4183-92be-cc5ef02d9b1b`.
- Provider/reference scan: `gsd_exec ddfad7fe-3030-4954-9015-3da244f4b16c`.
- Answer/RAG absence scan: `gsd_exec 12c8048e-c6c7-4a67-b3e2-277d0be5bcf2`.
- Skill discovery: `gsd_exec 8c38e716-0e44-45eb-9a64-b26008a7aa61`.
