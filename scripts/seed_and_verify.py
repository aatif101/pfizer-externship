"""End-to-end seed + eval verification script.

Steps:
1. Init the DB schema (compliance.db)
2. Seed documents, pages, compliance records, and a real retrieval index
3. Seed gold queries + targets
4. Run the retrieval eval runner twice (simulates two different pipeline runs)
5. Print a summary table of recent runs + metrics

Run with:
    venv/Scripts/python.exe scripts/seed_and_verify.py
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

# Ensure repo root is on sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DB_PATH = str(ROOT / "compliance.db")

print(f"Using database: {DB_PATH}")

# ── 1. Init schema ───────────────────────────────────────────────────────────
from src.db.schema import init_db

init_db(DB_PATH)
print("[1/5] Schema initialized.")


# ── 2. Seed documents + pages ────────────────────────────────────────────────
def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


DOCS = [
    {
        "doc_id": "doc_coa_001",
        "filename": "pfizer_coa_aspirin_2024.pdf",
        "file_path": "data/pfizer_coa_aspirin_2024.pdf",
        "page_count": 2,
    },
    {
        "doc_id": "doc_coa_002",
        "filename": "vendor_cert_ibuprofen_2023.pdf",
        "file_path": "data/vendor_cert_ibuprofen_2023.pdf",
        "page_count": 3,
    },
    {
        "doc_id": "doc_sdf_003",
        "filename": "supplier_sdf_acetaminophen_expired.pdf",
        "file_path": "data/supplier_sdf_acetaminophen_expired.pdf",
        "page_count": 2,
    },
    {
        "doc_id": "doc_coa_004",
        "filename": "pfizer_coa_amoxicillin_2025.pdf",
        "file_path": "data/pfizer_coa_amoxicillin_2025.pdf",
        "page_count": 1,
    },
]

PAGES = [
    # doc_coa_001
    (
        "doc_coa_001",
        0,
        "Certificate of Analysis for Aspirin 500mg batch PFZ-2024-0823. "
        "Manufacturer: Pfizer Inc. Expiry date: 2026-08-01. "
        "All quality parameters meet USP specifications. Lot number: L20240823.",
    ),
    (
        "doc_coa_001",
        1,
        "Test results summary: Assay 99.8% (spec 98.0-102.0%). "
        "Dissolution at 30 min: 96% (spec NLT 80%). Microbial limits: compliant. "
        "Release date: 2024-08-23. Authorized signatory: Dr. J. Smith, QA Director.",
    ),
    # doc_coa_002
    (
        "doc_coa_002",
        0,
        "Vendor Certificate: Ibuprofen 200mg bulk API. "
        "Supplier: ChemSource GmbH. Certificate valid through 2025-12-31. "
        "This vendor certificate is expiring soon and expires within 6 months. "
        "COA reference: CS-IBU-2023-0441. Batch ID: B2023441.",
    ),
    (
        "doc_coa_002",
        1,
        "Identity confirmed by IR spectroscopy. Purity: 99.5% by HPLC. "
        "Heavy metals: < 10 ppm. Residual solvents: within ICH Q3C limits.",
    ),
    (
        "doc_coa_002",
        2,
        "Conclusion: This batch meets all acceptance criteria per Pfizer "
        "supplier qualification SOP-QA-112. Approved for use.",
    ),
    # doc_sdf_003
    (
        "doc_sdf_003",
        0,
        "Supplier Data Form: Acetaminophen 500mg tablets. "
        "Document type: SDF. Expiry date: 2023-06-15. EXPIRED. "
        "Vendor: GenericPharma Ltd. DO NOT USE - document past validity.",
    ),
    (
        "doc_sdf_003",
        1,
        "This document expired on 2023-06-15. "
        "Please request an updated SDF from the supplier before processing.",
    ),
    # doc_coa_004
    (
        "doc_coa_004",
        0,
        "Certificate of Analysis: Amoxicillin Trihydrate 500mg. "
        "Manufacturer: Pfizer Ireland Pharmaceuticals. Expiry: 2027-03-15. "
        "All specifications met. Batch: AMX-2025-0312. Release date: 2025-03-12.",
    ),
]

conn = _connect(DB_PATH)
try:
    for doc in DOCS:
        conn.execute(
            """
            INSERT INTO documents (doc_id, filename, file_path, page_count, status)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(doc_id) DO UPDATE SET
                filename = excluded.filename,
                file_path = excluded.file_path,
                page_count = excluded.page_count,
                status = excluded.status
            """,
            (doc["doc_id"], doc["filename"], doc["file_path"], doc["page_count"], "ingested"),
        )
    for doc_id, page_num, page_text in PAGES:
        conn.execute(
            """
            INSERT INTO pages (doc_id, page_num, page_text)
            VALUES (?, ?, ?)
            ON CONFLICT(doc_id, page_num) DO UPDATE SET
                page_text = excluded.page_text
            """,
            (doc_id, page_num, page_text),
        )
    conn.commit()
finally:
    conn.close()

print(f"[2/5] Seeded {len(DOCS)} documents and {len(PAGES)} pages as indexable ingested records.")


# ── 3. Seed compliance records ───────────────────────────────────────────────
COMPLIANCE = [
    ("doc_coa_001", "CertificateOfAnalysis", "Pfizer Inc.", "2024-08-23", "2026-08-01", "compliant", "low", None),
    (
        "doc_coa_002",
        "VendorCertificate",
        "ChemSource GmbH",
        "2023-04-01",
        "2025-12-31",
        "expiring_soon",
        "medium",
        "Certificate expires within 6 months",
    ),
    (
        "doc_sdf_003",
        "SupplierDataForm",
        "GenericPharma Ltd.",
        "2023-01-10",
        "2023-06-15",
        "expired",
        "high",
        "Document expired on 2023-06-15",
    ),
    (
        "doc_coa_004",
        "CertificateOfAnalysis",
        "Pfizer Ireland Pharmaceuticals",
        "2025-03-12",
        "2027-03-15",
        "compliant",
        "low",
        None,
    ),
]

conn = _connect(DB_PATH)
try:
    for doc_id, doc_type, vendor, mfg_date, expiry, status, risk, risk_reason in COMPLIANCE:
        conn.execute(
            """
            INSERT INTO compliance_records
                (doc_id, doc_type, vendor_name, manufacturing_date, expiry_date, compliance_status, risk_level, risk_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(doc_id) DO UPDATE SET
                doc_type = excluded.doc_type,
                vendor_name = excluded.vendor_name,
                manufacturing_date = excluded.manufacturing_date,
                expiry_date = excluded.expiry_date,
                compliance_status = excluded.compliance_status,
                risk_level = excluded.risk_level,
                risk_reason = excluded.risk_reason,
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            """,
            (doc_id, doc_type, vendor, mfg_date, expiry, status, risk, risk_reason),
        )
    conn.commit()
finally:
    conn.close()

print(f"[3/5] Seeded {len(COMPLIANCE)} compliance records.")


# ── 4. Build retrieval index + seed gold queries ─────────────────────────────
from src.retrieval.indexer import build_retrieval_index, get_retrieval_index_status

# Older local demo databases may contain the historical invalid status value
# "complete" in retrieval_index_runs. Normalize it before the typed indexer reads
# the latest run so the script remains rerunnable on existing demo DBs.
conn = _connect(DB_PATH)
try:
    conn.execute("UPDATE retrieval_index_runs SET status = 'built' WHERE status = 'complete'")
    conn.commit()
finally:
    conn.close()

index_result = build_retrieval_index(DB_PATH)
index_status = get_retrieval_index_status(DB_PATH)

GOLD_QUERIES = [
    {
        "query_id": "q_expiry_001",
        "query_text": "Which supplier data form is expired?",
        "notes": "Compliance check — expired SDF",
        "targets": [("doc_sdf_003", 0)],
    },
    {
        "query_id": "q_expiring_002",
        "query_text": "Which vendor certificate expires within 6 months?",
        "notes": "Compliance check — expiring vendor certificate",
        "targets": [("doc_coa_002", 0)],
    },
    {
        "query_id": "q_batch_002",
        "query_text": "What is the batch number for the aspirin certificate of analysis?",
        "notes": "Field lookup — aspirin batch ID",
        "targets": [("doc_coa_001", 0)],
    },
]

conn = _connect(DB_PATH)
try:
    for q in GOLD_QUERIES:
        conn.execute(
            """
            INSERT INTO gold_retrieval_queries (query_id, query_text, notes)
            VALUES (?, ?, ?)
            ON CONFLICT(query_id) DO UPDATE SET
                query_text = excluded.query_text,
                notes = excluded.notes
            """,
            (q["query_id"], q["query_text"], q["notes"]),
        )
        conn.execute("DELETE FROM gold_retrieval_targets WHERE query_id = ?", (q["query_id"],))
        for doc_id, page_num in q["targets"]:
            conn.execute(
                "INSERT INTO gold_retrieval_targets (query_id, doc_id, page_num) VALUES (?, ?, ?)",
                (q["query_id"], doc_id, page_num),
            )
    conn.commit()
finally:
    conn.close()

print(
    "[4/5] Built retrieval index "
    f"{index_result.run.run_id} ({index_status.status.value}, {index_status.indexed_page_count} pages) "
    f"+ seeded {len(GOLD_QUERIES)} gold queries."
)


# ── 5. Run eval twice ────────────────────────────────────────────────────────
from src.eval.repository import list_eval_metrics, list_eval_runs
from src.eval.retrieval_eval_runner import run_retrieval_eval

print("[5/5] Running retrieval eval (run 1)...")
run_id_1 = run_retrieval_eval(DB_PATH, k_values=[5, 10])
print(f"       run_id_1 = {run_id_1}")

print("       Running retrieval eval (run 2)...")
run_id_2 = run_retrieval_eval(DB_PATH, k_values=[5, 10])
print(f"       run_id_2 = {run_id_2}")


# ── Print summary ────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("EVAL RUNS IN DATABASE")
print("=" * 60)

runs = list_eval_runs(DB_PATH)
print(f"Total runs: {len(runs)}")
for run in runs:
    print(f"\n  run_id:    {run.run_id}")
    print(f"  eval_type: {run.eval_type}")
    print(f"  status:    {run.status}")
    print(f"  created:   {run.created_at}")

    metrics = list_eval_metrics(DB_PATH, run.run_id)
    global_metrics = [m for m in metrics if m.scope_type is None]
    if global_metrics:
        print(f"  metrics ({len(global_metrics)} global):")
        for m in global_metrics:
            val = f"{m.metric_value:.4f}" if m.metric_value is not None else "None"
            print(f"    {m.metric_name}: {val}")
    else:
        print("  metrics: (none)")

print("\n" + "=" * 60)
print("COMPLIANCE RECORDS IN DATABASE")
print("=" * 60)

conn = _connect(DB_PATH)
try:
    rows = conn.execute(
        "SELECT doc_id, doc_type, vendor_name, expiry_date, compliance_status, risk_level FROM compliance_records"
    ).fetchall()
finally:
    conn.close()

for row in rows:
    print(f"  {row[0]:20} | {row[2]:35} | expiry={row[3]} | {row[4]:15} | risk={row[5]}")

print("\nSeed complete. Start Streamlit with:")
print("  venv/Scripts/python.exe -m streamlit run src/app.py")
print("Then open the Eval tab to verify the latest two runs appear with 100% retrieval metrics.\n")
