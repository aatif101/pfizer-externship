# Phase 5 Visual Retrieval Diagnosis

Date: 2026-06-28

This is a diagnosis of the negative Colab L4 result recorded in
`05-04-SUMMARY.md`: the ColQwen2.5 visual tier ran end-to-end but made the
hybrid system worse than text-only, and the four `rq_ex3_*` image-only Cytiva
Certificate of Quality queries missed the correct page at top-5 for text,
visual, and fused retrieval.

The short conclusion:

- The failure is real. The target page is present, image-only, clean, and
  correctly labeled. The local text baseline reproduces the text-only scores.
- The Qdrant late-interaction architecture is mostly canonical. Pooling and
  vector config are not the first place I would spend engineering cycles.
- The highest-probability root cause is the runtime/model-loading stack used by
  the notebook: `colpali-engine==0.3.17` with Transformers 5.x. Upstream
  `colpali-engine` main now contains an unreleased ColQwen2/ColQwen2.5 checkpoint
  conversion fix for `model.embed_tokens` and `model.norm`, explicitly described
  in the changelog as preventing weights from being silently dropped and randomly
  reinitialized. The 0.3.17 wheel used in the run does not contain that mapping.
- A separate product-level problem is also present: equal-weight RRF let an
  unproven visual ranking hurt a strong text baseline. That explains the
  aggregate metric regression, but it does not explain the visual-only
  `rq_ex3` miss.
- Even after the model stack is fixed, the outstanding system should not rely on
  visual retrieval alone for exact pharma values. Best document-intelligence
  systems use OCR/VLM text extraction for scanned pages, text retrieval for exact
  terms and values, and visual late-interaction retrieval as a complementary
  page-level signal.

## 1. Architecture & Decisions Recap

### Problem the phase was meant to solve

The project has a structurally blind text tier: `src/retrieval/indexer.py`
indexes only pages whose `page_text` is non-empty. In the local database:

- Total pages: 78
- Pages with image blobs: 78
- Pages with non-empty text: 72
- `5543408c4dacc48b`, page `2`: `page_text` length `0`, `image_blob` length
  `271221`

That target page is a clean Cytiva Certificate of Quality image. It visibly
contains the `Certificate of Quality` title, Cytiva issuer mark, product name
`AKTA ready Gradient Flow Section With Inlets`, Date of Manufacture `20210126`,
and Expiration Date `20230126`. Text retrieval cannot retrieve it because the
text index never sees it. Visual retrieval was supposed to break that ceiling.

### Visual tier design

The implemented visual tier uses:

- Model: `vidore/colqwen2.5-v0.2`
- Runtime wrapper: `colpali-engine`
- Storage/search: Qdrant local mode
- Vectors per page:
  - `original`: full ColQwen2.5 multi-vector embedding, HNSW disabled
  - `mean_pooling_columns`: column-pooled multi-vector embedding
  - `mean_pooling_rows`: row-pooled multi-vector embedding
- Query plan:
  - Prefetch candidates against row and column pooled vectors
  - Rerank candidates using full `original` multi-vector MaxSim
- Fusion:
  - Existing text rank + visual rank are fused with reciprocal rank fusion
    using `k=60`
- Evaluation:
  - Page-level recall@5/10 and citation accuracy over `(doc_id, page_num)`

This design came from the Qdrant/ColPali optimization pattern, not from an
invented local approximation. Qdrant's tutorial uses named vectors
`original`, `mean_pooling_columns`, and `mean_pooling_rows`, disables HNSW on
the full multivector, uses `MultiVectorComparator.MAX_SIM`, and performs pooled
prefetch followed by reranking with `original` ([Qdrant tutorial][qdrant-pdf]).

### Why each decision made sense at the time

**ColQwen2.5.** The project chose the ColPali-family visual retrieval approach
because it retrieves directly over page images, avoiding an OCR bottleneck for
scanned/stamped PDFs. The ColPali paper frames the core benefit this way:
document pages are embedded from images with a VLM and retrieved by late
interaction, rather than by text extraction first ([ColPali paper][colpali]).
`vidore/colqwen2.5-v0.2` is a Qwen2.5-VL-3B-based checkpoint, and the model card
shows canonical usage through `ColQwen2_5`, `ColQwen2_5_Processor`,
`process_images`, `process_queries`, and `score_multi_vector`
([model card][colqwen-card]).

**Qdrant multivectors + MaxSim.** The model emits many 128-dimensional vectors
per page. Qdrant supports multivector search with the MaxSim late-interaction
comparator. This matches the model's scoring family: query token vectors score
against page token vectors by maximum similarity and aggregation.

**Mean-pooled row/column prefetch.** HNSW on every page-token vector is expensive.
Qdrant recommends mean pooling rows and columns, searching those smaller
multivectors first, then reranking candidates with the original full
multivector. In their optimization writeup, this preserves NDCG while giving a
large speedup on their benchmark ([Qdrant optimization][qdrant-opt]).

**RRF fusion.** RRF is a defensible first fusion strategy when two rankers have
different score scales. It avoids score calibration by using rank only. That was
reasonable as a first integration choice, but questionable in hindsight because
it gives an unvalidated visual ranker the same rank-level authority as the
already-working text tier.

