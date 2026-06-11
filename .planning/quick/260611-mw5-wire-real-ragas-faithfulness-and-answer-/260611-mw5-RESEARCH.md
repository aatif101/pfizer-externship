# Quick Task: Wire Real RAGAS (Faithfulness + Answer Relevancy) — Research

**Researched:** 2026-06-11
**Domain:** RAGAS 0.4.3 eval integration with Gemini judge on Windows / Python 3.11
**Confidence:** HIGH (install verified by dry-run; API verified against current ragas docs + Langfuse cookbook)

## Summary

ragas 0.4.3 ships **two parallel APIs**. The new `ragas.metrics.collections.*` API uses a native `llm_factory`/`embedding_factory` (instructor-based, OpenAI-shaped clients). The **legacy `ragas.metrics.*` API** (`Faithfulness`, `ResponseRelevancy` + `SingleTurnSample` + `await metric.single_turn_ascore(sample)`) is still present in 0.4.3 — it is marked deprecated ("removed in 1.0") but fully functional and emits only a DeprecationWarning. **Use the legacy per-sample API**: it is the cleanest fit for this codebase because it scores one sample at a time, so scores map deterministically back to `query_id` with no batch-ordering risk, and it accepts a LangChain-wrapped Gemini judge directly.

The Gemini judge is wired via `langchain-google-genai` (`ChatGoogleGenerativeAI` for the LLM, `GoogleGenerativeAIEmbeddings` for answer-relevancy embeddings), each wrapped in ragas' `LangchainLLMWrapper` / `LangchainEmbeddingsWrapper`. `Faithfulness` needs only the LLM; `ResponseRelevancy` needs **both** LLM and embeddings.

**Install is clean and verified** (`pip install --dry-run` against the live venv): `ragas==0.4.3` resolves with zero conflicts. It pulls a large but self-consistent LangChain 1.x stack (langchain-core 1.4.6, langchain 1.3.7, langgraph 1.2.4, instructor 1.15.1, datasets 5.0.0). `langchain-google-genai==4.2.5` also resolves cleanly on top. `single_turn_ascore` is **async**, and the eval runner is sync — so each call must be driven via `asyncio.run(...)` with `nest_asyncio.apply()` guarding the Streamlit-already-running-loop case.

**Primary recommendation:** Lazy-import the legacy API inside a single function `compute_ragas_quality(samples) -> per-query {faithfulness, answer_relevancy}`. Build one Gemini judge (`gemini-2.5-flash`, temp 0) + one embeddings model (`gemini-embedding-001`), loop per query calling `asyncio.run(metric.single_turn_ascore(sample))`, coerce NaN→None, and persist into `rag_eval_observations` keyed by `query_id`.

---

## User Constraints

No CONTEXT.md (quick task). Constraints derived from CLAUDE.md (locked stack):
- **ragas pinned `==0.4.3`** — exact pin; verified installable (see below). Do not float.
- **Judge LLM = `gemini-2.5-flash`** ("use Gemini 2.5 Flash as judge" — CLAUDE.md eval section). Cheap; matches the answer provider's default model.
- **langfuse pinned `>=3.0,<4.0`** — must not be disturbed. ragas 0.4.3 does **not** touch langfuse (verified: not in dependency tree).
- **pydantic v2** — ragas 0.4.3 requires `pydantic>=2.0.0`; venv has 2.13.3 (satisfied).
- **Windows + Python 3.11**, verification via `venv\Scripts\python.exe -m pytest` (never `/bin/bash`).

