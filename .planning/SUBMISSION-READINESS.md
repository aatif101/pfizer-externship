# Submission readiness contract

Prepared 2026-09-22 from the owner's final-project assignment and the repository review. This is a roadmap and acceptance contract, not a claim that implementation or evaluation has passed.

## Finish line

A reviewer can start from the submitted revision in a clean environment, process a complete public or authorized pharmaceutical SDF packet, inspect extracted fields/document type and compliance flags, ask questions with inspectable source pages, observe an appropriate abstention, reproduce evaluation across document types, and watch a professional walkthrough. The public demonstration uses fictional documents by default. Real confidential records stay out of submission artifacts.

GSD source: https://github.com/open-gsd/gsd-core. Apply discuss/context -> research and plan checking -> small executable plans -> execution with atomic commits -> goal-backward verification -> UAT -> release. Each implementation plan begins with a working vertical slice and has observable must-haves, files, dependencies, automated verification, and human checks where appropriate. Planning documents alone never close a requirement.

## Baseline and evidence limits

- Reviewed branch: `codex/demo-ready-july-2026`, implementation HEAD `8f6c803`, 15 commits ahead of fetched `origin/main` at review time. Record fresh SHAs before implementation; these numbers will change.
- Ordinary selected suite: 644 passed, 10 failed, 7 skipped, 1 deselected. Command: `venv/Scripts/python.exe -m pytest -q -m 'not live and not model and not gpu' -o addopts=--tb=short`.
- Ten failures are in `tests/eval/test_synthetic_benchmark.py`: absent specifications/manifests plus unbundled DejaVu fonts. `benchmarks/` is untracked. The socket-disabled run additionally fails the Windows asyncio RAGAS test; solve local event-loop socket compatibility without allowing outbound provider/network access.
- Existing `pyproject.toml`, `uv.lock`, `.agents/`, `.codex/`, `AGENTS.md`, and benchmark work belong to the existing worktree. Inspect and preserve them; do not reset, broadly stage, or silently discard them.
- Local DB has five documents, 78 pages, 17 gold retrieval questions. Latest stored extraction macro-F1 is 0.46 from June; it is not a measurement of July/September code.
- Old RAG aggregates combine observations by index ID (85 observations in one index); the first-100 loader can also omit new observations. Zero cost/tokens and old latency must not be advertised as measured live performance.
- Historical 17/17 visual recall was obtained after fusion tuning on those examples and offline fusion of saved real ranks. Treat as development/exploratory evidence, not untouched holdout performance or a fresh full Colab execution.
- Current visual backend in ordinary chat raises; notebook starts with a populated DB and pulls main. No linked final walkthrough video was found. README has obsolete test counts and unsupported absolute grounding/local-only privacy statements.

## Scope and existing decisions

Keep Python, Docling, Qdrant, ColQwen2.5, LangGraph, Langfuse, Streamlit, Pydantic and RAGAS. Reuse working modules and contracts. Keep `.planning/` as the active GSD authority; `.gsd/` is historical evidence, not a competing execution queue. Do not upgrade GSD or dependencies just for novelty. Verify model availability, SDK compatibility and current pricing during phase research/live preflight; record resolved versions.

Preserve Phase 3 CONTEXT and AI-SPEC, including its frozen corpus, held-out evaluation, numerical gates, bounded generation and isolated RAGAS environment. Literal quote matching alone does not prove a claim is entailed: include wrong-entity, wrong-lot, negation, contradictory-date and instruction-in-document cases in validation and adjudication.

Preserve the original critic/confidence/HITL ambitions as Phase 5.1/6 work; they were deferred, not delivered. Do not invent unavailable log probabilities. Phase 5.1 research must either prove the documented confidence inputs are supported or surface a concrete amendment before changing that locked formula. No silent substitution of heuristic confidence for measured probabilities.

No production hosting, authentication, regulatory validation, new model families, fine-tuning, or UI rewrite is needed. Demo completion means a bounded, evaluated decision-support system, not zero hallucinations or validated pharmaceutical disposition.

## Dependency sequence and phase contracts

### 2.1 — Submission Baseline Recovery

