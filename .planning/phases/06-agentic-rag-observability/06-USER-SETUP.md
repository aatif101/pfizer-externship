# Phase 6: User Setup Required

**Generated:** 2026-09-24 (plan 06-04)
**Status:** Incomplete

## Environment Variables

| Status | Variable | Source | Add to |
|--------|----------|--------|--------|
| [ ] | `ANTHROPIC_API_KEY` | Anthropic Console -> Settings -> API Keys | `.env` |
| [ ] | `LANGFUSE_PUBLIC_KEY` | Langfuse project -> Settings -> API Keys | `.env` |
| [ ] | `LANGFUSE_SECRET_KEY` | Langfuse project -> Settings -> API Keys | `.env` |

Optional: `CRITIC_PROVIDER` (default `anthropic`; `gemini` is an explicit opt-in only), `CRITIC_MODEL` (default `claude-sonnet-4-6`), `CRITIC_MIN_FAITHFULNESS` (default `0.8`).

## Why

- **Anthropic:** the Claude Sonnet faithfulness critic for the agentic pipeline. Without the key the agentic path abstains with `critic_error` by design (D-02). It never switches to Gemini on its own.
- **Langfuse:** needed only to inspect live traces for the OBS-01 manual check. All tests run offline without it.

## Verification

```bash
venv/bin/python -c "from src.rag.critic import build_critic_provider; print(build_critic_provider().provider_name)"
# expected: anthropic
```

After an agentic Chat question, the Langfuse trace should show the LangGraph node spans and `generation.draft` / `generation.critique` generations with model and token usage, and no prompt text.

---
**Once all items are complete:** set Status to "Complete".
