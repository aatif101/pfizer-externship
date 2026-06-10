"""Recompute and persist compliance risk from the latest extractions.

This script re-derives risk metadata (risk_level / risk_reason / compliance_status
/ age_days) for already-extracted documents using the current
``src.extraction.risk.compute_record_risk`` logic, then re-persists the compliance
record. It does NOT call any provider and makes no network/API calls: it reuses the
field values already stored by a prior extraction run.

Use this after a deterministic change to risk scoring (e.g. the printed-"N/A"
expiry rule in docs/field-definitions.md) to refresh persisted verdicts without a
costly re-extraction.

Safety: prints only doc_id / vendor / dates / risk_level — never page text, image
bytes, prompts, or secrets. compliance.db is gitignored; ONLY this script is
committed, never any .db file.

Usage:
    python scripts/recompute_compliance_risk.py [--db-path PATH] [--today YYYY-MM-DD]
    python scripts/recompute_compliance_risk.py --doc-id 8652295bf141a3a0
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import date
from pathlib import Path

# Allow `python scripts/recompute_compliance_risk.py` from the repo root without
# requiring package installation or PYTHONPATH tweaks on Windows.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.extraction.repository import get_extraction_record, upsert_extraction_record
from src.extraction.risk import compute_record_risk

DEFAULT_DB_PATH = str(PROJECT_ROOT / "compliance.db")


def _list_doc_ids(db_path: str) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT doc_id FROM compliance_records ORDER BY doc_id").fetchall()
    finally:
        conn.close()
    return [str(row[0]) for row in rows]


def recompute(db_path: str, *, today: date, doc_ids: list[str] | None = None) -> int:
    """Recompute and persist risk for the given (or all) documents. Returns count."""

    targets = doc_ids if doc_ids else _list_doc_ids(db_path)
    updated = 0
    for doc_id in targets:
        record = get_extraction_record(db_path, doc_id)
        if record is None:
            print(f"SKIP doc_id={doc_id} (no complete extraction record)")
            continue

        risk = compute_record_risk(record, today=today)
        record.risk_level = risk.risk_level
        record.risk_reason = risk.risk_reason
        record.compliance_status = risk.compliance_status
        record.age_days = risk.age_days

        upsert_extraction_record(db_path, record)
        updated += 1
        print(
            f"OK doc_id={doc_id} risk_level={risk.risk_level} "
            f"compliance_status={risk.compliance_status} age_days={risk.age_days}"
        )
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description="Recompute compliance risk from latest extractions.")
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH, help="SQLite compliance database path.")
    parser.add_argument("--today", default=None, help="Override 'today' as YYYY-MM-DD (default: system date).")
    parser.add_argument("--doc-id", action="append", default=None, help="Restrict to one or more doc_ids.")
    args = parser.parse_args()

    today = date.fromisoformat(args.today) if args.today else date.today()
    updated = recompute(args.db_path, today=today, doc_ids=args.doc_id)
    print(f"SUMMARY recomputed={updated} today={today.isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