**Page-level metrics.** Recall@k and citation accuracy over `(doc_id, page_num)`
are exactly the right first metrics for this phase. The phase claim was "the
system finds the right source page." It was not claiming answer generation or
span extraction yet.

### Questionable decisions in hindsight

1. **The notebook accepted a major runtime-stack change without a golden quality
   gate.** The original project rationale pinned Transformers below 4.50 because
   ColQwen initialization was known to be sensitive. The final notebook moved to
   `colpali-engine==0.3.17` and Transformers 5.x because of resolver pressure.
   That was not just a dependency update; it changed the model-loading substrate.

2. **The proof cell measured only hit/miss at top-5.** It did not record the
   target page's full visual rank, score, score gap, nearest false positives, or
   whether direct ColQwen scoring agreed with Qdrant. Without those, the failed
   result is real but under-instrumented.

3. **Equal-weight RRF was used before visual retrieval had proven additive
   recall.** If visual is weak, rank-only fusion can demote correct text hits.
   That is exactly what the aggregate metrics suggest happened.

4. **No OCR fallback was added for empty text pages.** For exact values like
   manufacture and expiration dates, OCR/VLM text extraction is not optional if
   the goal is a compliance-grade system.

## 2. Stage-by-Stage Root-Cause Analysis

### 2.1 Corpus, page identity, and gold labels

**What we do.** The visual notebook loads all pages with `image_blob`, producing
78 Qdrant points. Text retrieval indexes only non-empty `page_text`, so the
Cytiva page is excluded from the text tier. Gold targets for all four `rq_ex3_*`
queries are `('5543408c4dacc48b', 2)`.

**Best practice.** For this phase, evaluate page identity directly. Before
debugging the model, confirm the page exists, the page number convention is
consistent, and the gold page visibly contains the queried evidence.

**Diagnosis.** Not the root cause. The target page is a clean, legible page
image. It is image-only in the text tier and present in the visual corpus.
The page numbering is consistently 0-indexed in the DB, gold targets, notebook,
and proof cell.

**Confidence.** High.

**Evidence.** Local DB inspection found 78 total image pages and `page_text` length
0 for the target. The extracted target image visibly contains the queried
fields.

### 2.2 Evaluation harness

**What we do.** `src/eval/retrieval_metrics.py` computes page-level recall@k by
intersecting gold pages with retrieved pages. Citation accuracy is binary per
query: whether any cited page matches any gold page.

**Best practice.** For a retrieval layer, page-level recall is the correct
primitive. It is intentionally stricter than "some document from the same file"
and simpler than answer faithfulness.

**Diagnosis.** Not the root cause. The metric is measuring the right thing. It
also explains why recall and citation accuracy are identical in this run: each
gold query has one target page, and the "citations" are the same top-k page
identities.

**Confidence.** High.

**Important count conversion.** With 17 one-target queries:

- Text recall@5 `0.647` = 11/17 queries hit.
- Fused recall@5 `0.529` = 9/17 queries hit.
- Text recall@10 `0.706` = 12/17 queries hit.
- Fused recall@10 `0.647` = 11/17 queries hit.

So the aggregate regression is "two top-5 wins lost and one top-10 win lost,"
not a mysterious continuous-score effect. The larger issue remains: visual
retrieval added zero `rq_ex3` wins.

### 2.3 Page rasterization and resolution

**What we do.** The visual tier uses the page `image_blob` stored by the ingest
pipeline. All local page images inspected are RGB and `1275 x 1651`, consistent
with roughly 150 DPI letter/A4-style rasterization. The target page is visually
legible at this resolution.

**Best practice.** ColPali/ColQwen-style systems generally let the model
processor resize the full page under a visual-token budget. The model card for
`vidore/colqwen2.5-v0.2` notes dynamic-resolution inference and gives examples
using `max_num_visual_tokens=1024` ([model card][colqwen-card]). Qwen2.5-VL
itself is designed for dynamic-resolution visual processing and document
understanding ([Qwen2.5-VL report][qwen25]).

**Diagnosis.** Plausible contributor, unlikely primary root cause. 150 DPI is
not obviously wrong for page-level retrieval, and the target page has large
semantic anchors: title, vendor, product name, and dates. However, exact numeric
fields are smaller and may be vulnerable to downsampling. If the processor's
effective token cap is lower than expected, the model may not preserve enough
fine text detail for date queries.

**Confidence.** Medium-low as the main cause; medium as an improvement lever.

**What would confirm it.** On a known-good model stack, increasing
`max_num_visual_tokens` and/or re-rasterizing at higher DPI materially improves
the target rank for `rq_ex3_expiry` and `rq_ex3_mfg` while leaving title/vendor
queries already strong.

### 2.4 Image embedding and model loading

**What we do.** `src/retrieval/visual/embedder.py` loads
`ColQwen2_5.from_pretrained("vidore/colqwen2.5-v0.2", torch_dtype=bfloat16,
device_map=...)` and `ColQwen2_5_Processor.from_pretrained(...)`. It uses
`processor.process_images(...)`, `torch.no_grad()`, and `model(**batch)`.

