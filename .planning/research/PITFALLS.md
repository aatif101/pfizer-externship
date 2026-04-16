# Domain Pitfalls

**Project:** Pfizer SDF Intelligence System
**Stack:** Docling + ColQwen2 + Qdrant + LangGraph + Langfuse + Streamlit + Pydantic + RAGAS
**Researched:** 2026-04-16
**Overall confidence:** MEDIUM-HIGH (most pitfalls confirmed via official issue trackers; a few synthesized from ecosystem patterns)

---

## How to Use This Document

Each pitfall includes:
- **What goes wrong** — the failure mode
- **Warning signs** — how to detect early
- **Prevention** — actionable fix in code/config
- **Phase** — where in the roadmap to address it (P1 = Baseline, P2 = Upgrade, P3 = Demo polish)

Pitfalls are grouped by severity. Read **Critical** before writing any code. Read **Moderate** before starting each phase. Read **Minor** during polish.

---

## Critical Pitfalls

These cause rewrites, broken demos, or silently-wrong answers. Address before or during the phase noted.

### C1. Indexing every ColQwen2 token-vector into HNSW (Qdrant OOM / slowness)

**Phase:** P2
**Confidence:** HIGH (Qdrant official docs + multiple blog confirmations)

**What goes wrong:** A single PDF page produces ~700–1030 ColQwen2 patch vectors (128-dim each). Naively creating a Qdrant multivector collection with default HNSW (`m=16`) builds a graph over every token-vector. For ~50 demo pages this is ~50k nodes; for a realistic corpus it explodes RAM, slows inserts, and wastes compute because late-interaction MaxSim is only meaningful at the *page* level, not token level.

**Warning signs:**
- Qdrant RSS >4 GB for modest corpora
- Indexing throughput <1 page/sec even on GPU
- Collection info reports `indexed_vectors_count` in the hundreds of thousands per doc
- Colab runtime crashes during `upsert` batches

**Prevention (code):**
```python
# Two-stage collection: mean-pooled vector WITH HNSW, full multivector WITHOUT
client.create_collection(
    collection_name="sdf_pages",
    vectors_config={
        "mean_pooled": VectorParams(size=128, distance=Distance.COSINE),  # HNSW here
        "colqwen_full": VectorParams(
            size=128,
            distance=Distance.COSINE,
            multivector_config=MultiVectorConfig(comparator=MultiVectorComparator.MAX_SIM),
            hnsw_config=HnswConfigDiff(m=0),  # CRITICAL: disables HNSW
        ),
    },
)
```
Retrieval = ANN on `mean_pooled` (top 50) → rerank with `colqwen_full` MaxSim (top 5).

**Detection:** Log `client.get_collection(...).indexed_vectors_count` after ingest. Should roughly equal page count, not token count.

---

### C2. Phase 1 → Phase 2 schema break (Qdrant collection incompatibility)

**Phase:** P2 (planning), P1 (prep)
**Confidence:** HIGH (Qdrant collections have immutable vector configs)

**What goes wrong:** Qdrant collection schemas (vector name, dim, distance, multivector config) are effectively immutable. Phase 1's `dense_768` collection cannot be upgraded in-place to Phase 2's multivector schema. Teams often discover this mid-Phase-2 and either (a) lose Phase 1 baselines, or (b) spend a day rebuilding parallel collections.

**Warning signs:**
- Phase 1 code hardcodes `collection_name="documents"`
- No version suffix on collection names
- Re-ingesting Phase 1 corpus after Phase 2 changes is expected to "just work"

**Prevention:**
- Use versioned, role-suffixed collection names from day 1: `sdf_pages_v1_dense`, `sdf_pages_v2_colqwen`
- Keep Phase 1 collection intact during Phase 2 — needed for the self-benchmark
- Store ingest manifest (doc hash → collection → point_id) as JSON to enable re-ingest parity checks
- Never do in-place schema migration; always create new collection + re-ingest

**Detection:** CI check that asserts collection names contain `_v[0-9]+_`.

---

### C3. Docling memory leak on sequential PDF processing

