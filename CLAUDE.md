<!-- GSD:project-start source:PROJECT.md -->
## Project

**Pfizer SDF Intelligence System**

An end-to-end AI-powered pharmaceutical document intelligence and compliance system for Pfizer supplier documentation (SDFs). The system ingests a folder of pharmaceutical PDFs (certificates of analysis, vendor certificates, compliance forms — many scanned or stamped) and delivers: automated field extraction with compliance flagging, a visual + hybrid RAG chatbot, and a Streamlit compliance dashboard with full observability. Built as a Pfizer externship demo to showcase AI engineering capability on real-world pharma document workflows.

**Core Value:** A pharmaceutical compliance officer can upload a folder of supplier documents and immediately see which ones are expired or at risk, ask natural language questions across the entire corpus, and trust every answer is grounded in a cited source page — with no hallucination.

### Constraints

- **Tech stack**: Python 3.11+, Docling, colpali-engine (ColQwen2), Qdrant, LangGraph, Langfuse, Streamlit, Pydantic, RAGAS — locked by design
- **VLM API**: Claude Sonnet or Gemini 2.5 Flash for extraction/generation — API-based, no self-hosted LLM
- **GPU**: ColQwen2 visual retrieval requires GPU; Colab Pro acceptable for demo
- **Timeline**: No hard deadline — build it right
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## TL;DR
## Recommended Stack
### Core Runtime
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Python | 3.11.x | Runtime | Docling 2.70+ dropped Python 3.9; 3.11 is the lowest-risk choice, widely tested in Colab and by all listed libraries. Streamlit 1.56 supports 3.10-3.14. Avoid 3.13+ because some ML deps still lag wheel availability. |
| Poetry or uv | latest | Dependency management | Reproducible locks for Colab and local parity. `uv` recommended for speed; both produce `pyproject.toml`. |
### Document Ingestion
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| docling | >=2.72.0 | PDF/image parsing with layout awareness | IBM's SDK, ships VlmPipeline that auto-selects the default Granite-Docling-258M. Latest major release on PyPI (Apr 16 2026) delivers 97.9% table extraction accuracy. Handles scanned, stamped, multi-column pharma docs far better than PyMuPDF/Tesseract. |
| docling-core | >=2.x (pulled transitively) | Unified DoclingDocument format | JSON/Markdown/DocTags export; needed for downstream chunking and bounding-box citations. |
| ibm-granite/granite-docling-258M | latest HF weights | VLM for end-to-end document conversion | Ultra-compact (258M params), ~114 ms/page on L4 GPU. Apache 2.0. Handles equations, tables, stamps, and has experimental multilingual support. Auto-downloaded by Docling on first run. |
# Weights pulled on first convert() call; cache ~/.cache/docling and HF_HOME
### Visual Retrieval
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| colpali-engine | >=0.3.11 | ColVision training/inference wrapper | Official library from illuin-tech. Version >=0.3.1 is required for ColQwen2.5; v0.3.7 is the training baseline. Pin latest minor in that series. |
| vidore/colqwen2.5-v0.2 | HF weights | Page-image visual retriever | Current SOTA checkpoint on the ViDoRe leaderboard. Based on Qwen2.5-VL-3B, dynamic resolution (up to 768 patches), ColBERT-style multi-vector output. Strictly better than colqwen2-v0.1 for document retrieval. |
| transformers | >=4.45 | Model loading backbone | Required floor for ColQwen2.5. Pin to a known-good minor (e.g., 4.46.x or 4.49.x) to avoid ColQwen init regressions; several bugfixes shipped in colpali-engine resolving `config.hidden_size` vs `config.text_config.hidden_size` across Transformers versions. |
| torch | >=2.3, <2.6 | GPU inference | Match the CUDA version Colab Pro ships (typically CU121 / CU124). On L4 use bfloat16 for ColQwen inference. |
| Pillow, pdf2image/pypdfium2 | latest | Page rasterization to images before embedding | Docling gives you `DoclingDocument.pages`; rasterize at 144-200 DPI for ColQwen. |
- ColPali generates ~1024 vectors per page; ColQwen2 dynamically adjusts up to 768 patches — smaller index, similar quality
- ColQwen2.5-v0.2 is the current top-performer on ViDoRe for English pharma-style layouts
- ColSmol is smaller but sacrifices accuracy — unacceptable for a compliance demo
### Vector Database
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| qdrant-client | >=1.17.1 | Python client for Qdrant | Latest (March 13 2026). Supports multivectors natively, `MaxSim` late interaction comparator, and Query API with `prefetch` for two-stage retrieval. |
| qdrant (server or local) | 1.12+ | Vector database | Native multivector support. Mean-pooled HNSW first stage + original multivector reranking is the canonical ColPali/ColQwen pattern documented by Qdrant (13x speedup, NDCG@20 = 0.952 vs un-pooled). |
| Environment | Mode | Reason |
|-------------|------|--------|
| Colab (demo) | `QdrantClient(path="/content/qdrant_storage")` | Persistent embedded local mode. No Docker in Colab. Survives session as long as Google Drive is mounted for storage; otherwise `:memory:` for ephemeral demos. |
| Local dev | Docker container on `:6333` | `docker run -p 6333:6333 -v ./qdrant_storage:/qdrant/storage qdrant/qdrant`. Full feature parity with cloud. |
| Production (out of scope) | Qdrant Cloud | — |
- Collection config: `MULTI_VECTOR_COMPARATOR=MaxSim`, `HNSW_INDEX` on a mean-pooled 128-d vector for first-stage, multivector disabled for HNSW (enabled for rerank).
- Use named vectors: `{"pooled": <128-d mean-pooled>, "multivector": <N x 128 original>}`.
- Query with `prefetch`: pooled HNSW top-200 → rerank with multivector MaxSim → top-k.
### LLM APIs
| Technology | Role | Model | Why |
|------------|------|-------|-----|
| Google Gemini API | Primary VLM (extraction, generation) | `gemini-2.5-flash` | $0.15/M input, $0.60/M output. Native vision, 1M-token context, ~35x cheaper than Claude Sonnet for bulk extraction over a folder of PDFs. Strong on structured outputs. |
| Anthropic Claude API | Critic agent, final generation, fallback | `claude-sonnet-4-6` | $3/M input, $15/M output. Best-in-class instruction following and self-critique for the faithfulness reflection loop. Use sparingly — only on the ~10% of extractions that need a second opinion and on final answer generation. |
| google-genai | >=1.0 | Google SDK | New unified SDK (replaces deprecated `google-generativeai`). |
| anthropic | >=0.40 | Anthropic SDK | Standard. |
### Agent Orchestration
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| langgraph | >=1.1.0 | Stateful agentic RAG graph | LangGraph 1.0 GA was Oct 2025; 1.1.0 released March 10 2026. Industry-standard framework for the query-decompose → retrieve → evaluate → regenerate loop. StateGraph + conditional edges are exactly the primitive needed for the critic/reflection pattern in PROJECT.md. |
| langgraph-prebuilt | latest | `create_react_agent` and tool helpers | Optional; use when the critic sub-agent needs ReAct-style tool-use. |
| langchain-core | >=0.3 | Message/tool abstractions | Pulled transitively; pin explicitly for reproducibility. |
| langchain-google-genai, langchain-anthropic | latest | Model bindings | Needed only if you want LangGraph's built-in LLM adapters. Alternative: wrap SDK calls in plain nodes — simpler and avoids LangChain's churn. |
### Observability
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| langfuse | **3.x (pinned, e.g., `>=3.0,<4.0`)** | Tracing, datasets, eval runs | **Critical:** Langfuse rewrote the Python SDK as v4 in March 2026. v4 is observations-first and has breaking API changes. Existing LangGraph integrations, callback handlers, and community cookbooks still target v3. Pin v3 for this demo to avoid churn; migration to v4 is an explicit Phase 3+ task. |
| openinference-instrumentation-langchain | latest | OTEL spans for LangGraph | Optional alternative/companion to Langfuse callback handler — gives OpenTelemetry-compatible spans. |
- Wrap the top-level graph invocation in `@observe()` decorator for a root trace
- Pass `CallbackHandler()` in `RunnableConfig.callbacks` so every LangGraph node, LLM call, and retrieval becomes a nested observation
- Attach metadata: `critic_score`, `retrieval_round`, `doc_id`, `page_number` for audit trail
### Evaluation
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| ragas | 0.4.3 (released Jan 13 2026) | Faithfulness, context recall/precision, answer relevancy | The standard. 0.4.x is API-stable vs the 0.2/0.3 churn. Works with any LLM judge — point it at Gemini 2.5 Flash for cheap eval runs. |
| scikit-learn | latest | F1 per field for extraction eval | Classical metrics for the ~50-page gold set — per-field precision/recall/F1. |
| pytest | latest | Harness | Run eval as part of CI-ish checks. |
- Extraction: per-field F1 (sklearn) on hand-labeled gold set
- Retrieval: `recall@5` and `ndcg@5` on query → expected page_id pairs
- Generation: RAGAS `faithfulness`, `answer_relevancy`, `context_recall`
- Citation: custom metric — does the cited `(doc_id, page)` actually contain the answer span? Binary.
- Latency: p50/p95 from Langfuse traces
- Cost: Langfuse token cost tracking per trace
### Hybrid Retrieval (Phase 1)
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| bm25s | latest | Sparse BM25 retrieval | **Strongly preferred over rank_bm25.** Uses scipy sparse matrices — orders of magnitude faster, near-Elasticsearch speeds on a single node, pure Python, no Java dependency. rank_bm25 is fine only for toy corpora. |
| sentence-transformers | latest | Dense embeddings for Phase 1 text RAG | Use `BAAI/bge-small-en-v1.5` or `bge-base-en-v1.5` for Phase 1 baseline dense retrieval — CPU-friendly, strong pharma-domain generalization. |
| rerankers (ms-marco cross-encoder) | via `sentence-transformers` | Rerank fused candidates | `cross-encoder/ms-marco-MiniLM-L-6-v2` as the fusion reranker for BM25+dense in Phase 1. |
### Data Validation & Schemas
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| pydantic | >=2.8 | Extraction schemas (Pfizer SDF fields) | v2 is mandatory — v1 is EOL. Use Pydantic models directly as Gemini/Claude structured-output schemas. Validation errors feed the critic loop. |
| pydantic-settings | latest | Env/config loading | Clean separation of API keys, model IDs, Qdrant URLs across Colab vs local. |
### Dashboard
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| streamlit | >=1.56 | Compliance dashboard UI | 1.56.0 released March 31 2026 — supports pandas 3.x, Material icons in alerts, shortcut file-uploader types. Perfect fit for the sortable table with risk color-coding described in PROJECT.md. |
| pandas | >=2.2 | Tabular manipulation for the dashboard | Standard. |
| streamlit-aggrid or st.dataframe | — | Sortable/filterable table | `st.dataframe` with `column_config.LinkColumn` is now rich enough — avoid aggrid complexity for a single-user demo. |
| st.pdf or pdf.js iframe | — | Source page preview on row click | For the "source page link" requirement. |
### Supporting Utilities
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pypdfium2 | latest | Fast PDF rasterization | Cross-platform, better than pdf2image on Colab (no poppler install headaches). |
| python-dateutil | latest | Date parsing from extracted strings | Pharma docs have inconsistent date formats — "01-JAN-2024", "Jan 1, 2024", "2024-01-01". |
| tenacity | latest | Retry wrapper for LLM API calls | Standard for handling transient 429/503 from Gemini/Claude. |
| loguru | latest | Structured logging | Simpler than stdlib `logging` for a demo; pairs with Langfuse traces. |
| tqdm | latest | Progress bars for batch ingest | User-facing feedback during folder ingestion. |
## Alternatives Considered
| Category | Recommended | Alternative Rejected | Why Not |
|----------|-------------|----------------------|---------|
| PDF ingestion | Docling | Unstructured.io | Works but weaker on scanned/stamped content; no integrated VLM pipeline. |
| PDF ingestion | Docling | PyMuPDF + Tesseract | Mangles complex tables and stamps common in pharma SDFs. |
| Visual retrieval | ColQwen2.5 | ColPali v1.3 | Older; more vectors/page, slightly lower accuracy on current ViDoRe. |
| Visual retrieval | ColQwen2.5 | ColSmol | Smaller/faster but accuracy drop unacceptable for compliance use. |
| Vector DB | Qdrant | Weaviate, Milvus | Qdrant's native multivector + MaxSim support is best-in-class for ColPali-family models; locked by PROJECT.md anyway. |
| Vector DB | Qdrant | pgvector | No late-interaction multivector support. |
| Sparse retrieval | bm25s | rank_bm25 | 10-100x slower on medium corpora; no sparse-matrix path. |
| Sparse retrieval | bm25s | Elasticsearch | Operational overhead unjustified for a demo corpus. |
| Agent framework | LangGraph | LlamaIndex Workflows | LangGraph locked by PROJECT.md; also more explicit state-machine ergonomics. |
| Agent framework | LangGraph | CrewAI / AutoGen | Less granular control over the critic/regenerate loop. |
| Observability | Langfuse v3 | Langfuse v4 | Breaking changes; integration examples lagging — adopt later. |
| Observability | Langfuse v3 | LangSmith | Locked to Langfuse in PROJECT.md; also Langfuse is self-hostable which matters for pharma data. |
| Eval | RAGAS | DeepEval, TruLens | RAGAS locked; also best-documented for faithfulness/recall pair. |
| Primary VLM | Gemini 2.5 Flash | Claude Sonnet 4.6 (as primary) | 35x more expensive for bulk extraction. Use Claude only for critic/final generation. |
| Primary VLM | Gemini 2.5 Flash | GPT-4o | Not on locked stack. |
| Dashboard | Streamlit | Gradio, Dash | Locked; Streamlit is the pragmatic pick anyway. |
## Colab Compatibility Notes
| Item | Colab Status | Notes |
|------|--------------|-------|
| Docling + Granite-Docling-258M | Works on Colab Pro L4 | First run downloads ~500 MB of weights; cache via `HF_HOME=/content/hf_cache` to survive session resets when mounted to Drive. CPU-only fallback works but is 10-20x slower. |
| ColQwen2.5-v0.2 (3B) | Requires GPU with >=16 GB VRAM | **T4 (15 GB) is marginal** — possible with `torch.bfloat16` and small batches; expect OOM on high-res images. **L4 (22.5 GB) is the sweet spot.** A100 (40 GB) is overkill but fastest. |
| Qdrant local mode | Works natively | `QdrantClient(path="/content/qdrant_storage")`. Mount Drive for persistence across Colab sessions. Zero external deps. |
| Streamlit in Colab | Works via tunneling | Use `pyngrok` or `localtunnel`; not ideal for demo. **Better:** run Streamlit locally and keep Colab for the heavy ColQwen inference via a FastAPI bridge. |
| Langfuse | SaaS works out of box | API-key based; set `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` as Colab secrets. |
| RAGAS | Works; LLM calls via API | No local model required — use Gemini 2.5 Flash as judge. |
- T4: 1.76 CU/hr — fine for dev, marginal for ColQwen2.5-v0.2
- L4: ~4 CU/hr — **recommended default**
- A100: ~15 CU/hr — only if batch-indexing the full corpus on a deadline
## Installation
### Colab cell (top-of-notebook)
### Local (Poetry / uv)
## Version Pinning Strategy
| Library | Strategy | Reason |
|---------|----------|--------|
| docling | `>=2.72,<3.0` | 2.x is stable; 3.x (not released) would be breaking. |
| colpali-engine | `>=0.3.11,<0.4` | Pre-1.0 library; minor bumps have broken init paths historically. |
| langgraph | `>=1.1.0,<2.0` | 1.x is semver-stable since GA. |
| langfuse | `>=3.0,<4.0` | **Hard upper bound.** v4 is breaking. |
| ragas | `==0.4.3` | Exact pin — metric definitions and API have shifted across 0.x minors. |
| transformers | `>=4.45,<4.50` | Floor for ColQwen2.5; ceiling avoids surprise regressions. |
| qdrant-client | `>=1.17,<2.0` | Stable major. |
| streamlit | `>=1.56,<2.0` | Stable. |
## Open Risks / Watch List
## Sources
- [docling on PyPI](https://pypi.org/project/docling/)
- [Docling VLM pipeline with GraniteDocling (official docs)](https://docling-project.github.io/docling/examples/minimal_vlm_pipeline/)
- [IBM Granite-Docling-258M model card](https://huggingface.co/ibm-granite/granite-docling-258M)
- [IBM announcement: Granite-Docling end-to-end document understanding](https://www.ibm.com/new/announcements/granite-docling-end-to-end-document-conversion)
- [colpali-engine on PyPI](https://pypi.org/project/colpali-engine/)
- [illuin-tech/colpali GitHub](https://github.com/illuin-tech/colpali)
- [vidore/colqwen2.5-v0.2 model card](https://huggingface.co/vidore/colqwen2.5-v0.2)
- [Qdrant: PDF retrieval at scale with ColPali/ColQwen](https://qdrant.tech/documentation/tutorials-search-engineering/pdf-retrieval-at-scale/)
- [Qdrant: Optimizing ColPali — 13x faster with mean pooling + rerank](https://qdrant.tech/blog/colpali-qdrant-optimization/)
- [qdrant-client on PyPI](https://pypi.org/project/qdrant-client/)
- [LangGraph on PyPI](https://pypi.org/project/langgraph/)
- [LangGraph agentic RAG (official)](https://docs.langchain.com/oss/python/langgraph/agentic-rag)
- [Self-reflective RAG with LangGraph (LangChain blog)](https://www.langchain.com/blog/agentic-rag-with-langgraph)
- [langfuse on PyPI](https://pypi.org/project/langfuse/)
- [Langfuse Python v3 → v4 migration guide](https://langfuse.com/docs/observability/sdk/upgrade-path/python-v3-to-v4)
- [Langfuse LangGraph integration cookbook](https://langfuse.com/guides/cookbook/integration_langgraph)
- [ragas on PyPI](https://pypi.org/project/ragas/)
- [RAGAS faithfulness metric docs](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/faithfulness/)
- [Streamlit release notes](https://docs.streamlit.io/develop/quick-reference/release-notes)
- [bm25s HuggingFace blog post (perf comparison vs rank_bm25)](https://huggingface.co/blog/xhluca/bm25s)
- [Gemini API pricing 2026 (Apr 2026)](https://benchlm.ai/blog/posts/gemini-api-pricing)
- [LLM API pricing comparison 2026 (Claude vs Gemini)](https://fungies.io/llm-api-pricing-comparison-2026-openai-claude-gemini-deepseek/)
- [Colab GPU options and pricing 2026](https://www.thundercompute.com/blog/colab-alternatives-for-cheap-deep-learning-in-2025)
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