**Best practice.** Use the processor and model class matching the checkpoint.
Also treat missing/unexpected checkpoint keys as a quality-critical failure, not
just a warning, especially for ColQwen/Transformers compatibility transitions.

**Diagnosis.** This is the highest-probability root cause.

The run used:

- `colpali-engine==0.3.17`
- `transformers==5.12.0`
- `torch==2.11.0+cu128`

That is materially different from the project rationale, which warned against
ColQwen/Transformers initialization drift, and from the model card's stated
training/evaluation environment (`colpali-engine==0.3.7`,
`transformers>4.45.0`) ([model card][colqwen-card]).

The package compatibility archaeology matters:

| colpali-engine | ColQwen2.5 class? | Transformers requirement from wheel metadata |
| --- | --- | --- |
| 0.3.7 | No | `>=4.47,<4.48` |
| 0.3.9 | Yes | `>=4.50,<4.51` |
| 0.3.10 | Yes | `>=4.51.1,<4.52` |
| 0.3.11 / 0.3.12 | Yes | `>=4.53.1,<4.54` |
| 0.3.13 | Yes | `>=4.53.1,<4.58` |
| 0.3.14 | Yes | `>=5.0,<6` |
| 0.3.17 | Yes | `>=5.3,<6` |

So "go back to `colpali-engine==0.3.7`" is not directly viable from PyPI because
that wheel does not contain `ColQwen2_5`. The earliest ColQwen2.5-capable PyPI
wheel is 0.3.9, and the closest pre-Transformers-5 stack is
`colpali-engine==0.3.9` with `transformers>=4.50,<4.51`.

More importantly, current upstream `colpali-engine` main has an unreleased
`ColQwen2_5` checkpoint conversion mapping that 0.3.17 lacks:

- 0.3.17 maps `model.layers -> language_model.layers`
- Current main additionally maps:
  - `model.embed_tokens -> language_model.embed_tokens`
  - `model.norm -> language_model.norm`

The upstream changelog says this fix prevents ColQwen2/ColQwen2.5 weights from
being silently dropped and randomly reinitialized when loading with the
Transformers 5 layout ([colpali changelog][colpali-changelog]). The current main
source contains the added mappings ([current source][colpali-current-source]).

That symptom class matches this run extremely well: the model loads, produces
128-dimensional embeddings, and the pipeline runs cleanly, but retrieval quality
is unexpectedly poor on an easy page.

**Confidence.** High as a leading suspect; not yet proven until a loading audit
or compatibility-matrix rerun confirms it.

**What would confirm it.**

- `output_loading_info=True` or warning capture on 0.3.17 shows missing or
  unexpected keys for `language_model.embed_tokens`, `language_model.norm`, or
  related base/adapter weights.
- Installing from current `colpali-engine` main, or patching the 0.3.17 mapping,
  makes the `rq_ex3` target rank improve sharply without changing Qdrant,
  pooling, or fusion.
- An early 4.x ColQwen2.5 stack, especially 0.3.9 + Transformers 4.50.x, also
  improves rank.

### 2.5 Query embedding and prompt format

**What we do.** `embed_queries()` calls `processor.process_queries([query])`,
moves the batch to the model device, and calls `model(**batch)`. In 0.3.17,
`process_queries` is inherited from the shared visual retriever processor:
it adds the query prefix and default query augmentation suffix, then calls the
model-specific `process_texts`.

**Best practice.** Use `process_queries`, not a raw tokenizer call. The model
card uses the same public entry point. Query text should be short enough to
focus the retriever, and exact field-value queries often benefit from multiple
canonical rewrites.

**Diagnosis.** The code is using the correct API. The query wording may still be
suboptimal. The `rq_ex3` queries are natural-language instructions, for example
"Find Expiration Date 20230126 for AKTA ready Gradient Flow Section." A visual
page retriever may not behave like exact OCR search over small numeric strings.

This does not explain the vendor/title query misses by itself. The query
"Find the Certificate of Quality page identifying Cytiva as issuer" should have
large visual/semantic anchors. If that query is also poor, model-load quality is
more likely than prompt wording alone.

**Confidence.** Low as primary root cause; medium as an optimization lever.

**What would improve it.**

- Generate compact retrieval queries:
  - `Cytiva Certificate of Quality AKTA ready Gradient Flow Section`
  - `AKTA ready Gradient Flow Section 20210126 20230126`
  - `Cytiva expiration date 20230126`
- Embed several rewrites and aggregate by max score or RRF within the visual
  modality before fusing with text.

### 2.6 Pooling implementation

**What we do.** `mean_pool_rows_cols()` selects image-token embeddings with
`image_mask`, reshapes them as `(n_patches_x, n_patches_y, dim)`, averages
rows/columns, and appends non-image prompt tokens to the pooled vectors.

**Best practice.** This mirrors Qdrant's documented pattern: compute patch grid
with the processor, use `get_image_mask`, reshape image embeddings, mean-pool
rows and columns, then append special/non-image embeddings before indexing
([Qdrant tutorial][qdrant-pdf]).