**Outcome:** a clean checkout can run the required offline gate and verify a complete public benchmark before any further calibration.

- First slice: one synthetic development packet can be generated and validated on Windows from documented dependencies.
- Complete and track specifications, manifests, generator/assets/licenses; make font/rendering reproducible across supported environments. Preserve exact 84-document/252-page and dev/holdout contracts from 03-00; never inspect holdout answers to debug model behavior.
- Fix the ten benchmark failures and socket-disabled asyncio incompatibility. Classify existing skips honestly; required offline cases must pass, optional live/model/GPU cases must be explicitly selected separately. Do not delete tests or globally enable sockets to obtain green status.
- Reconcile completed 03-00 tasks against actual commits and artifacts; write its SUMMARY only for verified work and leave unmet items open. Phase 3 must not regenerate or retune an already frozen corpus.
- Confirm a fresh locked install, `pip check`, baseline smoke commands, and documented API/GPU requirements. Correct the currently false README statements and record existing worktree changes without taking ownership blindly.

**Exit:** zero failures/skips/xpasses in the required offline selection, deterministic benchmark `--check`, clean-install evidence, public fixture provenance, and 03-00 reconciliation. Owners: SUBMIT-01/02/08. Suggested 2-3 small plans; planner decides exact split.

### 3 — Retrieval & Grounded RAG

**Outcome:** the real hybrid text stack answers a document question through the same service used by Streamlit, with validated claim evidence or canonical abstention.

- Reuse/reconcile existing 03-00 through 03-05; research changed library/API assumptions before execution. Retain BM25+BGE/Qdrant, reranking, strict claim schema and fixed LangGraph design.
- First slice: one development document -> real index -> retrieval -> Gemini -> claim/citation validation -> displayed answer and source page.
- Expand to multi-document retrieval, malformed output, prompt injection, unsupported questions, stale index, wrong-lot evidence, timeout and retry boundaries. No fake model adapters in demo/live mode.
- Execute the existing offline and live seals, preserve fingerprints and adjudication provenance, and enforce all existing quality/cost/latency gates. Replay validates plumbing only; it cannot replace live accuracy evidence.

**Exit:** 03-AI-SPEC gates and real end-to-end text path pass; failures route to targeted gap plans. Owners: RETRIEVE-01/02/03, RAG-01/02, SUBMIT-03 (text), SUBMIT-04 (claim evidence).

### 4 — Dashboard & Evaluation Integrity

**Outcome:** every displayed score and source preview belongs to a reproducible, correctly scoped run.

- First slice: create two evaluations on the same index with deliberately different results; the second report and comparison must contain only its own observations.
- Use evaluation-run identities, uniqueness/completeness checks and explicit pagination; eliminate cross-run mixing and first-100 truncation. Keep immutable legacy data labeled as legacy; do not rewrite old scores to look current.
- Measure full ingestion/extraction/retrieval/generation timing with clear boundaries, warm/cold separation, p50/p95, failures, token usage and dated model prices. Missing measurements are null/unavailable, never fabricated zero.
- Report extraction precision/recall/F1 per field, normalized document-type classification with confusion counts, retrieval metrics, claim/citation/abstention metrics, RAGAS judge coverage, and results by document type and native/scanned/mixed mode. Include denominator, exclusions and run manifests.
- Verify Compliance/Chat/Eval on empty, complete, failed and partial runs; source page opens must match displayed citations. Human-review labels and annotation provenance must distinguish synthetic authoring from independently reviewed gold. Preserve EVAL-01's ~50-page reviewed evidence requirement; never claim review that did not occur.

**Exit:** repeatable isolated metrics and usable UI, tests above 100 observations, correct failure/missingness treatment, and human UAT with source-page inspection. Owners: DASH-01/02, EVAL-01..05, SUBMIT-04.

### 5 — Visual Retrieval Foundation Revalidation

**Outcome:** existing visual implementation is accepted based on a fresh real GPU run, with its limitations explicit.

