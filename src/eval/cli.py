"""Command-line entrypoint for the provider-free retrieval eval harness.

This CLI is offline-safe to import: it imports neither ragas nor any LLM SDK at
module load. The live RAGAS path (``--with-ragas``) lazily resolves its judge and
embeddings only inside the runner. Output is bounded to compact status fields
(no query text, answers, snippets, or secrets) per the trace/echo privacy
convention used by the retrieval CLI.
"""
from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from src.eval.retrieval_eval_runner import run_retrieval_eval

app = typer.Typer(help="Run and inspect the provider-free retrieval eval harness.", no_args_is_help=True)


@app.callback()
def _main() -> None:
    """Provider-free retrieval eval harness commands."""


@app.command("run")
def run_command(
    db_path: Annotated[str, typer.Option("--db-path", help="SQLite compliance database path.")],
    with_ragas: Annotated[
        bool,
        typer.Option("--with-ragas", help="Compute real Gemini-judged RAGAS faithfulness + answer relevancy."),
    ] = False,
    include_latency_cost: Annotated[
        bool,
        typer.Option("--include-latency-cost", help="Aggregate optional latency/cost/token metrics."),
    ] = False,
    k: Annotated[
        list[int] | None,
        typer.Option("--k", help="Recall/citation cutoffs (repeatable). Defaults to 5 and 10."),
    ] = None,
) -> None:
    """Run retrieval evaluation, optionally producing real RAGAS quality scores."""

    path = Path(db_path)
    if not path.exists() or not path.is_file():
        typer.echo("status=error run_id=none with_ragas=false reason=db_missing", err=True)
        raise typer.Exit(2)

    k_values = tuple(k) if k else (5, 10)
    try:
        run_id = run_retrieval_eval(
            db_path,
            k_values=k_values,
            include_latency_cost=include_latency_cost,
            include_ragas=with_ragas,
        )
    except Exception as exc:  # noqa: BLE001 - surface a bounded reason, never a raw traceback.
        typer.echo(
            f"status=error run_id=none with_ragas={str(with_ragas).lower()} reason={exc.__class__.__name__}",
            err=True,
        )
        raise typer.Exit(1) from exc

    typer.echo(f"status=complete run_id={run_id} with_ragas={str(with_ragas).lower()}")


if __name__ == "__main__":  # pragma: no cover - exercised by Typer runner/tests.
    app()