**Diagnosis.** Probably not the root cause. The implementation matches the
Qdrant reference closely. The axis names are easy to distrust, but the local call
passes `PIL.Image.size` as `(width, height)`, and 0.3.17's processor calls
`smart_resize(width=image_size[0], height=image_size[1])`, then returns
`n_patches_x = width_new / patch / merge` and `n_patches_y = height_new / patch /
merge`. That is internally consistent.

Most importantly, this corpus has only 78 pages while the query uses
`prefetch_limit=200`. If Qdrant returns the union of all available row/column
prefetch hits, the final `original` rerank should see every page. In that case,
pooling cannot be the reason the target misses top-5; the full multivector score
is.

**Confidence.** Medium-high that pooling is not the main cause. Still worth a
parity check because dynamic patch grids are a sharp edge.

**What would confirm it.**

- Run direct in-memory `processor.score_multi_vector(query, all_page_embeddings)`
  over all 78 pages and compare ranks to Qdrant with `prefetch_limit >= 78` and
  `search_limit >= 78`.
- If rankings match, pooling/Qdrant prefetch are not the cause.
- If rankings diverge, inspect prefetch union semantics and patch-grid reshape.

### 2.7 Qdrant vector configuration

**What we do.** `src/retrieval/visual/collection.py` configures all three named
vectors as size 128, cosine distance, multivector MaxSim. It disables HNSW on
the full `original` vector and leaves HNSW enabled for pooled vectors.

**Best practice.** This is exactly the Qdrant ColPali pattern. ColQwen2.5's
projected embeddings are L2-normalized in `colpali-engine`, and Qdrant uses
cosine distance with MaxSim for late interaction.

**Diagnosis.** Not an obvious bug. Cosine + L2-normalized vectors is appropriate.
The Qdrant config mirrors official guidance.

**Confidence.** High that vector config is not the primary failure.

### 2.8 Two-stage prefetch and rerank

**What we do.** `build_query_payload()` creates two `Prefetch` blocks with
`limit=200`, one using `mean_pooling_columns` and one using `mean_pooling_rows`,
then asks Qdrant to rerank with `using="original"` and `limit=TOP_K`.

**Best practice.** Use pooled vectors only to select candidates; use the full
multivector for final ranking. For small corpora, set candidate limits high
enough to cover the whole corpus during debugging.

**Diagnosis.** Probably not the primary cause, but under-instrumented. With 78
pages and a prefetch limit of 200, the candidate stage should not filter out the
target. However, the notebook only requested top-10 final results. We do not
know whether the target was rank 11, rank 25, or rank 78.

**Confidence.** Medium.

**What would confirm it.**

- Query with `search_limit=78` and record the target rank and score for all
  `rq_ex3_*` queries.
- Compare direct ColQwen score ordering vs Qdrant ordering.

### 2.9 Fusion

**What we do.** `rrf_fuse()` gives visual rank and text rank equal weight:
`1 / (k + rank + 1)` for both modalities.

**Best practice.** RRF is a good baseline only when both rankers are trusted to
contribute useful signal. Production hybrid retrieval generally calibrates,
weights, gates, or learns fusion so a weak modality cannot damage a strong one.

**Diagnosis.** Fusion explains the aggregate fused-vs-text regression, but not
the visual-only failure. If visual returns irrelevant pages high in the list,
equal-weight RRF can push text-only correct pages out of top-5. Because text-only
already hits 11/17 at top-5 and visual contributes no `rq_ex3` wins, equal RRF
has more downside than upside in this run.

**Confidence.** High for explaining the metric regression; zero for explaining
why visual misses the target.

**Fix direction.** Use text-first gated fusion:

- Preserve text-only ordering unless visual provides a strong reason to insert a
  page.
- Give a boost to visual hits whose `page_text` length is zero, because those are
  exactly the pages text cannot retrieve.
- Tune visual weight on the gold set, and require fused recall to be no worse
  than text-only before accepting the modality.

### 2.10 Text baseline

**What we do.** SQLite FTS/BM25-style retrieval over extracted page text. It
cannot retrieve image-only pages by construction.

**Best practice.** Keep it. It is the strongest verified retrieval path today.
For scanned pages, add OCR/VLM text into the same indexing contract rather than
expecting visual embeddings alone to handle exact compliance values.

**Diagnosis.** The baseline is doing its job. The architecture needs to extend
text coverage to scanned pages and use visual retrieval as a complementary
signal.

**Confidence.** High.

## 3. SOTA Research Findings With Sources

### 3.1 ColPali-family visual retrieval is real, but it is page retrieval, not magic OCR

The ColPali paper proposes indexing document page images directly with a VLM and
late interaction, avoiding a brittle OCR-first pipeline for retrieval
([ColPali paper][colpali]). That is the right family for scanned pharma PDFs.

However, it is still a retrieval model. It is optimized to rank pages, not to
guarantee exact lookup of every small numeric field. The `vidore/colqwen2.5-v0.2`
model card reports strong but imperfect retrieval benchmark scores; for example,
DocVQA recall@5 is below perfect even in the model's own results table
([model card results][colqwen-results]). This matters because the `rq_ex3_expiry`
and `rq_ex3_mfg` queries are exact-value lookup tasks.

