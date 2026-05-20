"""Command-line entrypoints for provider-free retrieval index operations.

The retrieval CLI is intentionally offline-safe. It inspects only local SQLite
source tables and persisted retrieval metadata, never prints page text, image
blobs, provider responses, or secrets, and uses compact reason codes suitable
for health checks and dashboard setup diagnostics.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Annotated

import typer

from src.retrieval.indexer import RetrievalIndexBuildResult, build_retrieval_index, get_retrieval_index_status
from src.retrieval.models import RetrievalIndexStatus, RetrievalIndexStatusReport

app = typer.Typer(help="Build and inspect the provider-free retrieval index.", no_args_is_help=True)

_REQUIRED_SOURCE_TABLES = frozenset({"documents", "pages"})
_HASH_PREFIX_CHARS = 12


class SafeCliError(RuntimeError):
    """User-facing retrieval CLI failure that is safe to print."""

    def __init__(self, reason_code: str, *, exit_code: int = 1) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.exit_code = exit_code


def _preflight_source_database(db_path: str) -> None:
    """Ensure the target is an existing readable ingestion database.

    The indexer may initialize retrieval-specific tables, but the CLI should not
    turn a typo in --db-path into a brand-new empty ingestion database.
    """

    path = Path(db_path)
    if not path.exists() or not path.is_file():
        raise SafeCliError("db_missing", exit_code=2)

    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ('documents', 'pages')"
                ).fetchall()
            }
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise SafeCliError("db_unreadable", exit_code=2) from exc

    if not _REQUIRED_SOURCE_TABLES.issubset(tables):
        raise SafeCliError("schema_missing", exit_code=2)


def _hash_prefix(content_hash: str | None) -> str:
    return (content_hash or "none")[:_HASH_PREFIX_CHARS]


def _reason_code(report: RetrievalIndexStatusReport) -> str:
    if report.error_reason:
        return report.error_reason
    if report.status is RetrievalIndexStatus.MISSING:
        return "index_missing"
    if report.status is RetrievalIndexStatus.EMPTY:
        return "corpus_empty"
    if report.status is RetrievalIndexStatus.STALE:
        return "corpus_stale"
    return "none"


def _echo_report(report: RetrievalIndexStatusReport) -> None:
    typer.echo(
        " ".join(
            [
                f"status={report.status.value}",
                f"run_id={report.run_id or 'none'}",
                f"indexed_docs={report.source_document_count}",
                f"indexed_pages={report.indexed_page_count}",
                f"source_pages={report.source_page_count}",
                f"content_hash={_hash_prefix(report.content_hash)}",
                f"previous_content_hash={_hash_prefix(report.previous_content_hash)}",
                f"stale={str(report.is_stale).lower()}",
                f"reason={_reason_code(report)}",
            ]
        )
    )


def _echo_build_result(result: RetrievalIndexBuildResult) -> None:
    run = result.run
    typer.echo(
        " ".join(
            [
                f"status={run.status.value}",
                f"run_id={run.run_id}",
                f"indexed_docs={run.source_document_count}",
                f"indexed_pages={run.indexed_page_count}",
                f"source_pages={run.source_page_count}",
                f"content_hash={_hash_prefix(run.content_hash)}",
                f"previous_content_hash={_hash_prefix(run.previous_content_hash)}",
                f"stale={str(run.is_stale).lower()}",
                f"reason={'corpus_empty' if run.status is RetrievalIndexStatus.EMPTY else 'none'}",
            ]
        )
    )


def _exit_code_for_status(status: RetrievalIndexStatus) -> int:
    if status is RetrievalIndexStatus.BUILT:
        return 0
    if status in {RetrievalIndexStatus.MISSING, RetrievalIndexStatus.EMPTY, RetrievalIndexStatus.STALE}:
        return 1
    return 2


@app.command("build")
def build_command(
    db_path: Annotated[str, typer.Option("--db-path", help="SQLite compliance database path.")],
) -> None:
    """Build and persist the current provider-free retrieval index."""

    try:
        _preflight_source_database(db_path)
        result = build_retrieval_index(db_path)
    except SafeCliError as exc:
        typer.echo(f"status=error run_id=none indexed_docs=0 indexed_pages=0 content_hash=none stale=false reason={exc.reason_code}", err=True)
        raise typer.Exit(exc.exit_code) from exc
    except sqlite3.Error as exc:
        typer.echo("status=error run_id=none indexed_docs=0 indexed_pages=0 content_hash=none stale=false reason=db_error", err=True)
        raise typer.Exit(2) from exc

    _echo_build_result(result)
    exit_code = _exit_code_for_status(result.run.status)
    if exit_code:
        raise typer.Exit(exit_code)


@app.command("status")
def status_command(
    db_path: Annotated[str, typer.Option("--db-path", help="SQLite compliance database path.")],
) -> None:
    """Inspect retrieval index health without rebuilding it."""

    try:
        _preflight_source_database(db_path)
        report = get_retrieval_index_status(db_path)
    except SafeCliError as exc:
        typer.echo(f"status=error run_id=none indexed_docs=0 indexed_pages=0 content_hash=none stale=false reason={exc.reason_code}", err=True)
        raise typer.Exit(exc.exit_code) from exc
    except sqlite3.Error as exc:
        typer.echo("status=error run_id=none indexed_docs=0 indexed_pages=0 content_hash=none stale=false reason=db_error", err=True)
        raise typer.Exit(2) from exc

    _echo_report(report)
    exit_code = _exit_code_for_status(report.status)
    if exit_code:
        raise typer.Exit(exit_code)


if __name__ == "__main__":  # pragma: no cover - exercised by Typer runner/tests.
    app()
