"""Backfill OCR-derived page text for blank/short pages, then rebuild the index.

Usage:
    python scripts/backfill_ocr_text.py --db-path compliance.db

This writes OCR text to ``page_ocr_texts`` only. It never overwrites
``pages.page_text``. After backfill it rebuilds the retrieval index so the text
tier indexes original + OCR-derived text together.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.retrieval.indexer import build_retrieval_index
from src.retrieval.ocr_backfill import DEFAULT_LOW_TEXT_THRESHOLD, DEFAULT_OCR_SOURCE, backfill_low_text_pages

DEFAULT_DB_PATH = str(PROJECT_ROOT / "compliance.db")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--min-text-length", type=int, default=DEFAULT_LOW_TEXT_THRESHOLD)
    parser.add_argument("--source", default=DEFAULT_OCR_SOURCE)
    args = parser.parse_args(argv)

    result = backfill_low_text_pages(
        args.db_path,
        min_text_length=args.min_text_length,
        source=args.source,
    )
    print(f"ocr_candidates={result.candidate_count}")
    print(f"ocr_records_written={result.written_count}")
    index_result = build_retrieval_index(args.db_path)
    print(f"retrieval_run_id={index_result.run.run_id}")
    print(f"indexed_pages={index_result.run.indexed_page_count}")
    print("Reminder: compliance.db is gitignored and must NEVER be staged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
