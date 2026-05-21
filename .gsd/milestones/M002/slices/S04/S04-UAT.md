# S04: Streamlit Chat User Loop — UAT

**Milestone:** M002
**Written:** 2026-05-20T23:31:58.223Z

## UAT Type

Deterministic local UI/service acceptance using the Streamlit Chat tab with fixture SQLite/index state and fake/offline provider seams. No live Gemini credentials are required.

## Preconditions

1. Run from the project root on Windows.
2. Use the project Python 3.11 virtual environment: `venv/Scripts/python.exe`.
3. A fixture or local SQLite document store has been indexed by the M002 retrieval CLI, or tests use the existing fixture-backed service path.
4. Do not set live provider credentials for this UAT unless intentionally testing the live Gemini path.

## Steps and Expected Outcomes

1. Start the Streamlit app entrypoint and open the Chat tab.
   - Expected: The app imports and starts without constructing Gemini at import time, without requiring provider credentials, and without breaking the Compliance tab.
2. Ask a supplier-document question that is supported by the indexed corpus, such as a question about a known supplier document field in the fixture corpus.
   - Expected: The Chat tab shows the user prompt once and one assistant answer. The answer is concise and grounded in the service response.
3. Inspect the rendered citations.
   - Expected: Citations come only from `AnswerResult.citations` and include filename, 1-indexed page number, citation snippet, and bounded score display. No raw page text, image blobs, raw provider response, or content hash is shown.
4. Trigger a Streamlit rerun, for example by interacting with another widget or refreshing the page state.
   - Expected: Prior user and assistant turns remain visible, and the previous prompt is not re-sent or answered again.
5. Ask an unrelated/off-topic question.
   - Expected: The Chat tab shows a clear safe abstention rather than a fabricated answer. It renders compact diagnostics such as status, reason code, run ID, provider, top score, citation count, and evidence reason when available.
6. Test provider setup failure by running without required live Gemini credentials while selecting/using the live provider path.
   - Expected: The Chat tab displays a user-actionable provider setup message and safe error class only. It does not leak secrets, environment values, raw exceptions, or raw provider payloads.

## Edge Cases

- Missing or stale retrieval index: user should receive an actionable setup/refresh message rather than a crash.
- Empty corpus or weak evidence: assistant should abstain and cite nothing.
- Provider runtime failure: assistant should render a safe provider-error state with bounded diagnostics.
- Repeated reruns after an answer: chat history persists and old prompts are not re-executed.

## Not Proven By This UAT

- Live Gemini answer quality or cost behavior under real credentials.
- Browser-driven visual styling polish beyond tested render calls.
- Langfuse trace ingestion and end-to-end monitoring, which are deferred to S05 operational proof.
- Visual ColQwen/Qdrant retrieval, which remains deferred beyond this text-RAG baseline.
