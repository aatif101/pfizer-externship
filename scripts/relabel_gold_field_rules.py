"""Idempotently relabel gold_extraction_labels to follow the shared rulebook.

This script updates hand-labeled gold values in a compliance.db so they agree
with docs/field-definitions.md (the single source of truth shared by extraction
prompts AND gold labels). It is idempotent: every UPDATE is guarded so a second
run changes 0 rows.

Safety: prints only doc_id / field_name / row counts — never page text, image
bytes, or secrets. compliance.db is gitignored; ONLY this script is committed,
never any .db file.

Usage:
    python scripts/relabel_gold_field_rules.py [--db-path PATH]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

# Allow `python scripts/relabel_gold_field_rules.py` from the repo root without
# requiring package installation or PYTHONPATH tweaks on Windows.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.db.schema import _connect

DEFAULT_DB_PATH = str(PROJECT_ROOT / "compliance.db")


# Each rule is an idempotent, guarded relabel: (doc_id, field_name, old_value,
# new_value). The WHERE guard on expected_value makes re-runs a no-op.
RELABEL_RULES: tuple[tuple[str, str, str, str], ...] = (
    # vendor_name must be the full legal name as printed, never an abbreviation.
    ("144fc1ed", "vendor_name", "CPC", "Colder Products Company"),
)


def _apply_rule(
    conn: sqlite3.Connection,
    *,
    doc_id: str,
    field_name: str,
    old_value: str,
    new_value: str,
) -> int:
    """Apply one guarded relabel; return number of rows changed."""

    # Update expected_value, and normalized_value too when it still holds the old
    # abbreviation. Guarded on expected_value so re-running changes 0 rows.
    cursor = conn.execute(
        """
        UPDATE gold_extraction_labels
        SET expected_value = ?,
            normalized_value = CASE
                WHEN normalized_value = ? THEN ?
                ELSE normalized_value
            END
        WHERE doc_id = ? AND field_name = ? AND expected_value = ?
        """,
        (new_value, old_value, new_value, doc_id, field_name, old_value),
    )
    return cursor.rowcount


def relabel_gold_field_rules(db_path: str) -> int:
    """Apply all relabel rules to db_path. Return total rows changed."""

    conn = _connect(db_path)
    total_changed = 0
    try:
        for doc_id, field_name, old_value, new_value in RELABEL_RULES:
            changed = _apply_rule(
                conn,
                doc_id=doc_id,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
            )
            total_changed += changed
            print(f"doc_id={doc_id} field_name={field_name} rows_changed={changed}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    print(f"total_rows_changed={total_changed}")
    return total_changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        help="Path to compliance.db (default: project compliance.db).",
    )
    args = parser.parse_args(argv)
    relabel_gold_field_rules(args.db_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
