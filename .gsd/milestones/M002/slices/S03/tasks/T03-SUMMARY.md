---
id: T03
parent: S03
milestone: M002
key_files:
  - tests/test_rag_contract.py
key_decisions:
  - Locked `src.rag.__all__` as the supported S04-facing API and kept Gemini prompt/parser helpers private.
  - Validated answer diagnostics via the public package API rather than internal helper functions.
duration: 
verification_result: passed
completed_at: 2026-05-20T23:05:52.627Z
blocker_discovered: false
---

# T03: Added rag package contract tests that lock public exports, offline import safety, hidden internals, and bounded answer diagnostics.

**Added rag package contract tests that lock public exports, offline import safety, hidden internals, and bounded answer diagnostics.**

## What Happened

Created `tests/test_rag_contract.py` to exercise the package-level `src.rag` API as the stable downstream contract for S04. The tests assert the exact public export set for answer DTOs, provider protocol/errors, `answer_question`, `build_answer_provider`, and `GeminiAnswerProvider`; assert prompt helpers and private parser/service helpers are not exported; verify `src.rag`, `src.rag.gemini`, and `src.rag.providers` import safely with no Gemini credentials; and prove weak-evidence, provider-error, and retrieval-error diagnostics remain bounded without provider calls, fabricated citations, full hashes, raw page tails, or raw exception payloads. No production code changes were needed because the existing rag boundary already matched the intended contract.

## Verification

Ran the full S03 closeout command through `venv/Scripts/python.exe`; all answer service, Gemini answer provider, rag contract, retriever, and Gemini extraction provider regression tests passed. Also ran a static check confirming `tests/test_rag_contract.py` does not reference `.gsd`, `.planning`, or `.audits` artifact paths.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `venv/Scripts/python.exe -m pytest tests/test_answer_service.py tests/test_answer_provider_gemini.py tests/test_rag_contract.py tests/test_retriever.py tests/test_extraction_provider_gemini.py` | 0 | ✅ pass — 51 passed in 5.19s | 6750ms |
| 2 | `venv/Scripts/python.exe - <<'PY'
from pathlib import Path
p=Path('tests/test_rag_contract.py')
text=p.read_text()
forbidden=['.gsd/', '.gsd\\\\', '.planning/', '.planning\\\\', '.audits/', '.audits\\\\']
found=[token for token in forbidden if token in text]
print(f'forbidden_path_tokens={found}')
raise SystemExit(1 if found else 0)
PY` | 0 | ✅ pass — forbidden_path_tokens=[] | 183ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `tests/test_rag_contract.py`