- Preserve 05-01..05-04 plans/summaries and the 05-05 follow-up summary (there is no 05-05 plan file). Audit/revalidate the foundation instead of rebuilding it.
- Run clean Colab L4 install, clean model load report, real page embeddings, Qdrant two-stage queries and dev-only text/visual/fused comparison on the submitted code revision.
- Export environment, model/index identifiers, per-query ranks, runtime/cost data and failure logs. Treat the 17-query set as development only.

**Exit:** actual GPU evidence and a foundation verification report. Full visual-chat integration and extraction critic work belong to 5.1, not to the historical Phase 5 completion claim. Owners: VISUAL-01 and foundation evidence for VISUAL-02.

### 5.1 — Visual Integration and Extraction Assurance

**Outcome:** one real runtime can answer through visual-fused retrieval and conservatively review difficult extracted fields.

- First slice: a scanned development page -> real visual retrieval -> verified OCR/text evidence -> normal `answer_question` service -> Chat source preview. No notebook monkeypatch or fake ranking may be required by the public flow.
- Prefer a single Colab L4 runtime for the GPU demo; choose a local/bridge alternative only if clean-session testing proves necessary. Record the actual choice before planning transport/security details. Local CPU text mode remains usable and clearly labeled.
- Detect missing GPU/index, stale corpus/index, backend failure and page/provenance mismatches. Explicit degraded text-only mode is acceptable; never silently label it visual-fused. A visual similarity hit alone cannot authorize an unsupported answer.
- Implement the previously deferred image critic, capped reconciliation and validated confidence inputs. Uncertain fields become review items; missing confidence inputs cannot become fabricated confidence.

**Exit:** genuine visual Chat UAT, failure-mode tests, confidence contract resolution and extraction reviewer outputs. Owners: VISUAL-02 integration, EXTRACT-03/04, SUBMIT-03 (visual).

### 6 — Agentic RAG, Human Review & Observability

**Outcome:** the complete user workflow handles uncertainty, corrections and failures with bounded, auditable execution.

- Reuse Phase 3's graph; add only the explicitly required RAG-03 decomposition/critique behavior, bounded retrieval retries (at most two) and regeneration (at most one). Revalidate quality and latency after adding calls; do not weaken earlier gates silently.
- First slice: one difficult document produces a review item; the user inspects source, corrects a field, and sees a recomputed compliance result with retained provenance.
- Add HITL correction history, original-versus-reviewed values, index freshness handling when applicable, and Langfuse phase/run correlation without automatic raw content capture.
- Provide the complete orchestrated public-document path: ingest -> classify/extract -> assess -> index -> answer/review -> evaluate. Stop/retry/resume behavior must be explicit and preserve completed work.

**Exit:** full-document UAT, correction audit, bounded graph/error tests, actual sanitized trace evidence, and no hidden dependency on the developer's database. Owners: HITL-01, RAG-03, OBS-01, SUBMIT-03 (full workflow).

### 7 — Final Benchmark, Colab & Submission Package

**Outcome:** an external reviewer can reproduce, understand and inspect the demonstrated system from a single release revision.

- First slice: fresh Colab session -> pinned repo revision -> permitted sample PDFs -> complete workflow -> one cited answer and one abstention. Build on this exact runtime for the recording.
- Make the notebook an end-to-end entry point; do not require the private populated DB. Include setup, secrets guidance, GPU choice, model-access preflight, stage progress, expected outputs, troubleshooting and export steps. Optional sample downloads must have licenses and checksums. No credentials in Git remotes or outputs.
- Freeze implementation/model/prompt/index/dataset/scorer fingerprints and configuration before final holdout evaluation. Compare baseline and upgraded pipelines on identical data using three declared runs; show means, standard deviations, confidence intervals, stratified results, failures and exclusions. Correctness/faithfulness claims must be supported by evidence, not just retrieval recall.
- Rerun the Phase 3 release contract on the final integrated revision. Publish a redacted/synthetic report and machine-readable artifacts; preserve the threshold contract. If holdout inspection informs fixes, follow the existing new-version policy instead of repeatedly tuning against v1.
- README, architecture/data-flow diagrams, engineering decisions/tradeoffs, limitations, privacy/API disclosures, setup, commands and results all describe the delivered code. Link the Colab notebook and walkthrough.
- Prepare and record a roughly 5-8 minute video: problem and architecture; clean full-document processing; classification/fields and risk; supported question/source inspection; abstention or failure recovery; measured results and limitations. Recording/narration can require the owner; scripts and screenshots do not count as the video. Verify playback and audience access.
- Check fresh checkout and fresh Colab independently of existing caches. Pin notebook/report/video to an identifiable release. Final documentation-only edits may follow measured code if the code/artifact fingerprints remain explicit; any implementation change invalidates affected evidence.
- Publish through normal repository review; verify the submitted branch/tag/commit is remotely available. Do not claim a local commit or draft PR is already the submitted release.

