---
estimated_steps: 7
estimated_files: 2
skills_used: []
---

# T01: Add shared safe trace helper

Expected executor skills: observability, tdd, verify-before-complete.

Why: The project already has multiple local Langfuse update patterns, and ingestion/storage still call langfuse_context directly. R008 needs one hardened, testable boundary for optional Langfuse, compact metadata allowlisting, bounded values, and no-op behavior.

Do: In src/tracing.py, add a Langfuse v3-compatible no-op-safe helper such as safe_update_current_trace plus any small helpers needed for filtering and value bounding. Keep v3 import paths compatible with existing tests and project dependency pin. The helper must accept tags, metadata, and an explicit allowed key set; drop all non-allowed keys; catch missing context, import/auth/backend failures, and update exceptions; return a boolean or otherwise expose no-op status without raising. Add tests in tests/test_tracing.py using a fake context that verifies only allowlisted metadata is sent, forbidden keys and forbidden values are absent from repr(metadata), long strings are bounded, and a raising fake context does not raise to callers.

Failure Modes (Q5): Missing langfuse install, missing keys, auth failure, context unavailable, or backend update exception must result in no-op behavior. Malformed metadata values must be converted only when safely representable or dropped, never logged raw.

Load Profile (Q6): Per operation cost is a small in-memory filter and at most one Langfuse context update. At 10x ingestion/eval volume, the helper should not perform network calls beyond the Langfuse SDK update already requested by the decorated span.

Negative Tests (Q7): Include disallowed metadata keys, secret-looking values, oversized strings, no context, and raising context.

Done when: src/tracing.py exposes the shared helper; tests prove allowlist filtering, no-op behavior, and v3 compatibility without changing existing verify_langfuse_connection semantics.

## Inputs

- `src/tracing.py`
- `tests/test_tracing.py`

## Expected Output

- `src/tracing.py`
- `tests/test_tracing.py`

## Verification

venv/Scripts/python.exe -m pytest -q tests/test_tracing.py

## Observability Impact

Establishes the reusable redaction and no-op primitive used by all later S07 trace wiring.
