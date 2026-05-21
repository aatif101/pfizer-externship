---
estimated_steps: 18
estimated_files: 5
skills_used: []
---

# T03: Run S04 regression proof

---
estimated_steps: 4
estimated_files: 1
skills_used:
  - test
  - verify-before-complete
---

Why: S04 composes UI, retrieval, answer service, and provider seams, so completion needs a regression proof that the new Chat renderer did not break the S03 service contract, S02 retriever behavior, retrieval CLI, Gemini seam, or existing Compliance dashboard.

Do:
1. Run the broader S04 verification command with the Python 3.11 project venv.
2. If failures are caused by this slice, make the smallest correction in the relevant touched file or test and rerun the same command.
3. Confirm tests do not rely on `.gsd/`, `.planning/`, `.audits/`, live Gemini credentials, or network access.
4. Record completion evidence in the eventual task/slice summary only after fresh passing output is produced.

Done when: The full listed pytest command passes and proves the CLI-adjacent retrieval surfaces, RAG service contract, Chat rendering path, app startup, and existing dashboard behavior together.

Requirement Impact Q4: Re-verifies R005 grounded Q&A loop, R008 bounded diagnostics/redaction, R009 venv command path, and R010 environment-only lazy credentials.

Failure Modes Q5: Any regression in missing/stale index, weak evidence, provider failure, app startup, or dashboard empty state should be visible as a focused test failure before completion.

Load Profile Q6: The regression suite should remain offline and fixture-sized; if test runtime grows unexpectedly, isolate expensive setup and avoid repeated provider/retrieval work on Streamlit reruns.

Negative Tests Q7: The suite must retain negative coverage for off-topic abstention, provider exceptions, missing credentials, stale or missing index states, and no raw secret/full text leakage.

## Inputs

- `src/dashboard/chat.py`
- `src/app.py`
- `src/dashboard/__init__.py`
- `tests/test_chat_dashboard.py`
- `tests/test_app.py`
- `tests/test_answer_service.py`
- `tests/test_answer_provider_gemini.py`
- `tests/test_rag_contract.py`
- `tests/test_retriever.py`
- `tests/test_retrieval_cli.py`
- `tests/test_compliance_dashboard.py`

## Expected Output

- `src/dashboard/chat.py`
- `src/app.py`
- `src/dashboard/__init__.py`
- `tests/test_chat_dashboard.py`
- `tests/test_app.py`

## Verification

venv/Scripts/python.exe -m pytest tests/test_chat_dashboard.py tests/test_app.py tests/test_answer_service.py tests/test_answer_provider_gemini.py tests/test_rag_contract.py tests/test_retriever.py tests/test_retrieval_cli.py tests/test_compliance_dashboard.py

## Observability Impact

Provides final S04 confidence that failure-path diagnostics and redaction behavior remain observable and bounded across UI, service, provider, retriever, and existing dashboard tests.