---

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RAGAS-1 | Compute real faithfulness per query | Legacy `Faithfulness(llm=...)` + `single_turn_ascore`; needs `user_input`, `response`, `retrieved_contexts` |
| RAGAS-2 | Compute real answer_relevancy per query | Legacy `ResponseRelevancy(llm=..., embeddings=...)`; needs same fields + embeddings |
| RAGAS-3 | Use Gemini as judge + embeddings | `ChatGoogleGenerativeAI` / `GoogleGenerativeAIEmbeddings` via langchain wrappers |
| RAGAS-4 | Persist scores keyed to query_id | Per-sample loop → `RAGEvalObservationRow(faithfulness=, answer_relevancy=, query_id=)` via `insert_rag_eval_observation` |
| RAGAS-5 | Lazy-import seam, offline-safe import | `import ragas` and `from langchain_google_genai import ...` inside the function only |

---

## Install Verification (CRITICAL — dry-run, NOT installed)

Command run in repo against the live venv (`venv\Scripts\python.exe`):

```
venv\Scripts\python.exe -m pip install "ragas==0.4.3" --dry-run
venv\Scripts\python.exe -m pip install "langchain-google-genai" --dry-run
```

**Result: `ragas==0.4.3` resolves cleanly. No conflicts, no incompatibilities reported.** [VERIFIED: pip dry-run, 2026-06-11]

Already satisfied by the venv (not re-installed): `numpy 2.4.4`, `pydantic 2.13.3`, `openai 2.32.0`, `typer 0.21.2`, `rich 15.0.0`, `pillow 12.2.0`, `networkx 3.6.1`, `tqdm`, `pandas 3.0.2`, `pyarrow 24.0.0`, `httpx 0.28.1`, `huggingface-hub 1.12.0`, `tenacity 9.1.4`.

**`ragas==0.4.3` would install these new transitive deps:**

| Package | Version pulled | Notes |
|---------|---------------|-------|
| ragas | 0.4.3 | target |
| datasets | 5.0.0 | required `>=4.0.0` |
| instructor | 1.15.1 | new collections-API LLM backend |
| langchain | 1.3.7 | ragas requires the `langchain` meta-pkg |
| langchain-core | 1.4.6 | |
| langchain-community | 0.4.2 | |
| langchain-openai | 1.3.0 | pulled by langchain meta; harmless |
| langchain-classic | 1.0.8 | |
| langchain-text-splitters | 1.1.2 | |
| langgraph | 1.2.4 | satisfies CLAUDE.md `>=1.1.0,<2.0` ✓ |
| langgraph-checkpoint / prebuilt / sdk | 4.1.1 / 1.1.0 / 0.4.2 | |
| langsmith | 0.8.14 | |
| tiktoken | 0.13.0 | |
| nest-asyncio | 1.6.0 | **needed anyway for our async-in-sync driver** |
| aiohttp 3.14.1, sqlalchemy 2.0.50, scikit-network 0.33.5, diskcache, orjson, uuid_utils, xxhash, zstandard, rich→14.3.4*, + misc | | *rich would be pinned by langchain stack |

**`langchain-google-genai` (latest = 4.2.5) also resolves cleanly** [VERIFIED: pip dry-run]. It pulls only `langchain-core 1.4.6` (same version ragas wants — no split), `google-genai>=1.65` (venv has 2.7.0, satisfied), plus langsmith/orjson/uuid_utils already pulled by ragas. **No conflict between ragas and langchain-google-genai.**

**Recommended install command for the executor:**
```
venv\Scripts\python.exe -m pip install "ragas==0.4.3" "langchain-google-genai>=4.0,<5"
```

**Notes / watch items:**
- This is a **large dependency addition** — the venv currently has NO langchain/langgraph at all. ~40 new packages. Acceptable per CLAUDE.md (langgraph is a locked, planned dep), but it is a real footprint change. Pin `langchain-google-genai>=4.0,<5` to avoid a future 5.x break.
- `langgraph 1.2.4` lands inside CLAUDE.md's `>=1.1.0,<2.0` band — good.
- `rich` would move 15.0.0 → 14.3.4 (langchain stack caps it). Minor; no known downstream break in this repo.
- Nothing touches `langfuse 3.14.6`, `google-genai 2.7.0`, `docling`, `streamlit`, `transformers 5.6.2` — all left in place.

---

