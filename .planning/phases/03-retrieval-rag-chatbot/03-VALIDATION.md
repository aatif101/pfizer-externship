---
phase: 3
slug: retrieval-rag-chatbot
status: ready
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-15
benchmark: sdf-synthetic-v1
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for RETRIEVE-01/02/03 and RAG-01/02. Required behavior is credential-free and deterministic in ordinary CI; real-model and live-provider evidence is an additional tagged-release gate, never a substitute for offline coverage.

## Frozen release gates

These thresholds are release-blocking and may not be weakened by a plan or implementation task:

| Dimension | Required result |
|---|---|
| Retrieval | recall@5 >= 0.95; recall@10 >= 0.98; nDCG@5 >= 0.90; query-bootstrap 95% lower confidence bound for recall@5 >= 0.90 |
| Grounding | claim faithfulness >= 0.95; unsupported-claim rate <= 0.02; independent live RAGAS faithfulness >= 0.95 |
| Answer quality | answer correctness >= 0.90; citation precision >= 0.98; citation completeness >= 0.95 |
| Safety | abstention accuracy >= 0.95 across all 300 holdout queries; unanswerable-query abstention recall >= 0.95 across the 120 unanswerable queries |
| Stability | exactly three complete seeded runs (`1729`, `2718`, `3141`); population SD <= 0.02 for every primary quality metric; identical fingerprints across the run set |
| Performance | warm live-provider end-to-end p95 <= 6.0 seconds in each run; maximum billable cost <= $0.01 for every answer or abstention |
| Provenance/privacy | exactly 300 unique request rows per seed and 900 per run set; complete denominators/fingerprints/usage; no raw question, answer, evidence, PDF/image, provider payload, secret, or full hash in exported traces |

Every seeded run must independently meet the quality gates; reporting a passing three-run mean does not excuse a failing run. A zero denominator, partial run, unexpected/duplicate ID, changed fingerprint, missing usage, or mixed run mode is a failed gate.

## Test infrastructure

