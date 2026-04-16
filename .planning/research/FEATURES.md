# Feature Landscape: Pfizer SDF Intelligence System

**Domain:** Pharmaceutical supplier documentation (SDF) intelligence — ingestion, extraction, compliance flagging, and grounded Q&A over mixed scanned/stamped PDFs (CoAs, vendor certificates, compliance forms)
**Researched:** 2026-04-16
**Overall confidence:** MEDIUM-HIGH (domain conventions well-documented; specific extraction schemas vary by vendor)

---

## 1. Field Landscape — What Gets Extracted From Pharma Supplier Docs

Pharmaceutical supplier documents are not free-form — they follow conventions driven by GMP, USP <1083> (Supplier Qualification), and 21 CFR 211.84. Extraction targets cluster into five groups.

### 1.1 Certificate of Analysis (CoA) — The Canonical Document

Every CoA under GMP must contain:

| Field Group | Specific Fields | Notes |
|---|---|---|
| **Document header** | Title ("Certificate of Analysis"), manufacturer name + address, issuing site | Stamped/letterhead region |
| **Material identity** | Product/material name, grade, compendial designation (USP/EP/JP), product code, CAS number | Often in table header |
| **Lot identity** | Lot/batch number, manufacturing date, expiration date, pack date, quantity | Required for traceability |
| **Test results table** | Test name, method reference (e.g., USP <621>), specification (limit), actual result, pass/fail | Core table, 5–30 rows |
| **Approval block** | Authorized reviewer name, title, signature, release date | Often scanned/stamped |
| **Storage/handling** | Storage conditions, retest date, special handling | Sometimes separate section |

