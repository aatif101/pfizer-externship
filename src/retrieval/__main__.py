"""Run the retrieval CLI with ``python -m src.retrieval``."""
from __future__ import annotations

from src.retrieval.cli import app


if __name__ == "__main__":  # pragma: no cover - exercised through subprocess/CLI tests.
    app()