| Property | Value |
|---|---|
| Framework | `pytest` + `pytest-cov`; `pytest-socket` added in Wave 0 to prove offline isolation |
| Config | `pyproject.toml` (`[tool.pytest.ini_options]`); marker registration and Phase 3 no-skip hook added in Wave 0 |
| Unit doubles | Pure deterministic encoders/reranker/provider/repository/checkpointer; no heavy import, cache, key, or network |
| Integration substrate | Real SQLite and `QdrantClient(":memory:")` with deterministic embeddings and replayed strict provider output |
| Quick command | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_phase3_pytest.ps1 <task-owned tests> -q` |
| Phase command | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_phase3_pytest.ps1 tests\retrieval tests\rag tests\eval tests\test_retriever.py tests\test_retrieval_indexer.py tests\test_retrieval_index_repository.py tests\test_answer_service.py tests\test_answer_provider_gemini.py tests\test_chat_dashboard.py tests\test_tracing.py --ignore=tests\retrieval\visual -q` |
| Full command | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_phase3_pytest.ps1 tests -q` |
| Current baseline | 635 passed, 8 optional skips before Phase 3; Phase 3 required suites themselves permit zero skips/xpasses |
| Feedback budget | task unit <= 30 s; focused integration <= 90 s; phase offline <= 240 s; full regression <= 360 s on the reference Windows developer environment |

## Test tiers and sampling cadence

| Tier | Trigger | Scope | Maximum feedback latency | Failure action |
|---|---|---|---:|---|
| T0 — contract/unit | Red/green loop and before every task commit | The task-owned test files from the map below; pure doubles only | 30 s | Do not commit |
| T1 — focused integration | After every task that touches persistence, indexing, retrieval, provider, graph, or public DTOs | Task tests plus adjacent existing compatibility tests | 90 s | Fix in the same task; no deferral |
| T2 — Phase 3 offline | After every plan and at every wave boundary | All Phase 3 retrieval/RAG/eval tests, SQLite, in-memory Qdrant, replay provider, no network | 240 s | Wave remains incomplete |
| T3 — full regression/coverage | At each wave boundary and before phase verification | Entire non-live/non-model/non-GPU suite, dependency check, compile, overall and high-risk coverage | 360 s | Phase remains incomplete |
| T4 — frozen replay | At final Phase 3 integration and every release candidate | Manifest verification plus all 300 holdout queries x 3 seeds in `offline-replay` mode | Record actual runtime | Block release on any metric, provenance, privacy, or count failure |
| T5 — live release | Explicit tagged-release run only, after T0-T4 are green | Real pinned BGE/reranker, Gemini, isolated RAGAS, 300 holdout queries x 3 seeds | Record actual runtime | No published live numbers/tag until green and sealed |

Sampling continuity is strict: every implementation task creates or updates its automated tests in the same task, and no two consecutive tasks may defer verification. Tests assert negative paths and exact model/provider/retrieval call counts, not only returned strings.

## Per-task verification map

The planner should preserve these task IDs or carry the same rows into the final plan IDs without dropping a command.

| Task ID | Planned slice | Wave | Requirements | Threat / guardrail | Secure behavior under test | Automated command | File exists |
|---|---|---:|---|---|---|---|---|
| 03-00-01 | Offline/no-skip harness, markers, shared doubles, ignore rules | 1 | All | hidden network / skipped safety checks | Required offline tests deny sockets, fail on skip/xpass, use explicit test-double provenance, and keep artifacts/private data untracked | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify_phase3_wave0.ps1` | Owned by 03-00 |
| 03-00-02 | Freeze deterministic public benchmark before tuning | 1 | All | holdout leakage / mutable gold | Exact 84/252/120/300/180/120/360 contract, document-first split, hashes, rubric/license, no private data | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_phase3_pytest.ps1 tests\eval\test_synthetic_benchmark.py -q` | Owned by 03-00 |
| 03-01-01 | Isolated RAGAS CLI/lock and main-runtime dependency contract | 2 | RETRIEVE-01/02, RAG-01 | dependency collision / placeholder judge | Main runtime resolves LangGraph/Core 1.x without importing RAGAS; isolated module CLI/schema/scorer executes; failures are explicit | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_phase3_pytest.ps1 tests\test_phase3_dependency_contract.py tests\test_import_contracts.py tests\eval\test_ragas_subprocess.py tests\eval\test_ragas_quality.py -q` | Owned by 03-01 |
| 03-01-02 | Chunk, DTO, schema migration, and manifest primitives | 2 | RETRIEVE-01/02 | stale/misattributed evidence | Page-bounded 500-target/540-max chunks with 50-token overlap, stable IDs/offsets/hashes, exact OCR source, idempotent migration | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_phase3_pytest.ps1 tests\retrieval\test_chunks.py tests\test_retrieval_indexer.py tests\test_retrieval_index_repository.py -q` | Owned by 03-01 |
| 03-01-03 | Named sparse/dense Qdrant build, alias promotion, recovery | 2 | RETRIEVE-01/02 | fabricated/partial/split index | IDF sparse and 1024-d dense vectors, deterministic vocabulary, atomic alias/SQLite reconciliation, no fake release index | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_phase3_pytest.ps1 tests\retrieval\test_encoders.py tests\retrieval\test_qdrant_index.py tests\test_retrieval_indexer.py tests\test_retrieval_cli.py -q` | Owned by 03-01 |
| 03-02-01 | Sparse+dense query, RRF, rerank, page dedupe | 3 | RETRIEVE-03 | score mixing / nondeterministic rank | At least 50+50 candidates, RRF k=60, bounded top-40 rerank union, deterministic tie break, top-10 chunks/top-5 pages | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_phase3_pytest.ps1 tests\retrieval\test_hybrid.py -q` | Owned by 03-02 |
| 03-02-02 | Frozen-development calibration and evidence gate | 3 | RETRIEVE-03, RAG-02 | holdout leakage / false sufficiency | Development hash/IDs only; deliberate holdout access fails; contradictory/decoy/weak/visual-only text abstains | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_phase3_pytest.ps1 tests\retrieval\test_quality.py -q` | Owned by 03-02 |
| 03-02-03 | Compatibility facade, CLI, retrieval formulas/provenance | 3 | RETRIEVE-01/02/03 | fallback / misleading metrics | Required hybrid never falls back; recall/nDCG/bootstrap math and run fingerprints reject partial/mixed data | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_phase3_pytest.ps1 tests\test_retriever.py tests\test_retrieval_cli.py tests\test_retrieval_eval_metrics.py -q` | Owned by 03-02 |
| 03-03-01 | Strict claim schema, evidence registry, deterministic rendering/grounding | 4 | RAG-01/02 | prompt injection / invalid citation / unsupported summary | Unknown IDs, nonliteral quotes, stale hashes, scope/polarity/unit/date mismatch, and model display prose reject whole answer | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_phase3_pytest.ps1 tests\rag\test_schemas.py tests\rag\test_grounding.py tests\test_rag_contract.py -q` | Owned by 03-03 |
| 03-03-02 | Structured bounded Gemini adapter | 4 | RAG-01/02 | malformed output / timeout / budget | One strict structured call; no prose repair; complete safe usage/cost/model/schema provenance | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_phase3_pytest.ps1 tests\test_answer_provider_gemini.py -q` | Owned by 03-03 |
| 03-03-03 | Bounded graph, metadata-only checkpoint, service/dashboard compatibility | 4 | RAG-01/02 | loop overflow / content persistence / partial rendering | <=2 retrievals, <=1 generation; canonical zero-citation abstention; checkpoint cleanup and content privacy | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_phase3_pytest.ps1 tests\rag\test_graph.py tests\test_answer_service.py tests\test_chat_dashboard.py tests\test_dashboard_chat_tab.py -q` | Owned by 03-03 |
| 03-04-01 | Fresh corpus and complete structured offline replay | 5 | All | local-state dependency / replay mislabeled live | Frozen v1 unchanged; all 300 replay rows schema-valid, deterministic, and explicitly test-double/offline | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_phase3_pytest.ps1 tests\eval\test_synthetic_benchmark.py -q` | Owned by 03-04 |
| 03-04-02 | Demo-gate formulas/provenance/privacy/sealing | 5 | All | contaminated or misleading metrics | Exact counts/hashes/modes/formulas/usage/privacy; thresholds immutable; partial/mixed/tampered runs fail | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_phase3_pytest.ps1 tests\eval\test_demo_gate.py tests\eval\test_rag_claim_metrics.py tests\test_retrieval_eval_metrics.py -q` | Owned by 03-04 |
| 03-04-03 | Mandatory 900-row offline seal and regression | 5 | All | false-safe replay release | Fresh generation/index, adversarial E2E, exact 900 rows, seal, no-skips, coverage/dependency/full gates | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify_phase3_replay.ps1` | Owned by 03-04 |
| 03-05-01 | Real-release preflight/driver | 6 | All | replay/fake fallback / unbounded spend | Clean pinned real state, explicit key/budget ack, safe output path, no billable call on failed preflight | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_phase3_pytest.ps1 tests\eval\test_live_release_preflight.py -q` | Owned by 03-05 |
| 03-05-02 | Three live runs, isolated RAGAS, blinded AI adjudication, seal | 6 | All | unmeasured demo claims | Exactly 900 real rows, full usage/latency/cost, RAGAS/review complete, every frozen gate passes | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_phase3_live_release.ps1 -RequireRagas -RequireAdjudication` | Owned by 03-05 |
| 03-05-03 | Redacted publishable live report | 6 | All | privacy / overclaim / metric drift | Report derives from seal, matches metrics, discloses AI review and non-GxP scope, contains no sensitive content | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_phase3_pytest.ps1 tests\eval\test_live_release_preflight.py tests\eval\test_demo_gate.py -q` | Owned by 03-05 |