**Sources (HIGH confidence):** [IPEC CoA Guide 2024](https://www.gmp-compliance.org/files/guidemgr/2024-coa-guide-f-1720781885.pdf), [GMP Requirements for CoA — ECA Academy](https://www.gmp-compliance.org/gmp-news/gmp-requirements-for-certificates-of-analysis-coa), [WHO Model CoA](https://cdn.who.int/media/docs/default-source/medicines/norms-and-standards/guidelines/quality-control/trs1010_annex4_who_model_certificate_analysis.pdf)

### 1.2 Supplier/Vendor Qualification Documents

| Field Group | Specific Fields |
|---|---|
| **Vendor identity** | Legal name, DBA, address, manufacturing site(s), DUNS, regulatory ID |
| **Certifications held** | GMP certificate (+ validity 2–3 yr), ISO 9001, ISO 13485, GDP, FDA establishment registration |
| **Audit history** | Last audit date, auditor, findings, CAPA status |
| **Scope of supply** | Materials/services supplied, risk category (critical/non-critical) |
| **Quality agreement** | Effective date, revision number, expiry/renewal date |

**Source (HIGH):** [USP General Chapter <1083> Supplier Qualification](https://www.usp.org/sites/default/files/usp/document/supply-chain/apec-toolkit/USP%20GC1083.pdf)

### 1.3 Compliance Forms (Generic)

| Field Group | Specific Fields |
|---|---|
| **Document control** | Document ID, title, revision number, effective date, revision date, next review date, supersedes |
| **Approval chain** | Author, reviewer, approver (name + title + signature + date) |
| **Classification** | Document type, department, confidentiality level |
| **Change history** | Revision log (rev # + date + reason + author) |

### 1.4 Cross-Cutting Temporal Fields (Risk Engine Inputs)

These are the fields that feed the compliance flagging logic — **this is the load-bearing subset for the dashboard**:

- Manufacturing date
- Effective date (when the doc/policy takes effect)
- Revision date (most recent)
- Expiry date (when it becomes invalid)
- Retest date (CoA-specific — when material must be retested)
- Next review date (document control)

**Confidence:** HIGH — these are defined in [21 CFR 211.84](https://www.gmp-compliance.org/gmp-news/gmp-requirements-for-certificates-of-analysis-coa) and ICH Q7.

### 1.5 Data Integrity Metadata (ALCOA+)

Under ALCOA++ (Attributable, Legible, Contemporaneous, Original, Accurate, Complete, Consistent, Enduring, Available, Traceable), each extracted fact must preserve:

- **Attribution:** who signed it (auth reviewer)
- **Traceability:** source page + bounding box
- **Originality:** link back to source PDF (don't transform-then-lose)
- **Contemporaneity:** capture date

**Source (HIGH):** [ALCOA++ Principles for Data Integrity — Quanticate](https://www.quanticate.com/blog/alcoa-principles), [PIC/S Guidance on Data Integrity](https://picscheme.org/docview/4234)

---

## 2. Compliance Rules — What Governs Validity

### 2.1 Hard Regulatory Rules (HIGH confidence)

| Rule | Source | Practical Implication |
|---|---|---|
| Identity testing required on every incoming lot | 21 CFR 211.84(d)(1) | Every lot needs a CoA |
| Reduced testing only with documented supplier qualification + periodic verification | 21 CFR 211.84 | Supplier qualification doc must be current |
| GMP certificate valid 2–3 years from inspection | WHO / EU GMP | Flag GMP certs >3 yr as expired |
| Max drug product expiration 5 years | GMP shelf-life rules | CoA retest dates typically ≤3 yr |
| Electronic records must have tamper-evident audit trails | 21 CFR Part 11 | Every extraction must be traceable and immutable |

**Sources:** [21 CFR Part 11 Compliance Guide — SimplerQMS](https://simplerqms.com/21-cfr-part-11-requirements/), [Qualio 21 CFR Part 11 Supply Chain](https://www.qualio.com/blog/21-cfr-part-11-supply-chain), [GMP Certificate Validity — Moravek](https://www.moravek.com/how-long-does-your-gmp-certification-last/)

### 2.2 Project-Specific Flagging Rules (from PROJECT.md)

PROJECT.md specifies the Phase 1 flag rule: **documents older than 3–4 years are compliance risks**. This aligns with GMP certificate validity (2–3 years) and is defensible.

Recommended thresholds (MEDIUM confidence — interpreted from domain norms):
- Green: `<2 years` (fresh, within typical revision cycle)
- Amber: `2–3 years` (approaching GMP cert expiry window)
- Red: `>3 years` (past typical GMP validity) or explicit expiration date passed

### 2.3 Revision Cycles (MEDIUM confidence)

Domain norms for pharma SOPs/specs:
- Quality agreements: annual review, revised every 2–3 years
- SOPs: biennial review
- Supplier quality contracts: 3-year renewal
- CoAs: per-lot (not revised — each lot gets a new CoA)
- GMP certificates: 2–3 years validity

---

## 3. Questions Compliance Officers Actually Ask

Derived from pharmaceutical audit checklists ([ISPE GMP Audit Checklist](https://ispe.org/initiatives/regulatory-resources/gmp/audit-checklist), [FDA Group Supplier Auditing](https://www.thefdagroup.com/blog/supplier-auditing), [Pharmaguideline Vendor Audits](https://www.pharmaguideline.com/2017/02/vendor-audits-checklist-pharmaceuticals.html)).

### 3.1 Portfolio-Level ("show me the state of the world")

- "Which supplier documents are expired?"
- "Which are expiring in the next 90 days?"
- "Show me all GMP certificates and their validity."
- "Which vendors have no current qualification on file?"
- "How many CoAs are older than 3 years?"

### 3.2 Vendor-Level Drill-Downs

- "What documents do we have for vendor X?"
- "When was vendor X last audited?"
- "What materials does vendor X supply?"
- "What is vendor X's most recent quality agreement revision date?"

### 3.3 Lot/Batch Traceability

- "What is the lot number and expiry of the [material] batch received on [date]?"
- "Show me the CoA test results for lot #####."
- "Did lot ##### pass all specifications?"
- "What was the method reference used for [test] on lot #####?"

### 3.4 Risk-Oriented Questions

- "Which documents have missing fields?"
- "Are any signatures missing from the approval chain?"
- "Have any documents been superseded but not removed?"
- "Where does the system have low confidence? (show me the audit queue)"

### 3.5 Data Integrity / Audit Trail Questions

- "Where does this claim come from?" (source page citation)
- "Who signed this document?"
- "What was the effective date of this policy?"

**Implication for chatbot design:** Questions span structured (filter/sort table queries) and unstructured (semantic search into text). Hybrid retrieval (BM25 + dense) is not optional — it's required. The agentic RAG path in Phase 2 handles multi-hop ("all vendors with expired GMPs and no current audit") which single-shot retrieval can't.

---

## 4. What "Done" Looks Like for a Pharma Compliance Dashboard

Observed from [GreenwolfTechLabs Pharma Compliance Dashboard](https://greenwolftechlabs.com/pharma-compliance-dashboard/), [SafetyCulture Top 7 Pharma Compliance Software 2026](https://safetyculture.com/apps/pharmaceutical-regulatory-compliance-software), [InfiniTrak DSCSA](https://infinitrak.us/), [Kodiak Hub Supplier Compliance](https://www.kodiakhub.com/blog/supplier-compliance-software):

### 4.1 Demo-Shipping Definition of Done

A compliance officer loads the app and within 60 seconds can answer:
1. **How many docs are at risk?** (red/amber counts, top-of-dashboard)
2. **Which specific docs are at risk?** (sortable, filterable table)
3. **Why is this doc flagged?** (click-through to source page with extracted field highlighted)
4. **Can I ask a question about the whole corpus?** (chat panel with cited answers)
5. **Do I trust the answers?** (confidence scores + page citations + observability)

### 4.2 Pfizer-Externship "Wow" Threshold

Based on what distinguishes enterprise pharma compliance software from a student project:
- Handles stamped/scanned PDFs gracefully (Docling + ColQwen — core advantage)
- Answers ground in specific pages, not vague summaries
- System **abstains** when uncertain (saying "I don't know" beats a wrong answer — this is the #1 pharma concern per [IntuitionLabs RAG Performance on Pharma](https://intuitionlabs.ai/articles/rag-performance-pharmaceutical-documents))
- Full observability trace (Langfuse) — auditors can reconstruct every answer
- Before/after benchmark showing Phase 2 > Phase 1 with real numbers

---

## 5. Feature Categorization

### 5.1 Table Stakes — Demo Fails Without These

| Feature | Complexity | Why Required | Tied to PROJECT.md Phase |
|---|---|---|---|
| **PDF folder ingestion** | Low | Core entry point | Phase 1 |
| **Docling layout-aware extraction** | Medium | Stamped/scanned PDFs break naive OCR | Phase 1 |
| **Core field extraction** (doc type, vendor, mfg date, effective date, revision date, expiry date) | Medium | Dashboard + risk engine depend on these | Phase 1 |
| **Pydantic-validated extraction output** | Low | Schema-guaranteed downstream consumption | Phase 1 |
| **Age/expiry risk flagging** (>3yr red, 2–3yr amber, <2yr green) | Low | The whole "compliance" value prop | Phase 1 |
| **Sortable compliance table** (filename, doc type, vendor, revision date, age, flag, confidence, source link) | Low | Primary UI surface | Phase 1 |
| **Color-coded risk levels** | Low | Visual triage — officers scan, don't read | Phase 1 |
| **Hybrid RAG chatbot** (BM25 + dense + rerank) | Medium | Handles both "show me X batch" (lexical) and "what suppliers do Y" (semantic) | Phase 1 |
| **Source page citation on every answer** | Medium | Non-negotiable for pharma — see ALCOA+ traceability | Phase 1 |
| **Eval harness** (F1/recall/faithfulness/latency/cost) | Medium | Required to defend Phase 2 improvements quantitatively | Phase 1 |
| **Confidence score per extracted field** | Medium | Dashboard needs it for audit queue + trust signaling | Phase 2 |
| **Bounding-box citations** (not just page #) | Medium | "Click to highlight in source PDF" is the moment of trust | Phase 2 |
| **Abstention on low confidence** | Medium | Wrong answer is worse than no answer (regulated industry) | Phase 2 |
| **Full observability trace** (Langfuse on every step) | Low (config) | Pharma audit credibility; differentiator vs naive demos | Phase 2 |

### 5.2 Differentiators — Impressive for Pfizer Externship

| Feature | Complexity | Why This Wins | Tied to PROJECT.md Phase |
|---|---|---|---|
| **ColQwen2 visual retrieval** (page-image embeddings in Qdrant with HNSW + late-interaction rerank) | High | Captures layout/stamps/tables that text extraction loses — genuinely novel for pharma | Phase 2 |
| **Agentic extraction critic loop** (extractor → critic re-reads source → reconciliation) | High | Self-correcting extraction; measurable F1 lift in benchmark | Phase 2 |
| **LangGraph agentic RAG** (query decompose → retrieve → evaluate → re-retrieve → draft → self-critique → regenerate) | High | Multi-hop audit questions ("vendors with expired GMP AND no current audit") that single-shot RAG fails | Phase 2 |
| **HITL review queue** for low-confidence extractions | Medium | Mirrors real pharma workflow (nothing ships without human sign-off) | Phase 2 |
| **Before/after benchmark dashboard** (Phase 1 vs Phase 2 on same corpus) | Medium | Rare in student demos — shows engineering discipline, not just tool chaining | Phase 3 |
| **Confidence calibration** (scores that actually mean something — validated on gold set) | Medium | Distinguishes "looks confident" from "is well-calibrated" | Phase 2 |
| **Per-question cost + latency tracking** | Low | Demonstrates production awareness | Phase 1/2 |

### 5.3 Anti-Features — Deliberately NOT Build

Scope discipline is critical for a demo. The following are tempting but corrosive to timeline/focus:

| Anti-Feature | Why Not | What To Do Instead |
|---|---|---|
| **User authentication / RBAC** | Out of scope per PROJECT.md; adds no demo value | Single-user Streamlit session |
| **Multi-tenant / workspace isolation** | Same as above | N/A |
| **Live supplier portal integrations** (SAP, Ariba, etc.) | Months of work, zero demo payoff | Folder-of-PDFs input |
| **Writing back to source systems** (mark doc as reviewed in external QMS) | Side effects = audit risk; irrelevant for demo | Read-only dashboard |
| **Automatic CAPA/deviation creation** | Deep workflow territory; out of scope | Flag only, don't act |
| **Non-PDF ingestion** (Word, Excel, email attachments) | Out of scope per PROJECT.md | PDF-only, state this clearly |
| **Fine-tuning any models** | Out of scope per PROJECT.md; API models suffice | Claude Sonnet / Gemini 2.5 Flash via API |
| **Generating regulatory submissions** (eCTD, annual reports) | Submission-quality is a 6-month project on its own | Analysis-only |
| **Real-time monitoring / cron / scheduled re-ingestion** | Adds infra complexity; demo is on-demand | Manual re-ingest per demo run |
| **Custom OCR training per document template** | Docling generalizes; per-template fragile | Trust Docling + VLM fallback |
| **Production logging/alerting (PagerDuty etc.)** | Demo is not a prod system | Langfuse traces are sufficient |
| **Full regulatory knowledge base** (explain 21 CFR to users) | Not the problem being solved | Link out to sources if needed |
| **Doc editing / annotation / redlining** | Not a compliance question | Read-only |
| **Signature verification / cryptographic validation** | Plausible but deep rabbit hole; signatures are mostly scanned images anyway | Extract-and-display, don't validate |

---

## 6. Feature Dependencies

```
PDF Ingestion (Docling)
    ├──> Field Extraction (VLM single-pass)
    │       └──> Pydantic Schema Validation
    │               ├──> Risk Engine (age/expiry flagging)
    │               │       └──> Dashboard Table + Color Coding
    │               └──> Extraction Critic (Phase 2)
    │                       ├──> Confidence Scoring
    │                       │       └──> HITL Queue Routing
    │                       │       └──> Abstention Logic
    │                       └──> Bounding-Box Citations
    │
    ├──> Chunk + BM25 Index ──┐
    ├──> Dense Embedding Index ┼──> Hybrid Retrieval + Rerank ──> RAG Answer
    └──> Page-Image Embedding (ColQwen, Phase 2) ──────────────────┤
                                                                    └──> LangGraph Agentic Loop (Phase 2)
                                                                              └──> Self-Critique Faithfulness

All steps ──> Langfuse Trace ──> Observability Dashboard
All outputs ──> Eval Harness ──> Phase 1 vs Phase 2 Benchmark
```

---

## 7. MVP Recommendation (Maps to PROJECT.md Phase 1)

Ship in this order:

1. **Ingestion → extraction → Pydantic** (one doc, end-to-end, before scaling to folder)
2. **Risk flagging on extracted dates** (the payoff — first visible compliance value)
3. **Streamlit table with color coding + source page link** (demoable surface)
4. **Hybrid RAG with citations** (the "ask questions" story)
5. **Eval harness on ~50 hand-labeled pages** (numbers to beat in Phase 2)

**Defer to Phase 2:** ColQwen, critic loop, LangGraph, HITL, abstention. These are the "upgrade" that the benchmark measures against.

**Defer forever:** Everything in the Anti-Features table.

---

## 8. Complexity Summary

| Feature Cluster | Complexity | Risk |
|---|---|---|
| Docling ingestion + VLM extraction | Medium | Known-good tools, well-documented |
| Pydantic schema + risk engine | Low | Straightforward |
| Streamlit dashboard | Low | Streamlit's sweet spot |
| Hybrid RAG | Medium | Standard pattern now |
| Eval harness | Medium | Hand-labeling ~50 pages takes real time |
| ColQwen2 visual retrieval | High | GPU requirement, newer tech, less documentation |
| Agentic critic loop | High | Prompt engineering + reconciliation logic |
| LangGraph RAG | High | State machine complexity |
| Confidence calibration | High | Requires validated gold set + calibration method |
| Langfuse tracing | Low | Config/decorator |

---

## Sources

Primary regulatory and domain sources (HIGH confidence):
- [IPEC Certificate of Analysis Guide 2024](https://www.gmp-compliance.org/files/guidemgr/2024-coa-guide-f-1720781885.pdf)
- [GMP Requirements for CoA — ECA Academy](https://www.gmp-compliance.org/gmp-news/gmp-requirements-for-certificates-of-analysis-coa)
- [WHO Model Certificate of Analysis](https://cdn.who.int/media/docs/default-source/medicines/norms-and-standards/guidelines/quality-control/trs1010_annex4_who_model_certificate_analysis.pdf)
- [USP General Chapter <1083> Supplier Qualification](https://www.usp.org/sites/default/files/usp/document/supply-chain/apec-toolkit/USP%20GC1083.pdf)
- [ISPE GMP Audit Checklist](https://ispe.org/initiatives/regulatory-resources/gmp/audit-checklist)
- [PIC/S Guidance on Data Integrity](https://picscheme.org/docview/4234)
- [ALCOA++ Principles — Quanticate](https://www.quanticate.com/blog/alcoa-principles)

21 CFR Part 11 / regulatory compliance (HIGH confidence):
- [21 CFR Part 11 Compliance — SimplerQMS](https://simplerqms.com/21-cfr-part-11-requirements/)
- [21 CFR Part 11 Supply Chain — Qualio](https://www.qualio.com/blog/21-cfr-part-11-supply-chain)

Domain-specific feature references (MEDIUM confidence):
- [RAG Performance on Pharmaceutical Documents — IntuitionLabs](https://intuitionlabs.ai/articles/rag-performance-pharmaceutical-documents)
- [Pharmaceutical Document Management — SimplerQMS](https://simplerqms.com/pharmaceutical-document-management/)
- [Pharma Compliance Dashboards — Greenwolf](https://greenwolftechlabs.com/pharma-compliance-dashboard/)
- [Top 7 Pharma Compliance Software 2026 — SafetyCulture](https://safetyculture.com/apps/pharmaceutical-regulatory-compliance-software)
- [Supplier Compliance Software — Kodiak Hub](https://www.kodiakhub.com/blog/supplier-compliance-software)
- [Vendor Audits Checklist — Pharmaguideline](https://www.pharmaguideline.com/2017/02/vendor-audits-checklist-pharmaceuticals.html)
- [Supplier Auditing — FDA Group](https://www.thefdagroup.com/blog/supplier-auditing)

OCR/extraction references (MEDIUM confidence):
- [Certificate of Analysis OCR — Klippa](https://www.klippa.com/en/ocr/logistics-documents/certificate-of-analysis/)
- [CoA OCR & Extraction — DocuPipe](https://www.docupipe.ai/landing/certificate-of-analysis)
- [CoA Automation — Nanonets](https://nanonets.com/document-ocr/certificate-of-analysis)