Project correlation:

- They do: use visual embeddings to retrieve pages when text extraction is
  unavailable or lossy.
- We do: exactly that.
- Gap: our use case also needs exact compliance values. Visual page retrieval
  should identify the page; OCR/VLM extraction should carry exact field search
  and answer grounding.

### 3.2 The Qdrant row/column pooled architecture is the right optimization

Qdrant's official ColPali tutorial uses three named vectors:

- `original`
- `mean_pooling_columns`
- `mean_pooling_rows`

It disables HNSW for the full original multivector, enables MaxSim, and uses
pooled prefetch followed by full-vector reranking ([Qdrant tutorial][qdrant-pdf]).
The Qdrant optimization blog explains the memory/performance reason and reports
that row/column mean pooling preserves retrieval quality on their benchmark
while speeding search substantially ([Qdrant optimization][qdrant-opt]).

Project correlation:

- They do: row/column mean-pool prefetch + full multivector rerank.
- We do: same config and query shape.
- Expected metric movement from changing this first: low. This is unlikely to
  rescue `rq_ex3` unless a local implementation bug is found by direct
  score-vs-Qdrant parity testing.

### 3.3 The exact ColQwen2.5 runtime stack is unstable enough to be quality-critical

The model card says `vidore/colqwen2.5-v0.2` is based on Qwen2.5-VL-3B-Instruct,
initialized from `vidore/colqwen2.5-base`, and trained with
`colpali-engine==0.3.7` and `transformers>4.45.0`
([model card][colqwen-card]). The PyPI 0.3.7 wheel does not expose
`ColQwen2_5`, so the public package history is messy; nevertheless, the model's
reference stack is clearly pre-Transformers-5.

The run's stack used `colpali-engine==0.3.17`, whose PyPI metadata requires
`transformers>=5.3,<6` ([PyPI 0.3.17][colpali-pypi-0317]). The upstream
changelog now contains an unreleased fix for ColQwen2/ColQwen2.5 checkpoint
conversion that prevents weights from being silently dropped and randomly
reinitialized ([colpali changelog][colpali-changelog]). Current main source shows
the additional mappings for `model.embed_tokens` and `model.norm`
([current source][colpali-current-source]).

Project correlation:

- They fixed: ColQwen2/2.5 loading under the newer layout.
- We ran: the latest PyPI release before that fix.
- Expected metric movement if this is the root cause: high. A retrieval model
  with randomly reinitialized token embedding/norm components can still produce
  correctly shaped vectors and pass smoke tests while losing semantic alignment.

### 3.4 Transformers now has native ColQwen2 retrieval support, but that is an escape hatch

Hugging Face Transformers documents native `ColQwen2ForRetrieval` usage,
including `get_image_embeddings`, `get_text_embeddings`, and `score_retrieval`
([Transformers ColQwen2 docs][hf-colqwen]). This is relevant because it suggests
the ecosystem is moving the ColQwen path closer to core Transformers.

Project correlation:

- Locked stack says `colpali-engine`, so this is not the immediate Phase 5 fix.
- If `colpali-engine` remains unstable for ColQwen2.5, a future spike could
  compare native Transformers retrieval on a converted checkpoint to the
  colpali-engine path.

### 3.5 OCR/VLM text extraction is not a fallback of shame; it is how compliance systems get exactness

Docling's VLM pipeline is designed for document conversion using Granite-Docling
([Docling VLM pipeline][docling-vlm]). The Granite-Docling model card describes
OCR and structural document-conversion capabilities for text, tables, formulas,
and layout ([Granite-Docling model][granite-docling]). Docling also supports
forcing full-page OCR for scanned pages ([Docling OCR example][docling-ocr]).

Project correlation:

- They do: convert scanned/visual pages into structured text/DoclingDocument
  representations.
- We do: rely on pre-existing `page_text`; empty pages remain empty.
- Expected metric movement: high on `rq_ex3`. If OCR/VLM extraction adds the
  visible title/vendor/product/date strings into the text index, the existing
  text retriever should be able to retrieve the page for exact-value queries.

### 3.6 Best hybrid systems use modality-specific guardrails

The core lesson from this run is not "visual retrieval is bad." It is "a visual
ranker that has not proven additive recall should not be allowed to demote a
working text ranker." Rank fusion is useful, but rank-only equal weighting is a
baseline, not a safety policy.

Project correlation:

- We used equal RRF.
- We should use gated/weighted fusion:
  - text-first by default,
  - visual boost for image-only pages,
  - visual insertion only when score/rank evidence is strong,
  - acceptance criterion that fused recall is never below text-only on the gold
    set.

## 4. Ranked Recommendations

### Almost Certainly the Bug / Highest Leverage

#### 1. Audit and fix the ColQwen2.5 loading stack before any other tuning

**Expected impact.** High. This is the only hypothesis that explains "clean run,
correct shapes, bad retrieval on an easy page" while being supported by upstream
code changes.