## Wave 0 requirements

- [ ] Add `pytest-socket` to the development dependencies and register `live`, `model`, and existing `gpu` markers in `pyproject.toml` with explicit meanings.
- [ ] Add a Phase 3 collection hook in `tests/conftest.py`: when `PHASE3_NO_SKIPS=1`, any skip or xpass from a required Phase 3 test is a session failure. Marker-excluded tests do not count as skips.
- [ ] Add the new test directories/files listed in the verification map before their corresponding implementation. A plan may rename a file only if it updates every command here in the same planning revision.
- [ ] Add deterministic shared fixtures for synthetic pages/chunks, fixed UTC clock (`2026-07-01`), in-memory Qdrant, fake encoders/reranker, replay provider with usage, async checkpointer, and sanitized trace capture.
- [ ] Add `benchmarks\sdf-synthetic-v1` manifest validation fixtures and deterministic scorer tests; private Pfizer/source PDFs are forbidden.
- [ ] Add `.artifacts\` to ignore rules if not already ignored; test output and live run data are never committed unless explicitly redacted, reviewed, and designated as a public benchmark artifact.

Existing pytest/SQLite fixtures cover baseline database lifecycle and compatibility tests. The missing Phase 3 files above are blocking Wave 0 work, not optional future tests.

## Fixture and test-double policy

1. **Synthetic only:** Tests and public benchmark artifacts contain generated supplier names/materials/lots and no Pfizer/private document content, filenames, paths, IDs, prompts, screenshots, or traces.
2. **Fixed provenance:** Fixture documents/pages/chunks have stable IDs, hashes, page numbering, model revisions, seeds, and an explicit `2026-07-01` evaluation clock. Mutation tests deliberately change exactly one provenance field.
3. **Real storage, fake intelligence:** Medium tests use actual SQLite and Qdrant in-memory collection semantics. Sparse/dense encoders, cross-encoder, and Gemini are injected deterministic protocols; each records arguments and call counts.
4. **No semantic shortcuts:** Fake scores are designed to exercise sparse-only, dense-only, agreement, ties, wrong-lot decoys, contradictions, weak margins, and stale hashes. A fake may not merely return the expected answer text.
5. **Strict provider replay:** Replay rows are validated against the same Pydantic schema as live Gemini and include provider request ID plus token/cost usage. Missing, duplicate, out-of-order, or extra query IDs fail the run.
6. **Network denial:** T0-T4 run with `pytest-socket --disable-socket`, scrub provider credentials in fixtures, and fail if SDK/client construction attempts external access. No test downloads a model.
7. **No release fallback:** `demo` or `live-release` configuration raises a typed preflight/configuration failure when real Qdrant/models/credentials/cache are absent; it can never select fake/replay components silently.
8. **Call bounds:** Every RAG safety test asserts retrieval calls `<= 2`, generation calls `<= 1`, graph retry count `<= 1`, bounded evidence count `<= 8`, and canonical abstention has zero claims/citations.

## Marker and optional-dependency handling

| Marker/state | Ordinary CI | Release meaning |
|---|---|---|
| unmarked Phase 3 | Required on Windows and Linux, offline, zero skips/xpasses | Must be green before any release run |
| `model` | Excluded from ordinary CI; exercises real cached BGE/reranker without provider | Required and must pass in the release environment; cache absence is a failed preflight, not `pytest.skip` |
| `live` | Excluded from ordinary CI; never inferred from presence of a key | Runs only after explicit release acknowledgement with credentials/network; provider failure is a failed run, not replay fallback |
| `gpu` | Existing optional visual tier; excluded from the Phase 3 text gate | Does not satisfy any Phase 3 requirement and cannot authorize factual answers |
| `importorskip` / conditional skip | Forbidden in required Phase 3 tests | Allowed only inside a registered excluded marker for genuinely optional/deferred capability |

Required Phase 3 offline gate (PowerShell, three commands):

```powershell
$env:PHASE3_NO_SKIPS = "1"
venv\Scripts\python.exe -m pytest tests\retrieval tests\rag tests\eval tests\test_retriever.py tests\test_retrieval_indexer.py tests\test_retrieval_index_repository.py tests\test_answer_service.py tests\test_answer_provider_gemini.py tests\test_chat_dashboard.py tests\test_tracing.py --ignore=tests\retrieval\visual -m "not live and not model and not gpu" -q --disable-socket
Remove-Item Env:\PHASE3_NO_SKIPS -ErrorAction SilentlyContinue
```

## Requirement-to-test evidence

| Requirement | Automated evidence required before completion | Release evidence |
|---|---|---|
| RETRIEVE-01 | Chunk boundary/overlap/page/ID/hash tests; named sparse collection schema; bm25s-reference weights/ranks; deterministic vocabulary; atomic manifest/count/stale tests | Per-query sparse ranks plus collection/vocabulary/chunker fingerprints in all sealed run artifacts |
| RETRIEVE-02 | Named cosine vector size 1024; BGE passage/query instruction and normalization; pinned revision; batch/device manifest; fake adapter and real-model contract smoke | Real pinned BGE model preflight, index fingerprint, dense ranks, no fake/replay adapter in live run |
| RETRIEVE-03 | Independent sparse/dense candidate assertions; RRF `k=60`; bounded union; cross-encoder call/order/tie; page dedupe; dev-only calibration; exact recall/nDCG/bootstrap formula tests | recall@5/10, nDCG@5 and fixed-seed 10,000-resample lower bound for all 180 answerable holdout queries in each run |
| RAG-01 | Strict response schema; request-local evidence registry; literal quote/hash/fact validation; server-owned filename/page; citation DTO/dashboard compatibility; injection and cross-claim rejection | Claim/citation rows with supported fact IDs; faithfulness, correctness, precision, completeness gates; independent RAGAS and blinded adjudication |
| RAG-02 | No provider call for weak/stale/contradictory evidence; exactly one deterministic retry; malformed/injected/unsupported/provider/timeout/budget/persistence paths return exact canonical abstention and no citations | Answerability decision on all 300 queries; abstention accuracy >= 0.95 and unanswerable recall >= 0.95 in every seeded run |

## Coverage and regression commands

T3 full offline regression and coverage:

```powershell
venv\Scripts\python.exe -m pytest -m "not live and not model and not gpu" --disable-socket --cov=src --cov-branch --cov-report=term-missing --cov-report=xml:.artifacts\coverage\phase3.xml --cov-fail-under=85 -q
venv\Scripts\python.exe -m coverage report --include="src/retrieval/chunks.py,src/retrieval/hybrid/*,src/rag/*,src/eval/demo_gate*" --fail-under=90
venv\Scripts\python.exe -m pip check
venv\Scripts\python.exe -m compileall -q src tests
```

Coverage is >= 85% for all `src` code and >= 90% for the high-risk Phase 3 retrieval, RAG, and eval-gate code. Branch coverage is collected and reviewed; every fail-closed branch, conditional graph edge, validation failure, and release-gate failure needs an assertion. Windows and Linux CI run the same offline selection; platform-specific differences are failures unless documented as an excluded `gpu`/`model` capability.

## Frozen benchmark and provenance checks

T4 dataset verification and offline replay:

```powershell
venv\Scripts\python.exe -m src.eval.demo_gate verify-dataset --dataset benchmarks\sdf-synthetic-v1 --expected-manifest benchmarks\sdf-synthetic-v1\MANIFEST.sha256
venv\Scripts\python.exe -m src.eval.demo_gate run --mode offline-replay --dataset benchmarks\sdf-synthetic-v1 --split holdout --provider-replay benchmarks\sdf-synthetic-v1\replay\gemini-2.5-flash.jsonl --seeds 1729,2718,3141 --output .artifacts\eval\ci
venv\Scripts\python.exe -m src.eval.demo_gate seal --run-dir .artifacts\eval\ci
```

`verify-dataset` must prove: 84 documents/252 pages; 24-development-document/120-development-query split; document-disjoint 60-document/300-query holdout; exactly 180 answerable and 120 unanswerable holdout queries; separately disjoint 360-cell extraction holdout; six document types, five layout families, native/scanned/mixed render modes; unique IDs; complete labels; all PDF/page/manifest hashes; no split overlap; fixed generation seed/renderer/license. Threshold or prompt/model/reranker changes may use development data only.

`run` and `seal` must prove: one declared run mode/split; exactly 900 unique request rows; expected per-query, claim, citation, usage, environment and adjudication artifacts; checksums; git/dependency/dataset/index/model/prompt/schema/config/calibration/scorer/price fingerprints; provider usage/cost coverage; denominators and confidence intervals; same fingerprints across seeds; no `latest` aliases; no development IDs; and no forbidden raw payloads. Offline replay results must be labeled `offline-replay` and may not be published as live-provider performance/cost evidence.

T5 live release and independent judge:

```powershell
$env:PHASE3_LIVE_RELEASE_ACK = "I_ACCEPT_UP_TO_9_USD"
venv\Scripts\python.exe -m src.eval.demo_gate run --mode live-release --dataset benchmarks\sdf-synthetic-v1 --split holdout --seeds 1729,2718,3141 --require-credentials --output .artifacts\eval\release
uv run --project tools\ragas-eval python -m ragas_eval score --input .artifacts\eval\release\ragas-input.jsonl --output .artifacts\eval\release\ragas-results.jsonl
venv\Scripts\python.exe -m src.eval.demo_gate seal --run-dir .artifacts\eval\release --require-ragas --require-adjudication
Remove-Item Env:\PHASE3_LIVE_RELEASE_ACK -ErrorAction SilentlyContinue
```

The live preflight requires a clean commit, immutable index, pinned local model revisions, explicit credentials, known pricing, and release acknowledgement. Exactly one declared warm-up request may be excluded before the 300 scored requests per seed. Any real-model/provider failure invalidates the run; replay/fake fallback is forbidden.

## Manual-only verification

| Behavior | Requirement/gate | Why manual | Instructions |
|---|---|---|---|
| Blinded review and adjudication | RAG-01 quality | Deterministic metrics benefit from a separately reasoned semantic review of supplier/material/lot/date/method scope | For the demo seal, two independent reviewer agents inspect every deterministic mismatch plus a fixed-seed 10% pass sample and a third adjudicates. Persist reviewer type as `independent_ai_review`, IDs, rubric version, decisions, limitations, and checksums. Never label this human/domain-expert review. Qualified-human review is required before any regulated/operational claim and may supersede the AI review later. |
| Live provider/model execution authorization | Release performance/RAGAS | Credentials, billing, network, and external provider processing require explicit authorized execution | On the designated release machine, complete preflight, run the exact T5 commands, verify 900 scored rows and real provider request IDs/usage, then seal. Do not expose keys or document content. |
| Final citation usability smoke | RAG-01 | Human-readable filename/page presentation is perceptual; click-through preview belongs to Phase 4 | Launch the local demo against the synthetic corpus, ask one answerable and one unanswerable question, confirm citations show the immutable synthetic filename/display page and the latter shows only canonical abstention. Record no claim of source-page click-through in Phase 3. |

Manual review never replaces automated quote/hash/fact checks, frozen metrics, provenance validation, call-bound assertions, or regression tests.

## Validation sign-off

- [ ] Wave 0 files, markers, no-skip hook, and deterministic fixtures exist.
- [ ] Every final plan task maps to one row above and has an `<automated>` command with <= 90-second focused feedback.
- [ ] No two consecutive implementation tasks lack an automated verification point.
- [ ] Required Phase 3 offline selection is green with zero skips/xpasses and no network/model/provider access.
- [ ] Full non-live/non-model/non-GPU regression, `pip check`, and `compileall` are green on Python 3.11.
- [ ] Overall coverage >= 85%; Phase 3 retrieval/RAG/eval-gate coverage >= 90%; all fail-closed branches are exercised.
- [ ] Dataset manifest and split/count/hash/license provenance checks pass before indexing/scoring.
- [ ] Offline replay has exactly 900 rows, identical fingerprints, all frozen quality/safety/stability gates, complete denominators, and a clean privacy scan.
- [ ] Live release has real model/provider evidence, independent RAGAS, latency/cost gates, required blinded adjudication, and no fallback.
- [ ] No synthetic/replay result is labeled live; no holdout example influenced calibration, prompt, model, threshold, or reranker selection.
- [ ] No raw sensitive content or secret appears in committed files, logs, traces, test output, or sealed public artifacts.
- [ ] `nyquist_compliant: true` remains set; set `wave_0_complete: true`, `status: approved`, and record approval only after all Wave 0 items are actually green.

**Approval:** pending Phase 3 execution evidence