**Phase:** P1
**Confidence:** HIGH (confirmed in docling GitHub issue #2829)

**What goes wrong:** Docling's converter does not fully release memory between documents. Processing a folder of 50+ PDFs sequentially leaks 3–4 GB RAM and crashes the Colab runtime before the batch finishes. Granite-Docling VLM path is worse because of held GPU tensors.

**Warning signs:**
- RAM monitor climbs monotonically through batch
- Process killed (`^C` / OOMKill) around document 30–50
- Second run of same corpus fails earlier than first (leaked state from prior cell)
- Colab "You are using too much RAM" banner

**Prevention (code):**
```python
import gc, torch

for pdf_path in pdf_paths:
    converter = DocumentConverter()  # recreate per doc
    result = converter.convert(pdf_path)
    # ... extract and persist ...
    del converter, result
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
```
Also consider `DOCFLOW_PDF_BACKEND=pypdfium2` env var (reportedly fixes 90% of OOMs per docling community). For heavy batches, spawn worker subprocesses and recycle after N docs.

**Detection:** Log `psutil.Process().memory_info().rss` before/after each doc; alert if delta >200MB post-GC.

---

### C4. VLM extraction hallucinates plausible-but-wrong pharma metadata

**Phase:** P1 (observed), P2 (mitigated)
**Confidence:** HIGH (VADE 2025, HalLoc CVPR 2025, domain knowledge of pharma)

**What goes wrong:** VLMs (Claude Sonnet, Gemini 2.5 Flash) invent plausible dates, vendor names, and lot numbers when the target field is partially obscured by stamps, low-resolution scans, or handwritten overlays. The output *validates* against Pydantic schema, *looks right*, and is *completely fabricated*. In pharma context, a hallucinated "effective date" is regulatory risk, not just a UX bug.

**Warning signs:**
- Extractions succeed on every document (no nulls, no abstains) — too good
- Same value across unrelated docs (language-prior leakage: e.g., "Pfizer Inc." inferred from "Pfizer" watermark that isn't actually the vendor)
- Field values don't match any visible text span when manually checked
- Confidence scores uniform (~0.95) across all fields

**Prevention:**
- **Require grounding citation in schema**: every extracted field must return `{value, source_page, source_bbox, verbatim_text_span}`. Reject outputs where `verbatim_text_span not in page_ocr_text` (fuzzy match threshold ~0.85).
- **Null-biasing prompt**: "If the field is not clearly visible and legible, return null. Do NOT infer from context, headers, or watermarks."
- **Multi-shot verification (P2 critic loop)**: re-ask the VLM to quote the exact text for each field; fail if quotes disagree.
- **Schema with Optional + abstention**: `effective_date: Optional[date] = None` with `extraction_confidence: float` and `abstention_reason: Optional[str]`.

**Detection:** Eval metric: grounding_rate = fraction of non-null extractions whose verbatim span is found on the cited page. Target >0.95. Log as first-class RAGAS-adjacent metric.

---

### C5. Critic/reflection loop worsens accuracy (self-correction fallacy)

**Phase:** P2
**Confidence:** HIGH (Huang et al. 2023; 2025 reflection benchmarks confirm diminishing returns after round 2–4)

**What goes wrong:** Asking an LLM to "review and correct" its own output *without new information* systematically degrades accuracy. The critic draws on the same knowledge that produced the error. Pfizer demo will show "look, critic fixed the mistake" on cherry-picked cases while regressing on the aggregate.

**Warning signs:**
- Critic "finds issues" in >50% of initial extractions (over-critical)
- Final F1 after critic loop is lower than single-pass F1 on held-out set
- Reconciliation pass flips the correct answer to the wrong one
- More than 2–3 iterations produce no additional changes (burning tokens)

**Prevention:**
- **Ground the critic in new evidence**: the critic must re-read the source page image AND the verbatim span, not just the extractor's JSON. This provides new information.
- **Hard iteration cap at 2**: round 1 = extractor, round 2 = critic-with-evidence. No round 3 in P2; research shows diminishing returns after round 2 for this task class.
- **Disagreement-only reconciliation**: only invoke a third pass when critic and extractor disagree on a field; do NOT re-verify already-agreed fields.
- **A/B gate before shipping**: evaluate `extractor_only` vs `extractor+critic` F1 on gold set. Only enable critic if delta-F1 > +3% AND no field regresses by >2%.
- **Log critic edit distance**: track how many fields the critic changes. If >40%, prompt is broken (over-critical).

**Detection:** Offline eval harness compares `extraction_only` vs `extraction+critic` per field. CI fails if critic regresses any field.

---

### C6. Colab session dies mid-indexing (hours of work lost)

**Phase:** P1 and P2
**Confidence:** HIGH (Colab FAQ + GitHub colabtools issues)

**What goes wrong:** Colab free has ~90 min idle timeout, Colab Pro caps at 24h max runtime and 90 min idle. ColQwen2 indexing a few hundred pages can take 1–3 hours. Drive mount times out for folders with >10k items. If indexing isn't checkpointable, you restart from scratch every disconnect.

**Warning signs:**
- "Runtime disconnected" during cell execution
- `MessageError: TransportError: request to ... failed` on Drive operations
- GPU "in use" but notebook frozen
- Fresh runtime reports no cached embeddings

**Prevention:**
- **Resumable ingest**: Qdrant upserts are idempotent when you use deterministic point IDs (hash of doc_path + page_num). Re-running the indexer skips already-indexed pages via `client.retrieve(ids=[...])` pre-check.
- **Persist Qdrant storage to Drive**: run Qdrant in local mode with `path="/content/drive/MyDrive/qdrant_storage"` so embeddings survive runtime death. Note: Drive I/O is slow; acceptable for demo, not for scale.
- **Checkpoint ingest manifest every N docs**: write `{doc_id, status, timestamp}` JSON to Drive after each batch of 5.
- **Keep the tab focused** or use a keep-alive (e.g., `IPython.display.Javascript`); Colab idles after ~90 min of no browser activity.
- **Flatten Drive layout**: keep PDFs in one sub-folder, not >10k items in `MyDrive` root.
- **Plan for local fallback**: document a 15-min "run locally with CUDA" path for demo day.

**Detection:** Ingest script logs "resuming from doc N/M" on restart. If always starts at 0, resumability is broken.

---

### C7. Gemini/Claude structured-output silent schema mismatch

**Phase:** P1
**Confidence:** HIGH (pydantic-ai issues, Gemini JSON mode docs)

**What goes wrong:** Gemini's JSON mode returns a string that *looks* like JSON but silently omits fields, reorders them, or fills Optionals with empty strings instead of null. Claude's structured output is stricter but refuses certain schemas with complex nested Pydantic unions. Without retries and validation, you silently lose data.

**Warning signs:**
- `pydantic.ValidationError` once per ~10 calls with no retry
- All `Optional[str]` fields get empty string instead of None
- Nested models produce partial data (top-level fields present, nested ones missing)
- Gemini tool calls fail when combined with structured output (not supported simultaneously)

**Prevention:**
- Use `instructor` or `pydantic-ai` rather than raw API calls — they handle retries on validation failure (2–3 retries with validation error injected into prompt).
- **Keep schema flat**: avoid deep nesting. `ExtractedFields(vendor: str, effective_date: date | None, ...)` beats nested `Document(metadata: Metadata(dates: Dates(effective: date)))`.
- **Explicit null in prompt**: "Use null for missing fields, not empty string."
- **Field-order matters for Gemini**: put simpler scalar fields before complex ones in the schema.
- **Validate semantics, not just types**: date fields checked for `1990 <= year <= 2030`, vendor names non-empty after strip, etc.

**Detection:** Log validation retry count per call; alert on >2 retries or persistent failures on same doc.

---

## Moderate Pitfalls

Cause frustrating bugs and partial demo failures. Address during the phase noted.

### M1. Langfuse missing spans in async LangGraph nodes

**Phase:** P2
**Confidence:** HIGH (Langfuse discussion #9236, #10591)

**What goes wrong:** Attaching Langfuse `CallbackHandler` at graph compile time *usually* traces all nested LLM/retriever calls, but async generators, streaming responses, and multi-worker setups break OpenTelemetry context propagation. Result: top-level graph trace is captured but critical inner LLM calls (the ones you need for audit) are missing.

**Warning signs:**
- Langfuse UI shows a trace with 2 spans when you expect 15
- Spans appear under "orphan" trace IDs
- Works locally, breaks on Streamlit Cloud / multi-worker deploy

**Prevention:**
- Use `langfuse.start_as_current_observation(...)` context manager in async code, not bare `@observe` decorators.
- Pass callbacks at **invocation time** (`graph.invoke(state, config={"callbacks": [handler]})`) rather than compile time — more reliable for async.
- For Streamlit: wrap the whole graph call in a single `with langfuse.start_as_current_span("rag_query"):` block so the root span anchors downstream children.
- Test with `flush()` before session end in Streamlit — otherwise traces are lost on session reset.

**Detection:** After each dev query, check Langfuse UI for expected span count. Add CI smoke test that runs a fixed query and asserts `len(trace.observations) >= expected_min`.

---

### M2. LangGraph infinite loop / recursion limit exceeded

**Phase:** P2
**Confidence:** HIGH (LangGraph docs, discussion #1725, issue #1698)

**What goes wrong:** Agentic RAG graphs have cycles: `retrieve → evaluate → re-retrieve → draft → critique → regenerate`. If the "quality gate" node always returns "insufficient," the graph loops forever. Default LangGraph recursion limit is 25, which either truncates mid-improvement or silently hides the bug. `SubAgentMiddleware` doesn't propagate recursion_limit to subgraphs — known issue.

**Warning signs:**
- `GraphRecursionError` at query time
- Same retrieval round repeats with identical results (the critic hasn't learned)
- Queries that should take 2–3s take 30s+
- Token usage per query is 5–10x the P1 baseline for the same question

**Prevention:**
- **Explicit iteration counter in state**: `retrieval_rounds: int = 0`, increment in retrieve node, hard-cap at 2 with `Command(goto=END, update={"abstain": True})`.
- **Monotonic progress check**: if new retrieval returns identical doc IDs to previous round, force exit.
- **Set `recursion_limit=10`** explicitly on invoke — tight enough to fail fast, loose enough for 2–3 genuine rounds.
- **Exit criteria for critic**: faithfulness score > threshold OR rounds >= max OR identical-to-previous.
- **Unit-test each cycle path**: deliberately craft "always-insufficient" input and assert graceful abstention, not crash.

**Detection:** Log `retrieval_rounds` per query; histogram should peak at 1, long tail to 2–3. If >20% at max, loop logic is broken.

---

### M3. Docling struggles on stamped / rotated / handwritten pharma PDFs

**Phase:** P1
**Confidence:** HIGH (Docling issues #2128, #2134, #2446; pharma domain knowledge)

**What goes wrong:** Pharmaceutical SDFs often have: rotated pages (signatures on sideways form), red ink stamps over printed text ("APPROVED", "VOID", lot stamps), handwritten revision dates in margins, scanned-then-rotated archive docs. Docling's layout model + default OCR can: miss stamps entirely, read through them and corrupt the underlying text, mis-order reading flow on rotated pages.

**Warning signs:**
- "APPROVED" or lot number visible to human but absent from extracted markdown
- Extracted text has stamp-text interleaved with document text
- Tables extracted with wrong column count on rotated pages
- `do_ocr=False` behavior isn't actually disabling OCR (issue #2312)

**Prevention:**
- **Force full-page OCR** for scanned docs: use Docling's `force_full_page_ocr=True` option where applicable.
- **Preprocess rotation**: detect orientation with a lightweight classifier (or `ocrmypdf --rotate-pages`) before handing to Docling.
- **Use ColQwen2 as ground truth for visual retrieval** (P2): don't rely solely on Docling text for stamp/signature queries — the VLM sees the page image directly.
- **Parallel dual-path**: for critical fields (effective_date, expiry_date), run both Docling-OCR extraction AND direct VLM-on-image extraction; flag disagreements for HITL.
- **Domain-tuned eval subset**: ensure gold set includes 10+ stamped/rotated/handwritten examples — these are where baselines diverge.

**Detection:** Eval the gold-set stamped subset separately. If extraction F1 on stamped docs < 0.7× overall F1, Docling pipeline needs preprocessing.

---

### M4. Streamlit rerun destroys LangGraph state / streaming breaks

**Phase:** P1 (UI), P2 (streaming)
**Confidence:** HIGH (Streamlit issue #12076 + session state docs)

**What goes wrong:** Streamlit reruns the whole script on every widget interaction. LangGraph `MemorySaver` checkpoints live in memory and are lost on rerun unless stored in `st.session_state`. `st.write_stream` on `graph.astream(...)` raises `RuntimeError: Event loop is closed` because Streamlit's new event loop per rerun collides with LangGraph's.

**Warning signs:**
- Chat history disappears after user clicks any widget
- Streaming tokens appear then vanish
- `RuntimeError: Event loop is closed` in Streamlit logs
- "Agent memory" resets between user messages in same session

**Prevention:**
- Store LangGraph checkpointer + thread_id in `st.session_state`:
  ```python
  if "graph" not in st.session_state:
      st.session_state.graph = build_graph(checkpointer=MemorySaver())
      st.session_state.thread_id = str(uuid.uuid4())
  ```
- Use sync `graph.stream(...)` (not `astream`) for Streamlit; iterate with a placeholder container.
- For async unavoidable cases, wrap with `nest_asyncio.apply()` + `asyncio.run()` in a single cell.
- Gate expensive ingest/index behind `@st.cache_resource` so it runs once per process, not per rerun.

**Detection:** Smoke test: click a widget, verify chat history persists. Run `streamlit run` locally with verbose logs; watch for event-loop errors.

---

### M5. RAGAS faithfulness metric gameable / unstable on small gold sets

**Phase:** P1 (eval setup), P3 (benchmark)
**Confidence:** HIGH (2026 RAG eval best-practice articles)

**What goes wrong:** RAGAS uses LLM-as-judge. On a 50-page gold set with ~20 questions, single-run faithfulness scores swing ±0.1 between runs because the judge LLM is non-deterministic. You can also "game" faithfulness by retrieving huge contexts and having the generator parrot them — high faithfulness, low usefulness. A score of 0.85 on run-1 and 0.78 on run-2 doesn't mean the system got worse; it means the gold set is too small.

**Warning signs:**
- Same eval script, different runs produce >0.05 metric delta
- Faithfulness score rises as you retrieve MORE irrelevant chunks (gaming)
- <20 eval questions in gold set
- P2-vs-P1 delta smaller than run-to-run noise

**Prevention:**
- **Gold set size ≥50 questions** for stable metrics. Aim for 75+ to distinguish small improvements.
- **Average over 3 runs** with different judge seeds; report mean and stddev, not point estimates.
- **Use a classifier-based alternative for faithfulness** (HHEM, Lynx) alongside RAGAS LLM-judge; report both.
- **Cap retrieved context at 8 chunks max** — faithfulness degrades above that (attention dilution).
- **Track citation accuracy separately**: fraction of claims where the cited page actually supports the claim. This is harder to game.
- **Hold-out "hard" subset**: 10 adversarial questions (negation, expired doc edge cases, stamp-obscured fields) to surface regressions that average metrics hide.

**Detection:** Run eval twice back-to-back at P1 completion; compute run-to-run variance. If variance > target P2 improvement, grow gold set.

---

### M6. Gold-set labels are inconsistent (single annotator = single point of failure)

**Phase:** P1
**Confidence:** MEDIUM (general IAA best practices; pharma-specific nuance)

**What goes wrong:** "Hand-labeled gold set" by a single person (externship candidate) encodes that person's interpretation of ambiguous cases: Is the "revision date" the one in the footer or the one stamped on page 1? Is "Pfizer Ireland Ltd." the same vendor as "Pfizer Ireland"? Without a second annotator or written guidelines, you benchmark the pipeline against your own biases, not ground truth.

**Warning signs:**
- No written annotation guide
- No disagreement cases logged
- Fields ambiguous in docs (multiple dates, multiple vendor aliases) get one value without comment
- Re-labeling same doc a week later gives different answers

**Prevention:**
- **Write a 1-page annotation guide** before labeling: how to handle conflicting dates, vendor name canonicalization, null vs empty vs "not present," stamp precedence rules.
- **Label each doc twice** (self-re-annotation a week apart) and resolve disagreements — poor-man's IAA.
- **If possible, have a second person** label a 10-doc subset; compute Cohen's kappa per field. Target κ > 0.7.
- **Version the gold set** (`gold_v1.json`, `gold_v2.json`) — never silently change labels during eval.
- **Document edge-case decisions** inline with labels: `{"effective_date": "2022-03-15", "note": "chose stamped revision over printed date per guide §3.2"}`.

**Detection:** Re-annotate 5 docs after a week; measure self-agreement per field. <90% agreement = guide is ambiguous.

---

### M7. ColQwen2 out-of-memory on T4 / Colab GPU with default batch

**Phase:** P2
**Confidence:** HIGH (colpali-engine docs, issues)

**What goes wrong:** Default colpali-engine example batch sizes target A100/L4 GPUs (16+ GB). On a Colab T4 (15 GB) or free-tier K80, default `batch_size=8` OOMs. Users then guess-and-check, wasting Colab compute units.

**Warning signs:**
- `torch.cuda.OutOfMemoryError` during `processor(images=...)`
- `nvidia-smi` shows VRAM climbing past 13 GB then crash
- Batch index where crash happens varies run-to-run (leaked tensors)

**Prevention:**
- **Start with `batch_size=2`** for T4 / low VRAM, scale up only after successful end-to-end run.
- Use `torch.bfloat16` (not fp32); enable Flash Attention 2 if supported.
- Call `torch.cuda.empty_cache()` + `gc.collect()` between batches.
- **Cap image resolution**: ColQwen2 caps at 768 patches max; if Docling exports high-DPI page images, downsample to ~896×1152 before embedding.
- **Consider `HierarchicalTokenPooler`** for memory-constrained runs: reduces per-page vector count with small accuracy cost.

**Detection:** Log peak `torch.cuda.max_memory_allocated()` per batch; set a soft alarm at 90% of GPU capacity.

---

### M8. Bounding-box citations don't actually point to the claimed field

**Phase:** P2
**Confidence:** MEDIUM (inferred from ColQwen2 architecture + general VLM behavior)

**What goes wrong:** ColQwen2's late-interaction similarity maps show *which patches contribute to retrieval*, NOT *where a specific field value is located*. Teams conflate these: they show a user a bounding box and claim "here's where we extracted the effective date," but the box is actually the overall retrieval heatmap. User clicks, sees an unrelated region highlighted, loses trust.

**Warning signs:**
- Demo reviewer says "that box isn't pointing at the date"
- Bbox coordinates don't correspond to any text block
- Same bbox returned for multiple different fields on the same page

**Prevention:**
- **Separate retrieval heatmap from field bbox**: retrieval returns page+score; a second VLM pass ("quote the exact text and bbox for effective_date") returns field-level bbox.
- **Use Docling's layout bounding boxes** (from TableFormer / layout model) to snap VLM-returned regions to actual text blocks.
- **Validate bbox by cropping and re-reading**: crop image at bbox, run OCR or VLM on crop, check returned text matches extracted field value. Reject if no match.
- **Qwen3-VL bbox convention**: normalized to [0, 1000] range — do the coordinate conversion explicitly and test on a known example.

**Detection:** Eval script: for each field with bbox, crop image, OCR crop, measure substring containment of extracted value. Target >0.9.

---

### M9. Phase 1 to Phase 2 transition breaks Langfuse + eval continuity

**Phase:** P2
**Confidence:** MEDIUM (inferred from typical project evolution)

**What goes wrong:** Phase 1 logs queries with span names like `"retrieve_bm25"`, `"generate_answer"`. Phase 2 refactors to LangGraph nodes named `"agent_retrieve"`, `"agent_draft"`. Now you can't run aggregate latency/cost dashboards across phases, and the Phase 3 benchmark comparison loses the "apples-to-apples" Langfuse view.

**Warning signs:**
- Different Langfuse projects for P1 and P2
- Span names rename mid-project
- Trace tags don't include `phase: "1"` or `phase: "2"` from the start

**Prevention:**
- From P1 day 1, tag every trace: `{"phase": "1", "run_id": "<hash>", "doc_set_version": "v1"}`.
- Define span taxonomy upfront: `retrieval.*`, `generation.*`, `extraction.*`, `critic.*` — prefixes stable across phases.
- Single Langfuse project for the whole externship; filter by phase tag, not by project.
- Eval harness queries Langfuse by tag, outputs same CSV schema in both phases → direct diff possible in Phase 3.

**Detection:** Run Phase 3 comparison script against P1 traces today; if schema is incompatible, fix before P2 starts.

---

## Minor Pitfalls

Polish issues. Address during P3 or when encountered.

### m1. Qdrant local mode doesn't support concurrent access

**Phase:** P1
**Confidence:** HIGH (Qdrant docs)

**What:** Local-mode (embedded) Qdrant doesn't allow multiple processes/notebook cells accessing the same storage path simultaneously.
**Prevention:** Run Qdrant server mode (`docker run qdrant/qdrant`) even locally if you need parallel ingest workers. For Colab single-notebook use, local mode is fine.

### m2. Streamlit file_uploader limits (200 MB default)

**Phase:** P1
**Confidence:** HIGH (Streamlit docs)

**What:** Default max upload size is 200 MB; a pharma SDF folder can exceed this.
**Prevention:** Set `server.maxUploadSize = 1024` in `.streamlit/config.toml`. Document the limit for demo users.

### m3. Pydantic v2 `date` parsing rejects pharma date formats

**Phase:** P1
**Confidence:** MEDIUM

**What:** Pydantic's strict `date` parses ISO format by default. Pharma docs use `15-Mar-2022`, `March 15, 2022`, `15.03.2022`.
**Prevention:** Use `field_validator` with `dateutil.parser.parse` fallback + explicit date format whitelist. Log rejected date strings for schema refinement.

### m4. Docling Colab install conflicts with pre-installed torch

**Phase:** P1
**Confidence:** MEDIUM (general Colab dep hell)

**What:** `pip install docling` in Colab may downgrade/upgrade torch, breaking CUDA with pre-installed ColQwen2 dependencies.
**Prevention:** Pin versions in a `requirements.txt`; install in a specific order (docling first, then colpali-engine, then verify torch+cuda). Consider `uv pip install --resolution=lowest-direct` for predictable resolution.

### m5. Langfuse dashboard costs misleading when using Gemini

**Phase:** P2
**Confidence:** LOW (inferred from LLM cost tracking pitfalls)

**What:** Langfuse cost calculation depends on token counts and model pricing. Gemini 2.5 Flash pricing must be configured per model; incorrect or missing config shows $0 or wildly inflated costs.
**Prevention:** Manually verify cost-per-query against Google Cloud billing for one day, calibrate Langfuse model pricing config.

### m6. Risk-flag color thresholds baked in code, not configurable

**Phase:** P1 (design), P3 (polish)

**What:** Hardcoding "red >3yr, amber 2–3yr, green <2yr" means a reviewer asking "what if we change thresholds?" requires a code change during demo.
**Prevention:** Surface thresholds as Streamlit sidebar sliders bound to `st.session_state`; let demo reviewers tune live.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation | Severity |
|-------------|---------------|------------|----------|
| P1 Ingest | Docling memory leak (C3), stamped-doc OCR (M3) | Per-doc converter recreation + full-page OCR option | Critical |
| P1 Extraction | VLM hallucination (C4), schema mismatch (C7) | Grounded schema with verbatim spans + instructor retry | Critical |
| P1 Chatbot | Streamlit-LangGraph rerun (M4) | session_state for graph + sync stream | Moderate |
| P1 Eval | Small gold set instability (M5), single-annotator bias (M6) | ≥50 Qs, 3-run avg, self-reannotation | Moderate |
| P2 Visual retrieval | HNSW on multivectors (C1), T4 OOM (M7) | m=0 for colqwen vectors + batch_size=2 | Critical |
| P2 Critic loop | Self-correction regression (C5), infinite loop (M2) | Evidence-grounded critic + iteration cap + A/B gate | Critical |
| P2 Observability | Langfuse async gaps (M1), span-name drift (M9) | Context managers + phase tags from day 1 | Moderate |
| P2 Bbox citations | Retrieval heatmap ≠ field bbox (M8) | Separate VLM pass for field bbox + crop-verify | Moderate |
| P2/P3 Colab | Session timeout (C6), collection schema break (C2) | Resumable ingest + versioned collections | Critical |
| P3 Benchmark | Run-to-run variance (M5) | Report mean±stddev across 3 runs | Moderate |

---

## Sources

### IBM Docling
- [Docling GitHub — High memory usage processing large PDFs (#2829)](https://github.com/docling-project/docling/issues/2829) — HIGH confidence
- [Docling GitHub — `do_ocr=False` not disabling OCR (#2312)](https://github.com/docling-project/docling/issues/2312) — HIGH
- [Docling GitHub — Pluggable OCR stages (#2128)](https://github.com/docling-project/docling/issues/2128) — HIGH
- [Docling GitHub — Table extraction bug missing column (#2134)](https://github.com/docling-project/docling/issues/2134) — HIGH
- [Granite-Docling 258M on Hugging Face](https://huggingface.co/ibm-granite/granite-docling-258M) — HIGH
- [Docling official docs](https://docling-project.github.io/docling/) — HIGH

### ColQwen2 / ColPali
- [colpali-engine GitHub (illuin-tech/colpali)](https://github.com/illuin-tech/colpali) — HIGH
- [ColPali paper arXiv 2407.01449](https://arxiv.org/html/2407.01449v4) — HIGH
- [Vespa blog — Scaling ColPali to billions](https://blog.vespa.ai/scaling-colpali-to-billions/) — HIGH

### Qdrant
- [Qdrant — Multivectors and Late Interaction](https://qdrant.tech/documentation/tutorials-search-engineering/using-multivector-representations/) — HIGH
- [Qdrant — PDF retrieval at scale with ColPali/ColQwen](https://qdrant.tech/documentation/tutorials-search-engineering/pdf-retrieval-at-scale/) — HIGH
- [Qdrant 1.13 — GPU indexing & strict mode](https://qdrant.tech/blog/qdrant-1.13.x/) — HIGH
- [Qdrant ColBERT tracking issue #3684](https://github.com/qdrant/qdrant/issues/3684) — HIGH

### LangGraph
- [LangChain docs — GRAPH_RECURSION_LIMIT](https://docs.langchain.com/oss/python/langgraph/errors/GRAPH_RECURSION_LIMIT) — HIGH
- [LangGraph discussion — Agent-tool recursion #1725](https://github.com/langchain-ai/langgraph/discussions/1725) — HIGH
- [deepagents issue — SubAgent recursion_limit propagation #1698](https://github.com/langchain-ai/deepagents/issues/1698) — HIGH

### Langfuse
- [Langfuse discussion — Missing LLM spans in multi-worker #9236](https://github.com/orgs/langfuse/discussions/9236) — HIGH
- [Langfuse discussion — Isolated tracer provider spans #10591](https://github.com/orgs/langfuse/discussions/10591) — HIGH
- [Langfuse — Troubleshooting & FAQ](https://langfuse.com/docs/observability/sdk/troubleshooting-and-faq) — HIGH

### Streamlit + LangGraph
- [Streamlit issue — RuntimeError event loop closed with astream (#12076)](https://github.com/streamlit/streamlit/issues/12076) — HIGH
- [Streamlit discuss — Async LangGraph workflow](https://discuss.streamlit.io/t/using-streamlit-in-an-asynchronous-langgraph-workflow-graph/92510) — HIGH
- [Bridging LangGraph and Streamlit (Medium)](https://medium.com/@yigitbekir/bridging-langgraph-and-streamlit-a-practical-approach-to-streaming-graph-state-13db0999c80d) — MEDIUM

### VLM Hallucination & Confidence
- [VADE: Visual Attention Guided Hallucination Detection (ACL 2025)](https://aclanthology.org/2025.findings-acl.773.pdf) — HIGH
- [HalLoc: Token-level Localization of Hallucinations (CVPR 2025)](https://openaccess.thecvf.com/content/CVPR2025/papers/Park_HalLoc_Token-level_Localization_of_Hallucinations_for_Vision_Language_Models_CVPR_2025_paper.pdf) — HIGH
- [Trust but Verify: Programmatic VLM Evaluation (ICCV 2025)](https://openaccess.thecvf.com/content/ICCV2025/papers/Prabhu_Trust_but_Verify_Programmatic_VLM_Evaluation_in_the_Wild_ICCV_2025_paper.pdf) — HIGH
- [Know Your Limits: Abstention in LLMs (TACL)](https://direct.mit.edu/tacl/article/doi/10.1162/tacl_a_00754/131566/Know-Your-Limits-A-Survey-of-Abstention-in-Large) — HIGH
- [Self-RAG arXiv 2310.11511](https://arxiv.org/abs/2310.11511) — HIGH

### RAG Evaluation
- [RAG Evaluation Metrics & Frameworks 2026 (PremAI)](https://blog.premai.io/rag-evaluation-metrics-frameworks-testing-2026/) — MEDIUM
- [RAGAS — Faithfulness metric docs](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/faithfulness/) — HIGH
- [Vectara — Evaluating RAG with RAGAS](https://www.vectara.com/blog/evaluating-rag) — MEDIUM
- [Inter-Annotator Agreement survey arXiv 2603.06865](https://arxiv.org/html/2603.06865) — HIGH

### Colab
- [Colab FAQ](https://research.google.com/colaboratory/faq.html) — HIGH
- [colabtools issue — Drive mount timeout large folders (#1538)](https://github.com/googlecolab/colabtools/issues/1538) — HIGH
- [colabtools issue — Frequent disconnection with Drive mount (#3785)](https://github.com/googlecolab/colabtools/issues/3785) — HIGH

### Pydantic / Structured Output
- [Pydantic AI — Output docs](https://ai.pydantic.dev/output/) — HIGH
- [Make Gemini JSON output stricter (Medium)](https://medium.com/@andreasantoro.pvt/make-gemini-json-output-stricter-4feccf570d8c) — MEDIUM
- [pydantic-ai issue — Gemini structured streaming #1237](https://github.com/pydantic/pydantic-ai/issues/1237) — HIGH
