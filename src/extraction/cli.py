"""Command-line entrypoints for SDF extraction runs.

The CLI is intentionally import-safe: live provider credentials are checked only
when a command constructs the Gemini provider, and Langfuse availability is a
non-fatal diagnostic. Output is operator-oriented and excludes page text, raw
provider responses, image bytes, and secret values.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

import typer

from src.config import get_settings
from src.db.queries import list_documents
from src.extraction.gemini import GeminiSDFExtractionProvider, GeminiSDFVisualFallbackProvider
from src.extraction.pipeline import ExtractionPipelineError, extract_document as run_extraction
from src.extraction.providers import (
    ExtractionConfigurationError,
    ExtractionProviderError,
    SDFExtractionProvider,
    SDFVisualFallbackProvider,
)

app = typer.Typer(help="Run Pfizer SDF extraction against ingested documents.", no_args_is_help=True)


@dataclass(frozen=True)
class CommandResult:
    """Small non-secret summary of a CLI extraction command."""

    attempted: int
    succeeded: int
    failed: int


class SafeCliError(RuntimeError):
    """User-facing CLI failure that is safe to print."""

    def __init__(self, message: str, *, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def build_provider(provider: str) -> SDFExtractionProvider:
    """Construct the requested text provider lazily.

    Tests may monkeypatch this seam with a fake provider. The production default
    is Gemini and therefore fails clearly when ``GEMINI_API_KEY`` is absent.
    """

    provider_name = provider.strip().lower()
    if provider_name == "gemini":
        return GeminiSDFExtractionProvider()
    raise SafeCliError(f"Unsupported extraction provider '{provider}'.", exit_code=2)


def build_visual_provider(provider: str) -> SDFVisualFallbackProvider:
    """Construct the requested visual fallback provider lazily.

    Visual fallback is opt-in only. This seam must not be called by default CLI
    runs because constructing the live Gemini provider checks credentials.
    """

    provider_name = provider.strip().lower()
    if provider_name == "gemini":
        return GeminiSDFVisualFallbackProvider()
    raise SafeCliError(f"Unsupported visual fallback provider '{provider}'.", exit_code=2)


def _trace_status() -> str:
    settings = get_settings()
    if not settings.langfuse_enabled:
        return "disabled"
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return "not_configured"
    return "configured"


def _safe_error_message(exc: BaseException, *, doc_id: str | None = None) -> str:
    reason_code = getattr(exc, "reason_code", exc.__class__.__name__)
    parts = [f"reason={reason_code}"]
    if doc_id:
        parts.append(f"doc_id={doc_id}")
    exc_run_id = getattr(exc, "run_id", None)
    if exc_run_id:
        parts.append(f"run_id={exc_run_id}")
    parts.append(f"error_class={exc.__class__.__name__}")
    return "Extraction failed (" + ", ".join(parts) + ")."


def _extract_one(
    *,
    db_path: str,
    doc_id: str,
    provider: SDFExtractionProvider,
    run_id: str | None = None,
    visual_provider: SDFVisualFallbackProvider | None = None,
) -> None:
    result = run_extraction(db_path, doc_id, provider, run_id=run_id, visual_provider=visual_provider)
    diagnostics = result.diagnostics
    typer.echo(
        "OK "
        f"doc_id={diagnostics.doc_id} "
        f"run_id={diagnostics.run_id} "
        f"trace_id={diagnostics.trace_id or 'none'} "
        f"pages={diagnostics.page_count} "
        f"review_state={diagnostics.review_state} "
        f"needs_review={str(diagnostics.needs_review).lower()}"
    )


@app.command("extract")
def extract_command(
    doc_id: Annotated[str, typer.Option("--doc-id", help="Document ID to extract.")],
    db_path: Annotated[str, typer.Option("--db-path", help="SQLite compliance database path.")],
    provider_name: Annotated[str, typer.Option("--provider", help="Extraction provider to use.")] = "gemini",
    run_id: Annotated[str | None, typer.Option("--run-id", help="Optional extraction run ID to persist.")] = None,
    visual_fallback: Annotated[
        bool,
        typer.Option(
            "--visual-fallback",
            help="Opt in to targeted Gemini visual fallback for missing or suspicious fields.",
        ),
    ] = False,
) -> None:
    """Extract and persist one ingested document's six SDF fields."""

    typer.echo(
        f"Starting extraction doc_id={doc_id} provider={provider_name} "
        f"trace_status={_trace_status()} run_id={run_id or 'auto'} "
        f"visual_fallback={str(visual_fallback).lower()}"
    )
    try:
        provider = build_provider(provider_name)
        visual_provider = build_visual_provider(provider_name) if visual_fallback else None
        _extract_one(
            db_path=db_path,
            doc_id=doc_id,
            provider=provider,
            run_id=run_id,
            visual_provider=visual_provider,
        )
    except ExtractionConfigurationError as exc:
        typer.echo(_safe_error_message(exc, doc_id=doc_id), err=True)
        raise typer.Exit(2) from exc
    except (ExtractionPipelineError, ExtractionProviderError, SafeCliError) as exc:
        typer.echo(_safe_error_message(exc, doc_id=doc_id), err=True)
        raise typer.Exit(getattr(exc, "exit_code", 1)) from exc


@app.command("extract-all")
def extract_all_command(
    db_path: Annotated[str, typer.Option("--db-path", help="SQLite compliance database path.")],
    provider_name: Annotated[str, typer.Option("--provider", help="Extraction provider to use.")] = "gemini",
    run_id: Annotated[str | None, typer.Option("--run-id", help="Optional shared extraction run ID to persist.")] = None,
    visual_fallback: Annotated[
        bool,
        typer.Option(
            "--visual-fallback",
            help="Opt in to targeted Gemini visual fallback for missing or suspicious fields.",
        ),
    ] = False,
) -> None:
    """Extract and persist all documents with status='ingested'."""

    documents = sorted(
        (document for document in list_documents(db_path) if document.get("status") == "ingested"),
        key=lambda document: str(document.get("doc_id", "")),
    )
    if not documents:
        typer.echo("No ingested documents found for extraction.", err=True)
        raise typer.Exit(1)

    typer.echo(
        f"Starting batch extraction provider={provider_name} trace_status={_trace_status()} "
        f"docs={len(documents)} run_id={run_id or 'auto'} "
        f"visual_fallback={str(visual_fallback).lower()}"
    )
    try:
        provider = build_provider(provider_name)
        visual_provider = build_visual_provider(provider_name) if visual_fallback else None
    except ExtractionConfigurationError as exc:
        typer.echo(_safe_error_message(exc), err=True)
        raise typer.Exit(2) from exc
    except SafeCliError as exc:
        typer.echo(_safe_error_message(exc), err=True)
        raise typer.Exit(exc.exit_code) from exc

    succeeded = 0
    failed = 0
    for document in documents:
        doc_id = str(document["doc_id"])
        try:
            _extract_one(
                db_path=db_path,
                doc_id=doc_id,
                provider=provider,
                run_id=run_id,
                visual_provider=visual_provider,
            )
            succeeded += 1
        except (ExtractionPipelineError, ExtractionProviderError) as exc:
            failed += 1
            typer.echo(_safe_error_message(exc, doc_id=doc_id), err=True)

    typer.echo(f"SUMMARY attempted={len(documents)} succeeded={succeeded} failed={failed}")
    if failed:
        raise typer.Exit(1)


if __name__ == "__main__":  # pragma: no cover - exercised by Typer runner/tests.
    app()