**Exit:** every release checklist item below has accessible evidence; no unresolved required test, quality or user-facing blocker. Owners: BENCH-01/02, POLISH-01/02/03, SUBMIT-05/06/07/08.

## Release checklist and targets

The assignment gives no numeric grading thresholds. Existing Phase 3 gates are project commitments, not a grading rubric; preserve them. Additional extraction/classification acceptance targets must be specified before evaluation in Phase 4 based on the field rubric and error costs, not selected after seeing holdout results. Review-only/abstained fields must remain visible in denominators.

| Gate | Evidence required | Owner |
|---|---|---|
| Reproducibility | Clean install, exact revision/locks, fresh Windows and Colab logs | 2.1, 7 |
| Offline correctness | Required suite passes with no unexpected skip/xpass and network blocked | 2.1, every phase |
| Real functionality | Fresh full-document processing, source-backed answers, classification and risk inspection | 3, 5.1, 6 |
| Quality | Existing 03-AI-SPEC gates; per-field/classification targets fixed before scoring; results across document types | 3, 4, 7 |
| Reliability | Invalid PDFs, scanned/empty pages, bad provider response, timeout/quota, stale index, interruption/resume | 2.1, 3, 5.1, 6 |
| Speed/cost | Real end-to-end timing, warm/cold labels, token/cost provenance, dated prices | 4, 7 |
| Metric integrity | Unique run IDs, exact sample counts, no accumulated historical rows, no fake live scores | 4, 7 |
| Documentation | Claims agree with delivered behavior; architecture/design/tradeoffs and privacy disclosure | 7 |
| Presentation | Accessible Colab/repo/video links and a reviewer walkthrough from the release revision | 7 |

## Execution rules and external dependencies

- Start with `/gsd-plan-phase 2.1`, then execute and verify that phase. Detailed task plans for later phases are created just in time; the phase contracts above are input, not executable PLAN files.
- Feed this contract to every later planner. Phase 3 has existing plans: reconcile completed 03-00 work and replan only affected unexecuted work. Phase 5 has completed work: use verification/gap closure, not blind re-execution.
- Every phase produces PLAN, SUMMARY, VERIFICATION and relevant UAT artifacts; update REQUIREMENTS and STATE only against evidence. No new implementation phase is marked complete by this planning task.
- Use Windows PowerShell and `venv/Scripts/python.exe`; no `/bin/bash` verification. Respect runtime isolation between app, legacy RAGAS and GPU stack.
- Never tune on sealed holdout cases. Preserve the Phase 3 live budget cap of $9 per its existing contract; a paid live run needs its documented bounded acknowledgement. This planning task grants no new spending authorization. If budget/quota is insufficient, report incomplete live evidence, not a replay substitute.
- GPU access, API quota/model availability, independent gold review, video narration and submission-link access are external dependencies. Prepare scripts, fixtures, budget estimates and instructions before the checkpoint so owner action is concrete.
- If a required gate fails, create a narrow gap plan, execute it and rerun affected evidence. Do not lower the gate or add unrelated features to avoid the failure.

## Tomorrow's first useful session

Read START-HERE.md and plan Phase 2.1. The first implementation goal is a reproducible benchmark plus passing offline gate, not another redesign. Once that passes, proceed in order: 3 -> 4 -> 5 foundation verification -> 5.1 -> 6 -> 7. Completion is governed by the checklist, not an estimated number of days.
