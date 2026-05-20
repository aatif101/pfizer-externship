---
estimated_steps: 12
estimated_files: 5
skills_used: []
---

# T01: Implement service-owned cited answer contract

---
skills_used:
  - tdd
  - observability
  - verify-before-complete
---
Why: S03 needs the no-hallucination answer boundary before any live provider variability. The service must make the deterministic S02 evidence gate authoritative, attach citations itself, and expose enough diagnostics for S04/S05 without leaking raw corpus content.

Do: Create `src/rag` package modules for answer DTOs, provider protocol/errors, and `answer_question()`. Define statuses such as answered/abstained/provider_error, service-owned `AnswerCitation`, `AnswerDiagnostics`, `AnswerProviderRequest`, and `AnswerProviderResult`. Call `retrieve_evidence()` first. If evidence is weak, return abstained with `citations=()` and do not call the provider. If evidence is strong, pass only bounded `RetrievalHit` snippets and question/run_id to the provider, then attach citations derived exclusively from those hits. Catch typed or arbitrary provider failures and blank answer text as safe provider_error results with redacted diagnostics. Keep raw page text, provider raw responses, secrets, image blobs, and full hashes out of public DTO fields and repr-sensitive strings.

Failure Modes (Q5): missing/empty/stale indexes and empty questions map to abstained results; provider exceptions or blank text map to provider_error; malformed provider result is treated as provider_error; retrieval exceptions should be represented by S02 retrieval_error evidence or a safe provider-free abstention/result without crashing callers.

Load Profile (Q6): one retrieval operation per question plus one provider call only for strong evidence; shared resource is SQLite; 10x load first stresses DB reads/provider rate limits, so the service must avoid provider calls for weak evidence and keep top_k bounded.

Negative Tests (Q7): blank/stopword questions, missing index, stale index, off-topic no_match/below_threshold, provider exception, blank provider answer, top_k citation bounding, and secret/raw text redaction in repr/diagnostics.

Done when: fake-provider tests prove strong answer, abstention without provider calls, safe provider_error, citation ownership, run_id/diagnostics propagation, and no raw full page tail exposure.

## Inputs

- `src/retrieval/models.py`
- `src/retrieval/retriever.py`
- `src/retrieval/__init__.py`
- `src/extraction/providers.py`
- `tests/test_retriever.py`
- `tests/conftest.py`

## Expected Output

- `src/rag/__init__.py`
- `src/rag/models.py`
- `src/rag/providers.py`
- `src/rag/service.py`
- `tests/test_answer_service.py`

## Verification

venv/Scripts/python.exe -m pytest tests/test_answer_service.py tests/test_retriever.py

## Observability Impact

Introduces answer-level diagnostics with status/reason/run_id/provider/trace/citation_count/top_score fields and explicit redaction constraints, giving future agents a safe failure surface to inspect without reading raw corpus/provider payloads.