**Effort.** Medium. One Colab rerun after adding load diagnostics and either
installing from current `colpali-engine` main or pinning an early ColQwen2.5
stack.

**Risk.** Medium. Installing from main can introduce other changes. Early
0.3.9/Transformers 4.50 may have different Qwen2.5-VL bugs. That is why this
should be run as a small compatibility matrix, not a blind permanent pin.

**Why.** The upstream changelog explicitly names silently dropped and randomly
reinitialized ColQwen2/ColQwen2.5 weights. The current main source has mappings
that 0.3.17 lacks. This is too aligned with the observed failure to ignore.

**Concrete action.**

- Add a model-loading audit cell:
  - print exact versions,
  - capture missing/unexpected checkpoint keys,
  - fail if critical language model, adapter, or projection keys are missing,
  - print `model.__class__`, processor class, `model.dim`, patch size, merge
    size, visual-token cap, and image grid for the target page.
- Compare at least:
  - current baseline: 0.3.17 + Transformers 5.12,
  - `colpali-engine` current main at the commit containing the new
    `embed_tokens`/`norm` mappings,
  - earliest PyPI ColQwen2.5-capable pre-Transformers-5-ish stack:
    0.3.9 + Transformers 4.50.x.

**Success criteria.**

- No critical missing/unexpected keys.
- `rq_ex3_doc_type` and `rq_ex3_vendor` target rank <= 5 visually.
- `rq_ex3_expiry` and `rq_ex3_mfg` target rank <= 10 visually, preferably <= 5.
- Visual-only recall adds at least one image-only win; after gated fusion, fused
  recall is not below text-only.

#### 2. Add direct scorer-vs-Qdrant parity diagnostics

**Expected impact.** High diagnostic value, low direct product impact.

**Effort.** Low-medium.

**Risk.** Low.

**Why.** It separates model quality from Qdrant/pooling mechanics. With only 78
pages, direct all-pairs MaxSim is cheap enough on L4 for diagnostics.

**Concrete action.**

- Save all page embeddings.
- For each gold query, compute direct `processor.score_multi_vector(q, pages)`.
- Query Qdrant with `prefetch_limit=78` and `search_limit=78`.
- Record for each `rq_ex3` query:
  - target rank in direct scoring,
  - target rank in Qdrant,
  - target score,
  - top-10 false positives with filenames/page numbers,
  - score gap between target and rank 1/5/10.

**Success criteria.**

- If direct and Qdrant ranks match, stop suspecting Qdrant first.
- If they diverge materially, inspect pooling/prefetch/serialization.

### Would Make the System Outstanding

#### 3. Add OCR/VLM text extraction for empty or low-text pages, then index it

**Expected impact.** Very high for compliance retrieval. This is the most likely
way to make exact manufacture/expiration/date/vendor queries robust.

**Effort.** Medium-high. The project already chose Docling and Granite-Docling,
so this is aligned with the locked stack.

**Risk.** Medium. OCR/VLM extraction can hallucinate or misread dates, so store
provenance, page image references, and confidence/validation metadata.

**Why.** Visual retrieval should find source pages; text retrieval should handle
exact strings. The target page visibly contains the strings. Once extracted,
SQLite FTS can retrieve them. This turns the current structural blind spot into
ordinary text retrieval.

**Concrete action.**

- For pages with empty `page_text` or below a text-length threshold:
  - run Docling VLM/OCR conversion,
  - persist OCR/VLM text separately from original extracted text,
  - record source (`docling_vlm`, `ocr`, etc.), timestamp, and page image hash,
  - index combined text with a field indicating generated/OCR provenance.
- Add a dashboard flag for OCR-derived evidence so users understand the source.

**Success criteria.**

- The four `rq_ex3_*` queries hit the target page at text top-5 after OCR
  indexing.
- Text-only recall@5 improves above the current 11/17 count without reducing
  existing text hits.
- The answer layer cites the image page and can quote/extract the exact visible
  values with page provenance.

#### 4. Replace equal RRF with gated or weighted fusion

**Expected impact.** High for preventing regressions; medium for improving recall
unless visual retrieval becomes good.

**Effort.** Low-medium.

**Risk.** Low if evaluated against text-only as a hard baseline.

**Why.** Equal RRF made the fused system worse because visual had no proven
additive signal. A hybrid system should degrade gracefully.

**Concrete action.**

Start with a deterministic policy:

- If text has >= N high-confidence hits and none of the top visual hits are
  image-only pages, return text-first.
- If a visual hit has `page_text_len == 0`, allow it to enter high in the fused
  list.
- Otherwise use weighted RRF with `text_weight > visual_weight`, tuned on the
  gold set.

**Success criteria.**

- Fused recall@5 and recall@10 are never below text-only on the 17-query gold
  set.
- Any visual gain on image-only queries is retained in fused results.

#### 5. Add query canonicalization and multi-query visual retrieval

**Expected impact.** Medium. Likely helps exact-value and product-name queries;
not a substitute for fixing model loading.

**Effort.** Low-medium.

**Risk.** Low if queries and ranks are logged.

