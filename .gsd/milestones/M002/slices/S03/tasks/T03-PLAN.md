---
estimated_steps: 10
estimated_files: 4
skills_used: []
---

# T03: Lock rag package contract and slice regression proof

---
skills_used:
  - tdd
  - verify-before-complete
---
Why: S04 should consume a stable service API without relying on internals, and S03 closeout must prove the new package did not regress S02 retrieval or extraction provider behavior.

Do: Add package-level contract tests for `src.rag` exports and import safety. Assert stable public exports include answer DTOs, provider protocol/errors, `answer_question`, `build_answer_provider` if implemented, and `GeminiAnswerProvider`; assert prompt helpers/private parser functions are not exported. Add regression assertions that importing `src.rag` and `src.rag.gemini` with no environment credentials is safe, and that answer result diagnostics remain bounded. Run the full S03 closeout command and adjust only the new rag package/tests if contract mismatches appear.

Failure Modes (Q5): accidental eager Gemini construction/import breaks offline tests; accidental helper exports couple S04 to internals; regression in S02 evidence semantics can permit fabricated citations; regression in extraction provider errors can leak raw provider data.

Negative Tests (Q7): no credentials in environment, no helper internals in `__all__`, weak evidence with no hits, provider_error with no citations, and regression tests for retriever/extraction provider suites.

Done when: the full closeout command passes through `venv/Scripts/python.exe` and no S03 tests require .gsd/.planning/.audits paths, live secrets, network, or gitignored artifacts.

## Inputs

- `src/rag/__init__.py`
- `src/rag/models.py`
- `src/rag/providers.py`
- `src/rag/service.py`
- `src/rag/gemini.py`
- `tests/test_answer_service.py`
- `tests/test_answer_provider_gemini.py`
- `tests/test_retriever.py`
- `tests/test_extraction_provider_gemini.py`

## Expected Output

- `tests/test_rag_contract.py`
- `tests/test_answer_service.py`
- `tests/test_answer_provider_gemini.py`
- `src/rag/__init__.py`

## Verification

venv/Scripts/python.exe -m pytest tests/test_answer_service.py tests/test_answer_provider_gemini.py tests/test_rag_contract.py tests/test_retriever.py tests/test_extraction_provider_gemini.py

## Observability Impact

Confirms the observable package boundary is stable and credential-free, and that diagnostic surfaces remain bounded under full slice regression verification.
