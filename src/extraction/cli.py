"""Command-line entrypoints for SDF extraction runs.

The CLI is intentionally import-safe: live provider credentials are checked only
when a command constructs the Gemini provider, and Langfuse availability is a
non-fatal diagnostic. Output is operator-oriented and excludes page text, raw
provider responses, image bytes, and secret values.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Annotated
from uuid import uuid4

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
from src.extraction.repository import (
    ExtractionRunConflictError,
    ExtractionRunStateError,
    begin_or_resume_extraction_run,
    finalize_extraction_run,
    list_resume_candidates,
    mark_run_document_completed,
    mark_run_document_failed,
    mark_run_document_running,
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

    def __init__(self, message: str, *, exit_code: int = 1, reason_code: str = "cli_configuration_error") -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.reason_code = reason_code


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
    reason_code = _stable_reason_code(exc)
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
) -> str | None:
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
    return diagnostics.trace_id


_SAFE_CLI_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$")
_SAFE_REASON_RE = re.compile(r"^[a-z][a-z0-9_]{0,95}$")


def _normalized_provider_name(provider_name: str) -> str:
    normalized = provider_name.strip().lower()
    return normalized if _SAFE_CLI_LABEL_RE.fullmatch(normalized) else "unsupported"


def _validated_corpus_version(corpus_version: str) -> str:
    normalized = corpus_version.strip()
    if _SAFE_CLI_LABEL_RE.fullmatch(normalized) is None:
        raise SafeCliError(
            "Invalid corpus version.",
            exit_code=2,
            reason_code="invalid_corpus_version",
        )
    return normalized


def _stable_reason_code(exc: BaseException) -> str:
    reason = getattr(exc, "reason_code", None)
    if isinstance(reason, str) and _SAFE_REASON_RE.fullmatch(reason):
        return reason
    return "unexpected_error"


def _requested_model(provider_name: str) -> str:
    if provider_name == "gemini":
        configured = get_settings().gemini_model.strip()
        if _SAFE_CLI_LABEL_RE.fullmatch(configured):
            return configured
        raise SafeCliError(
            "Invalid configured model identity.",
            exit_code=2,
            reason_code="invalid_requested_model",
        )
    return "unresolved"


def _summary_line(summary, *, skipped: int) -> str:
    return (
        "SUMMARY "
        f"run_id={summary.run_id} "
        f"status={summary.status.value} "
        f"expected={summary.expected_document_count} "
        f"attempted={summary.attempted_document_count} "
        f"succeeded={summary.succeeded_document_count} "
        f"failed={summary.failed_document_count} "
        f"skipped={skipped} "
        f"corpus_version={summary.corpus_version}"
    )


def _mark_candidates_failed_after_construction_error(
    *,
    db_path: str,
    run_id: str,
    candidates,
    exc: BaseException,
) -> None:
    reason_code = _stable_reason_code(exc)
    for candidate in candidates:
        mark_run_document_running(db_path, run_id, candidate.doc_id)
        mark_run_document_failed(db_path, run_id, candidate.doc_id, reason_code=reason_code)


def _coordinate_extraction_run(
    *,
    db_path: str,
    doc_ids: tuple[str, ...],
    provider_name: str,
    run_id: str,
    corpus_version: str,
    visual_fallback: bool,
) -> None:
    """Run one manifest exactly once, preserving SQL truth across resumes."""

    requested_model = _requested_model(provider_name)
    initial = begin_or_resume_extraction_run(
        db_path,
        run_id=run_id,
        doc_ids=doc_ids,
        provider=provider_name,
        requested_model=requested_model,
        corpus_version=corpus_version,
    )
    candidates = list_resume_candidates(db_path, run_id)
    skipped = initial.expected_document_count - len(candidates)
    if not candidates:
        summary = finalize_extraction_run(db_path, run_id)
        typer.echo(_summary_line(summary, skipped=skipped))
        if summary.status.value != "completed":
            raise typer.Exit(1)
        return

    try:
        provider = build_provider(provider_name)
        visual_provider = build_visual_provider(provider_name) if visual_fallback else None
    except Exception as exc:  # noqa: BLE001 - construction boundary reduces arbitrary failures to safe codes.
        _mark_candidates_failed_after_construction_error(
            db_path=db_path,
            run_id=run_id,
            candidates=candidates,
            exc=exc,
        )
        summary = finalize_extraction_run(db_path, run_id)
        typer.echo(_safe_error_message(exc), err=True)
        typer.echo(_summary_line(summary, skipped=skipped))
        raise typer.Exit(2) from None

    loop_finished = False
    for candidate in candidates:
        mark_run_document_running(db_path, run_id, candidate.doc_id)
        try:
            trace_id = _extract_one(
                db_path=db_path,
                doc_id=candidate.doc_id,
                provider=provider,
                run_id=run_id,
                visual_provider=visual_provider,
            )
        except (ExtractionPipelineError, ExtractionProviderError) as exc:
            mark_run_document_failed(
                db_path,
                run_id,
                candidate.doc_id,
                reason_code=_stable_reason_code(exc),
            )
            typer.echo(_safe_error_message(exc, doc_id=candidate.doc_id), err=True)
            continue
        mark_run_document_completed(db_path, run_id, candidate.doc_id, trace_id=trace_id)
    loop_finished = True

    if not loop_finished:  # pragma: no cover - BaseException propagates before this branch.
        return
    summary = finalize_extraction_run(db_path, run_id)
    typer.echo(_summary_line(summary, skipped=skipped))
    if summary.status.value != "completed":
        raise typer.Exit(1)


def _invoke_coordinator_safely(**kwargs) -> None:
    try:
        _coordinate_extraction_run(**kwargs)
    except ExtractionRunConflictError as exc:
        typer.echo(_safe_error_message(exc), err=True)
        raise typer.Exit(2) from None
    except ExtractionRunStateError as exc:
        typer.echo(_safe_error_message(exc, doc_id=exc.doc_id), err=True)
        exit_code = 1 if exc.reason_code == "document_not_found" else 2
        raise typer.Exit(exit_code) from None
    except SafeCliError as exc:
        typer.echo(_safe_error_message(exc), err=True)
        raise typer.Exit(exc.exit_code) from None


@app.command("extract")
def extract_command(
    doc_id: Annotated[str, typer.Option("--doc-id", help="Document ID to extract.")],
    db_path: Annotated[str, typer.Option("--db-path", help="SQLite compliance database path.")],
    provider_name: Annotated[str, typer.Option("--provider", help="Extraction provider to use.")] = "gemini",
    run_id: Annotated[str | None, typer.Option("--run-id", help="Optional extraction run ID to persist.")] = None,
    corpus_version: Annotated[
        str,
        typer.Option("--corpus-version", help="Bounded corpus identity used for reproducible run manifests."),
    ] = "unversioned",
    visual_fallback: Annotated[
        bool,
        typer.Option(
            "--visual-fallback",
            help="Opt in to targeted Gemini visual fallback for missing or suspicious fields.",
        ),
    ] = False,
) -> None:
    """Extract and persist one ingested document's six SDF fields."""

    effective_run_id = run_id or f"sdf-{uuid4().hex}"
    try:
        safe_provider_name = _normalized_provider_name(provider_name)
        safe_corpus_version = _validated_corpus_version(corpus_version)
        typer.echo(
            f"Starting extraction doc_id={doc_id} provider={safe_provider_name} "
            f"trace_status={_trace_status()} run_id={effective_run_id} "
            f"corpus_version={safe_corpus_version} "
            f"visual_fallback={str(visual_fallback).lower()}"
        )
        _invoke_coordinator_safely(
            db_path=db_path,
            doc_ids=(doc_id,),
            provider_name=safe_provider_name,
            run_id=effective_run_id,
            corpus_version=safe_corpus_version,
            visual_fallback=visual_fallback,
        )
    except SafeCliError as exc:
        typer.echo(_safe_error_message(exc, doc_id=doc_id), err=True)
        raise typer.Exit(exc.exit_code) from None


