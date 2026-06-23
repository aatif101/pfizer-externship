"""Offline data-fix test for the rq_ex3 gold mojibake repair.

Pure SQLite data fix — no GPU, no fabricated metric. Asserts the repair (a)
replaces U+FFFD with Ä in the rq_ex3 row, (b) leaves an unrelated gold row
byte-identical, and (c) is idempotent (a second run changes 0 rows).
"""

from __future__ import annotations

import sqlite3

from scripts.repair_gold_ex3_mojibake import repair_gold_ex3_mojibake
from src.db.schema import init_db

# Explicit codepoints so the test does not depend on file/console encoding.
MOJIBAKE = "�"  # U+FFFD REPLACEMENT CHARACTER (rendered as the box/diamond)
AKTA_OK = "ÄKTA"  # "ÄKTA" with U+00C4
AKTA_BAD = f"{MOJIBAKE}KTA"


def _insert_gold_query(conn: sqlite3.Connection, query_id: str, query_text: str) -> None:
    conn.execute(
        "INSERT INTO gold_retrieval_queries (query_id, query_text) VALUES (?, ?)",
        (query_id, query_text),
    )


def _query_text(conn: sqlite3.Connection, query_id: str) -> str:
    row = conn.execute(
        "SELECT query_text FROM gold_retrieval_queries WHERE query_id = ?",
        (query_id,),
    ).fetchone()
    assert row is not None
    return row[0]


def test_repair_fixes_mojibake_leaves_others_and_is_idempotent(tmp_path):
    db_path = str(tmp_path / "gold.sqlite")
    init_db(db_path)

    corrupted = f"What document type is the Cytiva {AKTA_BAD} ready Gradient Flow Section."
    unrelated = "What is the vendor name on the certificate?"

    conn = sqlite3.connect(db_path)
    try:
        _insert_gold_query(conn, "rq_ex3_doc_type", corrupted)
        _insert_gold_query(conn, "rq_other_vendor", unrelated)
        conn.commit()
    finally:
        conn.close()

    changed = repair_gold_ex3_mojibake(db_path)
    assert changed == 1

    conn = sqlite3.connect(db_path)
    try:
        repaired = _query_text(conn, "rq_ex3_doc_type")
        # (a) the rq_ex3 row is repaired: contains ÄKTA, no replacement char.
        assert AKTA_OK in repaired
        assert MOJIBAKE not in repaired
        # (b) the unrelated gold row is byte-identical (untouched).
        assert _query_text(conn, "rq_other_vendor") == unrelated
    finally:
        conn.close()

    # (c) idempotent: a second run changes 0 rows and the text is unchanged.
    changed_again = repair_gold_ex3_mojibake(db_path)
    assert changed_again == 0

    conn = sqlite3.connect(db_path)
    try:
        assert _query_text(conn, "rq_ex3_doc_type") == corrupted.replace(MOJIBAKE, "Ä")
    finally:
        conn.close()


def test_repair_vendor_row_without_mojibake_is_noop(tmp_path):
    db_path = str(tmp_path / "gold.sqlite")
    init_db(db_path)

    clean = f"Who is the vendor for the {AKTA_OK} ready Gradient Flow Section?"
    conn = sqlite3.connect(db_path)
    try:
        _insert_gold_query(conn, "rq_ex3_vendor", clean)
        conn.commit()
    finally:
        conn.close()

    changed = repair_gold_ex3_mojibake(db_path)
    assert changed == 0

    conn = sqlite3.connect(db_path)
    try:
        assert _query_text(conn, "rq_ex3_vendor") == clean
    finally:
        conn.close()
