---
phase: "6"
slug: "agentic-rag-observability"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-09-23"
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 (+ pytest-cov, pytest-socket) |
| **Config file** | `pytest.ini` / `pyproject.toml` (`addopts = -x --tb=short`, `gpu` marker) |
| **Quick run command** | `venv\Scripts\python.exe -m pytest tests/rag/agentic tests/test_review_repository.py tests/test_dashboard_review_tab.py tests/test_tracing_phase.py -q` |
| **Full suite command** | `venv\Scripts\python.exe -m pytest -q -m "not gpu"` |
| **Estimated runtime** | ~30 seconds (quick), ~120 seconds (full) |

---

## Sampling Rate

- **After every task commit:** Run the quick run command
- **After every plan wave:** Run the full suite command
- **Before `/gsd-verify-work`:** Full suite must be green, plus one manual live Langfuse trace check recorded in a SUMMARY
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

Task IDs are filled in by the planner/executor. Requirement-level map (from 06-RESEARCH.md § Validation Architecture):

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | 0/1 | RAG-03 | — | Pinned langgraph==1.0.1 + langchain-core 0.3.x importable | unit | `venv\Scripts\python.exe -m pytest tests/rag/agentic/test_stack_pins.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | — | RAG-03 | T-6 DoS | Retrieval retries capped (3 rounds), regen capped (1), abstain after | integration | `venv\Scripts\python.exe -m pytest tests/rag/agentic/test_routing.py tests/rag/agentic/test_graph.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | — | RAG-03 / SC-4 | T-6 injection | Critic failure fails closed (abstain); citations service-owned | integration | `venv\Scripts\python.exe -m pytest tests/rag/agentic/test_graph.py -k "critic_failure or citations" -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | — | RAG-03 | — | Decomposition ≤3 sub-queries with malformed-LLM fallback | unit | `venv\Scripts\python.exe -m pytest tests/rag/agentic/test_decompose_rewrite.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | — | RAG-03 | — | Critic adapters parse/validate JSON, no `temperature` kwarg | unit | `venv\Scripts\python.exe -m pytest tests/rag/test_critic_provider.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | — | RAG-03 | — | Chat tab routes to agentic by default | unit | `venv\Scripts\python.exe -m pytest tests/test_dashboard_chat_tab.py tests/test_chat_dashboard.py -x` | ✅ extend | ⬜ pending |
| TBD | TBD | — | HITL-01 | T-6 SQLi / repudiation | Queue selection; corrections update extractions + compliance_records + audit row; history untouched; invalid input rolled back | unit | `venv\Scripts\python.exe -m pytest tests/test_review_repository.py tests/test_db.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | — | HITL-01 | — | Review tab renders queue and submits corrections | unit | `venv\Scripts\python.exe -m pytest tests/test_dashboard_review_tab.py tests/test_app.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | — | OBS-01 | T-6 disclosure | trace_session no-op without keys; phase tag on all boundaries; mask strips evidence/question/secrets; callback wiring; entry points open sessions | unit | `venv\Scripts\python.exe -m pytest tests/test_tracing_phase.py tests/test_tracing.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | — | SC-4 | — | Cross-path abstention (extraction + agentic RAG) | unit | `venv\Scripts\python.exe -m pytest tests/test_extraction_pipeline.py tests/rag/agentic/test_graph.py -k abstain -x` | ✅ partial | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Install `langgraph==1.0.1`, `anthropic>=1,<2`, `langfuse>=3.9,<4.0` into venv; update `pyproject.toml`
- [ ] `tests/rag/__init__.py`, `tests/rag/agentic/__init__.py`, `tests/rag/agentic/conftest.py` — fake retrieve_fn, FakeAnswerProvider, FakeCritic
- [ ] `tests/rag/agentic/test_stack_pins.py`, `test_routing.py`, `test_graph.py`, `test_decompose_rewrite.py`
- [ ] `tests/rag/test_critic_provider.py`
- [ ] `tests/test_review_repository.py`
- [ ] `tests/test_dashboard_review_tab.py`
- [ ] `tests/test_tracing_phase.py`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live trace shows root + node + generation spans with phase tag | OBS-01 | Needs live Langfuse keys and UI | Run one chat question with keys set; inspect Langfuse UI; record trace URL in SUMMARY |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