## Standard Stack (for this task)

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| ragas | ==0.4.3 | Faithfulness + answer relevancy metrics | Locked by CLAUDE.md; verified installable |
| langchain-google-genai | >=4.0,<5 (4.2.5) | Gemini judge + embeddings adapters for ragas | ragas legacy API consumes LangChain LLM/embeddings objects; cleanest Gemini seam |
| nest-asyncio | 1.6.0 (pulled by ragas) | Allow `asyncio.run` inside Streamlit's running loop | `single_turn_ascore` is async; Streamlit already owns an event loop |

Gemini model strings (current, verified):
- **Judge LLM:** `gemini-2.5-flash` [CITED: langchain-google-genai docs; matches `DEFAULT_GEMINI_ANSWER_MODEL` in `src/rag/gemini.py`]
- **Embeddings:** `gemini-embedding-001` [VERIFIED: Google Developers Blog — GA model]. **Do NOT use `text-embedding-004`** — deprecated **Jan 14, 2026** [VERIFIED: ai.google.dev changelog + mem0 issue #3942]. Avoid `gemini-embedding-2-preview` (preview, unstable) shown in current LangChain docs for a compliance demo.

---

## Exact API — Code Snippets (legacy per-sample path)

All imports lazy (inside the function) to keep module import offline-safe, per the existing `src/rag/providers.py` / `src/rag/gemini.py` seam pattern.

### 1. Build the Gemini judge + embeddings (once per run)

```python
# Source: ragas docs (faithfulness/answer_relevance) + langchain-google-genai docs
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper

judge = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.0, api_key=api_key)
evaluator_llm = LangchainLLMWrapper(judge)

emb = GoogleGenerativeAIEmbeddings(model="gemini-embedding-001", google_api_key=api_key)
evaluator_embeddings = LangchainEmbeddingsWrapper(emb)
```

> `ChatGoogleGenerativeAI` takes `api_key=`; `GoogleGenerativeAIEmbeddings` takes `google_api_key=` (name differs — [ASSUMED] from langchain-google-genai convention; if it rejects, fall back to env var `GOOGLE_API_KEY`). Reuse the repo's `get_settings().gemini_api_key`.

### 2. Build the metrics

```python
from ragas.metrics import Faithfulness, ResponseRelevancy

faithfulness = Faithfulness(llm=evaluator_llm)
answer_relevancy = ResponseRelevancy(llm=evaluator_llm, embeddings=evaluator_embeddings)
```

> `ResponseRelevancy` is the current name for what older tutorials call `AnswerRelevancy`. Its `.name` attribute returns `"answer_relevancy"` — use that as the metric key for persistence.

### 3. Build a SingleTurnSample per query

```python
from ragas.dataset_schema import SingleTurnSample  # also re-exported from ragas

sample = SingleTurnSample(
    user_input=query_text,            # the gold query
    response=answer_text,             # answer_question(...).answer_text
    retrieved_contexts=[h.snippet for h in evidence_hits],  # list[str] of context chunks
)
```

`retrieved_contexts` must be a **list of strings**. In this repo, source them from the same retrieval hits the answer used (`AnswerResult.citations[*].snippet`, or re-run `retrieve_evidence`). Faithfulness needs `response` + `retrieved_contexts`; ResponseRelevancy needs `user_input` + `response` (+ embeddings).

### 4. Score per sample (async → driven from sync runner)

```python
import asyncio, math
import nest_asyncio
nest_asyncio.apply()  # safe no-op outside a running loop; required under Streamlit

def _score_one(metric, sample) -> float | None:
    try:
        value = asyncio.run(metric.single_turn_ascore(sample))
    except Exception:
        return None  # one bad sample must not sink the batch
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return float(value)

faith = _score_one(faithfulness, sample)        # -> float | None
relev = _score_one(answer_relevancy, sample)    # -> float | None
```

### 5. Persist keyed to query_id

```python
from src.eval.repository import RAGEvalObservationRow, insert_rag_eval_observation

insert_rag_eval_observation(db_path, RAGEvalObservationRow(
    source_run_id=source_run_id,
    query_id=query_id,
    status="observed",
    faithfulness=faith,            # None tolerated (repo coerces None safely)
    answer_relevancy=relev,
))
```

The existing `aggregate_quality_metrics(observations)` already averages `faithfulness` / `answer_relevancy` from these rows into `eval_metrics` — so once observations carry real scores, the existing `include_ragas=True` aggregation path in `retrieval_eval_runner.py` lights up with no change. `_coerce_nullable_float` in the repo already accepts `None` and rejects non-finite — NaN must be converted to `None` **before** insert (done in step 4).

---

## Architecture / Integration Notes

- **Where it plugs in:** `retrieval_eval_runner.py` currently has `_maybe_persist_ragas_placeholder_metrics` that only *averages already-present* observation scores — it never computes them. The new function is the **producer** of those observation rows. Recommended: a new module `src/eval/ragas_quality.py` exposing `compute_ragas_quality(db_path, *, source_run_id, samples) -> int` (count persisted). The runner calls it before `aggregate_quality_metrics`.
- **Per-sample, not batch.** Do **not** use ragas `evaluate(dataset=...)`. It returns aggregate/batch results and risks losing the row→`query_id` mapping. The per-sample `single_turn_ascore` loop keeps `query_id` association explicit and lets one failure be isolated.
- **Re-running the RAG answer:** the eval must produce a `response` per gold query. Call the existing `answer_question(db_path, query_text, provider=build_answer_provider("gemini"))` and feed `result.answer_text` + citation snippets into the sample. Abstained/provider-error answers (status != ANSWERED) should be recorded with `status` reflecting that and scores `None` — do not send abstention boilerplate to the judge as if it were a real answer.
- **Lazy-import seam confirmed feasible:** mirror `build_answer_provider` — top-level module import stays credential/SDK-free; `import ragas` and `from langchain_google_genai import ...` live inside the function body. Tests can monkeypatch the judge/embeddings or the whole compute function.

---

## Common Pitfalls

### Pitfall 1: Async inside Streamlit's running loop
**What goes wrong:** `asyncio.run()` raises `RuntimeError: asyncio.run() cannot be called from a running event loop` when the eval is triggered from a Streamlit callback.
**How to avoid:** `import nest_asyncio; nest_asyncio.apply()` once before scoring. It is pulled in transitively by ragas anyway. [VERIFIED: nest_asyncio docs; Windows ProactorEventLoop handled]

### Pitfall 2: NaN faithfulness scores
**What goes wrong:** Faithfulness returns `np.nan` (logged "No statements were generated from the answer") for short/abstained/out-of-context answers. NaN then fails `_coerce_nullable_float` (rejects non-finite → ValueError) and would sink the insert.
**How to avoid:** Coerce `nan`→`None` in the scorer wrapper (step 4) **before** building the row. [VERIFIED: ragas issues #733, #1403, #1651]

### Pitfall 3: One bad sample sinking the batch
**What goes wrong:** A judge timeout / 429 / parse failure on one query raises, aborting the whole eval run.
**How to avoid:** Wrap each `single_turn_ascore` in try/except → `None` (step 4). Per-sample isolation is the whole reason for not using batch `evaluate()`.

### Pitfall 4: Gemini rate limits on the judge
**What goes wrong:** Faithfulness + answer relevancy each make multiple LLM calls per sample (statement decomposition, NLI, question generation). ~17 gold queries × 2 metrics × several calls = bursty traffic → 429s on the free/low tier.
**How to avoid:** `gemini-2.5-flash` has generous limits, but score sequentially (the per-sample loop already does), set `temperature=0.0` for determinism, and consider a small `tenacity` retry around the score call (repo already depends on tenacity 9.1.4) for 429/503. Do not parallelize the loop.

### Pitfall 5: Deprecation warning noise
**What goes wrong:** Legacy `Faithfulness`/`ResponseRelevancy` emit a DeprecationWarning ("removed in 1.0"). Harmless on 0.4.3 (pinned), but may trip `-W error` test configs.
**How to avoid:** It is functional on 0.4.3. If tests run with warnings-as-errors, filter `DeprecationWarning` for the ragas module, or migrate to the `ragas.metrics.collections` API later (out of scope for this pin).

### Pitfall 6: text-embedding-004 deprecated
**What goes wrong:** Copy-pasted tutorials use `text-embedding-004` for answer-relevancy embeddings — **deprecated Jan 14, 2026**, will 404.
**How to avoid:** Use `gemini-embedding-001`. [VERIFIED: Google Developers Blog]

---

## Don't Hand-Roll

| Problem | Don't build | Use instead | Why |
|---------|-------------|-------------|-----|
| Faithfulness scoring | Custom NLI / statement-checking prompt | `ragas.metrics.Faithfulness` | Decomposition + NLI verification is exactly what ragas does; locked by CLAUDE.md |
| Answer relevancy | Cosine-sim of question vs answer by hand | `ragas.metrics.ResponseRelevancy` | Generates synthetic questions from the answer then embeds — non-trivial |
| Gemini→ragas adapter | Custom LLM wrapper implementing ragas' interface | `LangchainLLMWrapper(ChatGoogleGenerativeAI(...))` | Maintained adapter; instructor/collections path is the only alternative and is OpenAI-shaped |
| Async-in-sync bridge | Manual loop juggling | `nest_asyncio.apply()` + `asyncio.run` | Handles Windows ProactorEventLoop + Streamlit nesting |

---

## Environment Availability

| Dependency | Required by | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | runtime | ✓ | 3.11 | — |
| venv pip | install | ✓ | 24.0 | — |
| ragas 0.4.3 | metrics | ✗ (not yet installed) | resolves clean | none needed — installs cleanly |
| langchain-google-genai | Gemini judge | ✗ (not yet installed) | 4.2.5 resolves | none needed |
| GEMINI_API_KEY | judge + embeddings calls | ? (env) | — | required at runtime; eval must skip/record None if missing |
| Gemini API network | live judge calls | runtime | — | no offline fallback — this metric is inherently online |

**Blocking with no fallback:** Real RAGAS scoring needs the Gemini API + key at run time. The eval path must degrade to `status` markers / `None` scores (not crash) when the key is absent — mirror `GeminiAnswerProvider`'s `AnswerConfigurationError` handling.

---

## Validation Architecture

**Framework:** pytest (repo standard). Run via `venv\Scripts\python.exe -m pytest`.

| Req | Behavior | Test type | Command | Exists? |
|-----|----------|-----------|---------|---------|
| RAGAS-1/2 | scorer wrapper coerces float / NaN→None / exception→None | unit (mock metric) | `venv\Scripts\python.exe -m pytest tests/eval/test_ragas_quality.py -x` | ❌ Wave 0 |
| RAGAS-4 | scores persist keyed to query_id | unit (tmp_path sqlite) | same file | ❌ Wave 0 |
| RAGAS-5 | module import is offline-safe (no ragas/langchain import at import time) | unit | `... -k offline_import` | ❌ Wave 0 |

**Wave 0 gaps:**
- [ ] `tests/eval/test_ragas_quality.py` — mock the metric objects (inject fake `single_turn_ascore`) so tests stay offline; assert NaN→None, exception→None, query_id mapping, persistence. Follow the existing `client`/`client_factory` injection pattern from `src/rag/gemini.py`.
- [ ] Make the judge/embeddings injectable (param or factory) so no live Gemini call happens in tests.

---

## Assumptions Log

| # | Claim | Section | Risk if wrong |
|---|-------|---------|---------------|
| A1 | `GoogleGenerativeAIEmbeddings` uses kwarg `google_api_key` (vs `api_key`) | API §1 | Low — fall back to `GOOGLE_API_KEY` env; one-line fix |
| A2 | `ResponseRelevancy.name == "answer_relevancy"` | API §2 | Low — verify at runtime; only affects metric-key string |
| A3 | `SingleTurnSample` importable from both `ragas` and `ragas.dataset_schema` in 0.4.3 | API §3 | Low — `ragas.dataset_schema.SingleTurnSample` is the stable path |
| A4 | Legacy `Faithfulness`/`ResponseRelevancy` still present (not removed) in 0.4.3 | Summary | Medium — docs say "removed in 1.0", we pin 0.4.3 so present; confirm with one import smoke test post-install |

**Resolve A1–A4 with a 5-line post-install smoke test** (`python -c "from ragas.metrics import Faithfulness, ResponseRelevancy; from ragas.dataset_schema import SingleTurnSample; print(ResponseRelevancy.__name__)"`) before writing the full integration.

---

## Open Questions

1. **Where do `retrieved_contexts` come from for the sample?**
   - Known: must be `list[str]`; should be the contexts the answer actually used.
   - Recommendation: re-run `retrieve_evidence` (or reuse `answer_question` citations' snippets) per gold query so faithfulness judges against the real evidence set.

2. **How to handle abstained/provider-error answers?**
   - Recommendation: record the observation with a non-"observed" status and `None` scores; never send abstention boilerplate text to the judge.

---

## Sources

### Primary (HIGH)
- pip `--dry-run` against the live venv, 2026-06-11 — install resolution, transitive deps, no conflicts (`ragas==0.4.3`, `langchain-google-genai`)
- [ragas Faithfulness docs](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/) — legacy `Faithfulness` + `SingleTurnSample` + `single_turn_ascore`
- [ragas Response Relevancy docs](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/answer_relevance/) — `ResponseRelevancy`, collections vs legacy, embeddings required
- [ragas RAG eval getstarted](https://docs.ragas.io/en/stable/getstarted/rag_eval/) — `LangchainLLMWrapper`, `EvaluationDataset`/`evaluate` (the batch path we avoid)
- [Langfuse RAGAS cookbook](https://langfuse.com/guides/cookbook/evaluation_of_rag_with_ragas) — exact per-sample `single_turn_ascore` loop pattern
- [Google Developers Blog — Gemini Embedding GA](https://developers.googleblog.com/gemini-embedding-available-gemini-api/) — `gemini-embedding-001` GA
- [Gemini API changelog](https://ai.google.dev/gemini-api/docs/changelog) — `text-embedding-004` deprecation Jan 14 2026

### Secondary (MEDIUM)
- [langchain-google-genai PyPI](https://pypi.org/project/langchain-google-genai/) — `ChatGoogleGenerativeAI`, `GoogleGenerativeAIEmbeddings`
- [GoogleGenerativeAIEmbeddings integration docs](https://docs.langchain.com/oss/python/integrations/text_embedding/google_generative_ai) — constructor form (showed preview model — we override to GA `gemini-embedding-001`)
- [nest_asyncio](https://github.com/erdewit/nest_asyncio) — Windows ProactorEventLoop nesting
- ragas NaN issues [#733](https://github.com/explodinggradients/ragas/issues/733), [#1403](https://github.com/explodinggradients/ragas/issues/1403), [#1651](https://github.com/vibrantlabsai/ragas/issues/1651)

## Metadata
- **Install resolution:** HIGH — dry-run verified against live venv.
- **API shape:** HIGH — legacy per-sample path confirmed in current docs + Langfuse cookbook; A1–A4 are low-risk kwarg/name details to confirm with a post-install smoke test.
- **Pitfalls:** HIGH — NaN, async-loop, rate-limit, embedding-deprecation all verified against issues/changelogs.
- **Valid until:** ~2026-07-11 (ragas pinned to 0.4.3 freezes the API; langchain-google-genai floats within `<5`).
