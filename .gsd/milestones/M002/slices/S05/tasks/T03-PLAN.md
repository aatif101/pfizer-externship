---
estimated_steps: 9
estimated_files: 15
skills_used: []
---

# T03: Run final M002 operational regression

Expected executor skills: test, verify-before-complete.

Why: S05 is the final assembly slice; it must close with fresh evidence that the CLI, retrieval, RAG service, Gemini seam, Chat renderer, app startup, and tracing hooks work together after T01 and T02.

Do: Run the full M002 deterministic regression command from the project virtual environment. If failures are real regressions in files touched by T01 or T02, fix them in the appropriate touched file and rerun the focused and full commands. Do not introduce live Gemini, live Langfuse auth, browser, network, GPU, or `.gsd`/gitignored-file dependencies into tests. Confirm the test suite contains executable assertions for indexing, retrieval, answer generation, Chat rendering, abstention, provider failure, tracing metadata, and redaction. Capture the final command, exit code, and pass/fail counts in the task completion summary.

Threat Surface Q3: the regression suite validates the externally visible demo boundary and redaction surface rather than adding a new runtime exposure.
Requirement Impact Q4: final re-verification for R005, R008, and R010 across the assembled milestone.
Failure Modes Q5: any remaining missing index, stale index, empty corpus, weak evidence, provider config, provider runtime, and trace hook failures must be visible as typed statuses or bounded diagnostics.
Load Profile Q6: pytest runtime should remain local and deterministic; if runtime grows unexpectedly, split slow/non-deterministic checks rather than depending on live services.
Negative Tests Q7: verify existing and new tests include weak/off-topic question, no provider call on weak evidence, provider exception/configuration error, trace context failure/no-op, and forbidden-string redaction.

Done when: The full regression command passes freshly and proves the S05 success criteria with no live secrets.

## Inputs

- `tests/test_s05_end_to_end_proof.py`
- `tests/test_retrieval_cli.py`
- `tests/test_retriever.py`
- `tests/test_answer_service.py`
- `tests/test_answer_provider_gemini.py`
- `tests/test_rag_contract.py`
- `tests/test_chat_dashboard.py`
- `tests/test_app.py`
- `tests/test_tracing.py`
- `src/retrieval/indexer.py`
- `src/retrieval/retriever.py`
- `src/rag/service.py`
- `src/dashboard/chat.py`
- `src/app.py`
- `pyproject.toml`

## Expected Output

- Update the implementation and proof artifacts needed for this task.

## Verification

venv/Scripts/python.exe -m pytest tests/test_s05_end_to_end_proof.py tests/test_retrieval_cli.py tests/test_retriever.py tests/test_answer_service.py tests/test_answer_provider_gemini.py tests/test_rag_contract.py tests/test_chat_dashboard.py tests/test_app.py tests/test_tracing.py

## Observability Impact

Produces the final fresh verification evidence for operational readiness; no new runtime signal is added by this pure verification task.
