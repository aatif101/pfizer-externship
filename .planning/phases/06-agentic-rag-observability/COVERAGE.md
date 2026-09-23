# API Coverage — Phase 6 (Anthropic Messages API, Langfuse Python SDK v3, LangGraph 1.0.1, Google GenAI)

> Full coverage by default. Opt-outs are explicit, reasoned decisions. Capability names are prefixed by service so they stay unique in one matrix.

| capability | decision | reason |
|---|---|---|
| anthropic.messages.create (sync, text JSON critic verdict) | INTEGRATE | |
| anthropic.client construction from ANTHROPIC_API_KEY (lazy import) | INTEGRATE | |
| anthropic.usage token reporting (input_tokens/output_tokens to generation spans) | INTEGRATE | |
| anthropic.transient error retry (429/5xx via tenacity) | INTEGRATE | |
| anthropic.streaming responses | OPT-OUT | explicitly out of scope: streaming chat is in REQUIREMENTS Out of Scope |
| anthropic.tool use / function calling | OPT-OUT | not needed: the critic returns one JSON verdict and has no tools |
| anthropic.output_config structured-output schema | OPT-OUT | not needed yet: Pydantic validation of text JSON already fails closed; revisit if the malformed-verdict rate is material |
| anthropic.async client | OPT-OUT | not needed: Streamlit path uses sync graph.invoke (research anti-pattern: async in Streamlit) |
| anthropic.batch / files / vision inputs | OPT-OUT | not needed: the critic judges text evidence only |
| langfuse.observe decorator (spans + as_type=generation) | INTEGRATE | |
| langfuse.propagate_attributes (phase tags, session_id, metadata) | INTEGRATE | |
| langfuse.Langfuse(mask=...) global masking | INTEGRATE | |
| langfuse.langchain.CallbackHandler (LangGraph node tracing) | INTEGRATE | |
| langfuse.update_current_trace, _span, _generation | INTEGRATE | |
| langfuse.flush | INTEGRATE | |
| langfuse.auth_check (existing verify_langfuse_connection) | INTEGRATE | |
| langfuse.datasets / experiment runs | OPT-OUT | not needed yet: Phase 7 benchmark owns eval-run storage |
| langfuse.scores API (attach critic_score as a Langfuse score) | OPT-OUT | not needed yet: critic_score is carried as allowlisted metadata; Phase 7 can promote it to a score |
| langfuse.prompt management | OPT-OUT | not needed: prompts are versioned in code |
| langfuse.v4 SDK | OPT-OUT | explicitly out of scope: REQUIREMENTS pins <4.0 (breaking changes) |
| langgraph.StateGraph + add_node/add_edge/add_conditional_edges + compile | INTEGRATE | |
| langgraph.invoke with RunnableConfig (recursion_limit, callbacks) | INTEGRATE | |
| langgraph.errors.GraphRecursionError handling | INTEGRATE | |
| langgraph.checkpointers / persistence / interrupts | OPT-OUT | not needed: each question is a stateless run; HITL is a DB review queue, not graph interrupts |
| langgraph.astream / streaming | OPT-OUT | explicitly out of scope: streaming excluded and async breaks Streamlit |
| langgraph.prebuilt create_react_agent | OPT-OUT | not needed: plain-function nodes per CLAUDE.md guidance |
| langgraph.get_graph().draw_mermaid diagram export | OPT-OUT | not needed yet: Phase 7 POLISH-01 architecture diagrams |
| google-genai.generate_content (draft, decompose, rewrite, opt-in critic) | INTEGRATE | |
| google-genai.usage_metadata token reporting | INTEGRATE | |
| google-genai.streaming / live API | OPT-OUT | explicitly out of scope: streaming excluded |