@app.command("extract-all")
def extract_all_command(
    db_path: Annotated[str, typer.Option("--db-path", help="SQLite compliance database path.")],
    provider_name: Annotated[str, typer.Option("--provider", help="Extraction provider to use.")] = "gemini",
    run_id: Annotated[str | None, typer.Option("--run-id", help="Optional shared extraction run ID to persist.")] = None,
    corpus_version: Annotated[
        str,
        typer.Option("--corpus-version", help="Bounded corpus identity used for reproducible run manifests."),
    ] = "unversioned",
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

    effective_run_id = run_id or f"sdf-{uuid4().hex}"
    try:
        safe_provider_name = _normalized_provider_name(provider_name)
        safe_corpus_version = _validated_corpus_version(corpus_version)
        typer.echo(
            f"Starting batch extraction provider={safe_provider_name} trace_status={_trace_status()} "
            f"docs={len(documents)} run_id={effective_run_id} "
            f"corpus_version={safe_corpus_version} "
            f"visual_fallback={str(visual_fallback).lower()}"
        )
        _invoke_coordinator_safely(
            db_path=db_path,
            doc_ids=tuple(str(document["doc_id"]) for document in documents),
            provider_name=safe_provider_name,
            run_id=effective_run_id,
            corpus_version=safe_corpus_version,
            visual_fallback=visual_fallback,
        )
    except SafeCliError as exc:
        typer.echo(_safe_error_message(exc), err=True)
        raise typer.Exit(exc.exit_code) from None


if __name__ == "__main__":  # pragma: no cover - exercised by Typer runner/tests.
    app()
