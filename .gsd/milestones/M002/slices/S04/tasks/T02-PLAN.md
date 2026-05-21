---
estimated_steps: 17
estimated_files: 3
skills_used: []
---

# T02: Wire Chat tab into app entrypoint

---
estimated_steps: 5
estimated_files: 3
skills_used:
  - verify-before-complete
---

Why: S04 is only user-visible when the existing Streamlit app delegates the Chat tab to the new renderer. This task replaces the placeholder with real composition while preserving existing Compliance, Eval, and Langfuse sidebar behavior.

Do:
1. Export `render_chat_tab` from `src/dashboard/__init__.py` without removing existing compliance exports.
2. Update `src/app.py` to import `render_chat_tab` and call `render_chat_tab(get_settings().db_path)` inside the Chat tab.
3. Keep `st.set_page_config` as the first Streamlit call and keep the Langfuse session-state guard unchanged.
4. If the existing smoke test needs adjustment, update `tests/test_app.py` only to reflect the real Chat tab import/startup path; do not make the app import secret-dependent.
5. Run focused app and dashboard tests.

Done when: Streamlit app startup succeeds headlessly, the Chat tab no longer shows only placeholder copy, and app import/startup still requires no Gemini key.

Threat Surface Q3: App wiring must not broaden secret exposure; Gemini credentials remain environment-only and must not be read or logged at import time.

Failure Modes Q5: A missing Gemini key, missing index, or retrieval setup problem must be contained to the Chat tab renderer and must not crash the Streamlit process or unrelated tabs.

Negative Tests Q7: Startup with no Gemini key and no retrieval index should still render the app shell and actionable Chat setup state.

## Inputs

- `src/app.py`
- `src/dashboard/__init__.py`
- `src/dashboard/compliance.py`
- `src/dashboard/chat.py`
- `tests/test_chat_dashboard.py`
- `tests/test_app.py`
- `tests/test_compliance_dashboard.py`

## Expected Output

- `src/app.py`
- `src/dashboard/__init__.py`

## Verification

venv/Scripts/python.exe -m pytest tests/test_chat_dashboard.py tests/test_app.py tests/test_compliance_dashboard.py

## Observability Impact

Makes the bounded Chat diagnostics reachable from the real Streamlit entrypoint while preserving existing Langfuse connection status behavior.