**Why.** The model card and ColPali usage treat queries as retrieval text, not
verbose instructions. Pharma queries mix document type, product, vendor, field
name, and field value. A single phrasing can underweight the visual anchor.

**Concrete action.**

For each user/gold query, generate 2-4 retrieval-specific variants:

- entity/document variant,
- exact value variant,
- vendor/product variant,
- field-name variant.

Aggregate visual candidates within the visual modality before cross-modal fusion.

**Success criteria.**

- On a fixed model stack, target visual rank improves for at least two
  `rq_ex3` queries.
- No aggregate visual recall drop on the full 17-query set.

#### 6. Tune visual token budget and raster source after the loader is fixed

**Expected impact.** Medium. Could help exact small text; unlikely to fix a
corrupted model load.

**Effort.** Medium.

**Risk.** Medium due to L4 memory and indexing latency.

**Why.** The target page is legible at 150 DPI, but small numeric dates may be
lost under a tight token budget. ColQwen2.5 supports dynamic resolution, and the
processor exposes `max_num_visual_tokens`.

**Concrete action.**

After stabilizing model loading, compare:

- existing stored images,
- higher-DPI rerasterization from source PDFs if available,
- `max_num_visual_tokens` values such as 768, 1024, and 1280,
- target page image-grid dimensions and embedding token counts.

**Success criteria.**

- Better target ranks for exact numeric queries without L4 OOM.
- No loss on title/vendor queries.

### Nice-to-Have / Later

#### 7. Add a persistent visual retrieval run report artifact

**Expected impact.** Medium for future debugging.

**Effort.** Low.

**Risk.** Low.

**Why.** The current run artifact records headline metrics but not enough
evidence to diagnose rank failures quickly.

**Concrete action.**

Save a JSON/Markdown report with:

- version triple,
- loading diagnostics,
- point count,
- per-query target ranks for text, visual, fused,
- top-10 visual hits with scores,
- target score percentile,
- example thumbnails or page metadata for false positives.

#### 8. Add visual retrieval acceptance tests around the Cytiva target

**Expected impact.** Medium as a regression guard.

**Effort.** Low after the notebook produces run artifacts.

**Risk.** Low.

**Why.** The exact failure should become a golden smoke test. Shape checks are
not enough for retrieval models.

**Concrete action.**

Store a small non-sensitive image fixture if allowed, or keep a Colab-only
acceptance cell requiring the `rq_ex3` ranks to meet thresholds before claiming
visual success.

## 5. Proposed Experiment Plan With Success Criteria

### Experiment 0: Loading audit

**Goal.** Determine whether the current 0.3.17/Transformers 5.12 stack is
silently missing or reinitializing critical ColQwen2.5 weights.

**Method.**

- Load `vidore/colqwen2.5-v0.2` with the current notebook stack.
- Capture all load warnings and missing/unexpected key metadata.
- Specifically inspect keys containing:
  - `embed_tokens`
  - `norm`
  - `language_model`
  - `model.layers`
  - `custom_text_proj`
  - LoRA adapter target modules
- Repeat with current `colpali-engine` main or a local patch containing the
  `model.embed_tokens` and `model.norm` mappings.

**Confirming result.**

- If 0.3.17 reports missing/unexpected critical keys and current main does not,
  the root cause is effectively confirmed.

**Refuting result.**

- If both stacks load with identical clean key reports, the version hypothesis
  weakens and attention moves to direct scoring, resolution, and query
  formulation.

### Experiment 1: Compatibility matrix on direct visual ranking

**Goal.** Find a stack that retrieves the target page before touching fusion.

**Method.**

Run the same 78 page embeddings and 17 queries under:

1. Baseline: `colpali-engine==0.3.17`, Transformers 5.12.
2. Patched/current main `colpali-engine`, Transformers 5.12.
3. Early ColQwen2.5 PyPI stack: `colpali-engine==0.3.9`,
   Transformers 4.50.x.
4. Optional: `colpali-engine==0.3.10` or 0.3.13 to isolate pre-5 behavior.

For each stack, compute direct all-page MaxSim ranks without Qdrant first.

**Measure.**

- Visual recall@5/10.
- Target rank and score for each `rq_ex3_*` query.
- Whether title/vendor queries behave differently from exact-date queries.

**Success criteria.**

- A viable stack must put the target page in visual top-5 for
  `rq_ex3_doc_type` and `rq_ex3_vendor`.
- It should put the target page in top-10 for `rq_ex3_expiry` and `rq_ex3_mfg`.
- If no stack does this, visual retrieval alone is not sufficient for this
  proof; proceed directly to OCR fallback.

### Experiment 2: Direct scorer vs Qdrant parity

**Goal.** Prove whether Qdrant/pooling changes the rank produced by the model.

**Method.**

- Use the best stack from Experiment 1.
- Query direct all-page MaxSim and Qdrant with `prefetch_limit=78`,
  `search_limit=78`.
- Compare rankings, especially for `rq_ex3`.

**Success criteria.**

- Rankings should match closely enough that the target rank category is the same
  (top-5, top-10, or miss).
