"""Idempotently repair the rq_ex3 gold-query mojibake (U+FFFD -> Ä).

The four Example-3 gold retrieval queries reference Cytiva's "ÄKTA ready
Gradient Flow Section". Three of them stored the Ä as a Unicode replacement
character (U+FFFD, rendered ``�``) — corrupting the gold query text. This script
replaces U+FFFD with Ä (U+00C4) in the ``rq_ex3_*`` rows of
``gold_retrieval_queries``. It is idempotent: every UPDATE is guarded on the
current query_text, so a second run changes 0 rows. The vendor row carries no
mojibake and is left byte-identical.

Safety: prints only query_ids / row counts — never page text, query text, image
bytes, or secrets. compliance.db is gitignored; ONLY this script is committed,
never any .db file.

Usage:
    python scripts/repair_gold_ex3_mojibake.py [--db-path PATH]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

# Allow `python scripts/repair_gold_ex3_mojibake.py` from the repo root without
# requiring package installation or PYTHONPATH tweaks on Windows.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.db.schema import _connect

DEFAULT_DB_PATH = str(PROJECT_ROOT / "compliance.db")

# U+FFFD (REPLACEMENT CHARACTER) -> U+00C4 (LATIN CAPITAL LETTER A WITH DIAERESIS).
MOJIBAKE_CHAR = "�"
REPAIRED_CHAR = "Ä"

# The Example-3 gold query ids. rq_ex3_vendor has no mojibake; its guarded
# UPDATE is a natural no-op (repaired == current).
TARGET_QUERY_IDS: tuple[str, ...] = (
    "rq_ex3_doc_type",
    "rq_ex3_mfg",
    "rq_ex3_expiry",
    "rq_ex3_vendor",
)


def repair_query(conn: sqlite3.Connection, query_id: str) -> int:
    """Replace U+FFFD with Ä in one gold query, guarded; return rows changed.

    Reads the current query_text, computes the repaired text, and runs a guarded
    UPDATE keyed on (query_id, current query_text) so a second run — where the
    text is already repaired — matches nothing and changes 0 rows. A row with no
    mojibake produces repaired == current and the guard makes it a no-op too.
    """

    row = conn.execute(
        "SELECT query_text FROM gold_retrieval_queries WHERE query_id = ?",
        (query_id,),
    ).fetchone()
    if row is None:
        return 0
    current = row[0]
    repaired = current.replace(MOJIBAKE_CHAR, REPAIRED_CHAR)
    if repaired == current:
        return 0
    cursor = conn.execute(
        """
        UPDATE gold_retrieval_queries
        SET query_text = ?
        WHERE query_id = ? AND query_text = ?
        """,
        (repaired, query_id, current),
    )
    return cursor.rowcount


def repair_gold_ex3_mojibake(db_path: str) -> int:
    """Repair all rq_ex3 gold queries in db_path. Return total rows changed."""

    conn = _connect(db_path)
    total_changed = 0
    try:
        for query_id in TARGET_QUERY_IDS:
            changed = repair_query(conn, query_id)
            total_changed += changed
            print(f"{query_id}: rows_changed={changed}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    print(f"total_rows_changed={total_changed}")
    print("Reminder: compliance.db is gitignored and must NEVER be staged.")
    return total_changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        help="Path to compliance.db (default: project compliance.db).",
    )
    args = parser.parse_args(argv)
    repair_gold_ex3_mojibake(args.db_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