- If Qdrant is worse than direct scoring, inspect pooled candidate union,
  patch-grid shape, serialization precision, and named-vector config.

### Experiment 3: Resolution and token budget

**Goal.** Determine whether small field values are lost due to raster/token
budget limits.

**Method.**

Using the best loader stack:

- Index current stored images.
- If source PDFs are available, rerasterize target/source pages at higher DPI.
- Load processor with `max_num_visual_tokens` values such as 768, 1024, 1280.
- Log target page image-grid dimensions, visual token count, GPU memory, and
  latency.

**Success criteria.**

- Exact-date target ranks improve without OOM.
- Title/vendor ranks remain stable or improve.
- If only exact-date queries improve, keep the setting as an enhancement but
  still implement OCR for compliance exactness.

### Experiment 4: OCR/VLM text fallback for empty pages

**Goal.** Remove the structural blind spot in the text tier.

**Method.**

- Run Docling VLM/OCR on pages with empty or very short `page_text`.
- Store OCR/VLM text and provenance separately.
- Rebuild the text index over original + OCR/VLM text.
- Re-run the 17 gold queries text-only.

**Success criteria.**

- All four `rq_ex3_*` queries retrieve `('5543408c4dacc48b', 2)` at top-5 in
  text-only or text+OCR mode.
- Existing 11/17 text top-5 wins are preserved.
- Extracted OCR/VLM text for the target page contains the document type, vendor,
  product, manufacture date, and expiration date.

### Experiment 5: Fusion guardrail

**Goal.** Make hybrid retrieval additive instead of risky.

**Method.**

Using logged text and visual rankings, compare:

- text-only,
- visual-only,
- equal RRF,
- weighted RRF,
- text-first gated fusion,
- image-only-page boost.

No new embeddings are required if run artifacts store full rankings.

**Success criteria.**

- Fused recall@5 >= text-only recall@5.
- Fused recall@10 >= text-only recall@10.
- Any visual/OCR-only `rq_ex3` wins appear in fused top-5.
- The policy is deterministic and explainable enough for compliance demos.

## Final Diagnosis

The current result should not be interpreted as "ColQwen2.5 cannot work for
pharma document retrieval." It should be interpreted as:

1. The run used a ColQwen2.5/Transformers 5 stack with credible upstream evidence
   of silent checkpoint-conversion quality failure.
2. The pipeline's shape checks were too weak to catch that class of failure.
3. Equal RRF then let a weak visual ranking damage a strong text baseline.
4. For exact compliance fields on scanned pages, visual page retrieval is not a
   complete substitute for OCR/VLM text extraction.

The highest-leverage next move is to audit and stabilize model loading, compare
direct visual ranks under a patched/current-main or early-4.x stack, and then add
OCR text coverage plus fusion guardrails. That gives the project a credible path
to both a stronger demo metric and a more realistic pharmaceutical compliance
architecture.

## Sources

- [ColPali: Efficient Document Retrieval with Vision Language Models][colpali]
- [vidore/colqwen2.5-v0.2 model card][colqwen-card]
- [vidore/colqwen2.5-v0.2 results JSON][colqwen-results]
- [Qdrant PDF retrieval at scale with ColPali/ColQwen][qdrant-pdf]
- [Qdrant ColPali optimization blog][qdrant-opt]
- [colpali-engine changelog][colpali-changelog]
- [Current colpali-engine ColQwen2.5 source][colpali-current-source]
- [colpali-engine 0.3.17 on PyPI][colpali-pypi-0317]
- [Hugging Face Transformers ColQwen2 docs][hf-colqwen]
- [Qwen2.5-VL technical report][qwen25]
- [Docling VLM pipeline example][docling-vlm]
- [Granite-Docling-258M model card][granite-docling]
- [Docling force full-page OCR example][docling-ocr]

[colpali]: https://arxiv.org/abs/2407.01449
[colqwen-card]: https://huggingface.co/vidore/colqwen2.5-v0.2
[colqwen-results]: https://huggingface.co/vidore/colqwen2.5-v0.2/blob/8717f1e72ab1d502d849ba0e6f16487914de1bab/results.json
[qdrant-pdf]: https://qdrant.tech/documentation/tutorials-search-engineering/pdf-retrieval-at-scale/
[qdrant-opt]: https://qdrant.tech/blog/colpali-qdrant-optimization/
[colpali-changelog]: https://raw.githubusercontent.com/illuin-tech/colpali/main/CHANGELOG.md
[colpali-current-source]: https://raw.githubusercontent.com/illuin-tech/colpali/main/colpali_engine/models/qwen2_5/colqwen2_5/modeling_colqwen2_5.py
[colpali-pypi-0317]: https://pypi.org/project/colpali-engine/0.3.17/
[hf-colqwen]: https://huggingface.co/docs/transformers/en/model_doc/colqwen2
[qwen25]: https://arxiv.org/abs/2502.13923
[docling-vlm]: https://docling-project.github.io/docling/examples/minimal_vlm_pipeline/
[granite-docling]: https://huggingface.co/ibm-granite/granite-docling-258M
[docling-ocr]: https://docling-project.github.io/docling/examples/force_full_page_ocr/
