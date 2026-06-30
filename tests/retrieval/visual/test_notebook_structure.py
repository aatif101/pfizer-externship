"""Offline structural validation for the Colab visual-retrieval notebook.

These tests validate AUTHORING ONLY. They parse
``notebooks/visual_retrieval_colab.ipynb`` as JSON (a ``.ipynb`` is a JSON
document), assert the nbformat-v4 envelope, grep the concatenated cell source for
the required pins, tokens, and shared-builder imports, and assert that NO
secret-shaped strings appear. When ``nbformat`` is installed they additionally run
``nbformat.validate`` for a stricter check, but the suite stays green offline
WITHOUT it (no skip — the structural guard must actually execute in CI).

They NEVER execute the notebook and assert NO retrieval-quality number — the real
VISUAL-01/VISUAL-02 numbers come only from the manual Colab L4 run
(metric-integrity rule, 05-CONTEXT.md §"No fabrication"; threat T-05-19).
"""
from __future__ import annotations

import importlib.util
import ast
import json
import re
from pathlib import Path

NOTEBOOK_PATH = Path("notebooks/visual_retrieval_colab.ipynb")


def _load_notebook() -> dict:
    """Parse the .ipynb as JSON (stdlib only — no nbformat install required)."""
    return json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))


def _cell_source(cell: dict) -> str:
    source = cell.get("source", "")
    return "".join(source) if isinstance(source, list) else str(source)


def _concatenated_source(nb: dict) -> str:
    return "\n".join(_cell_source(cell) for cell in nb.get("cells", []))


def test_notebook_exists() -> None:
    """The committed notebook artifact exists at the expected path."""
    assert NOTEBOOK_PATH.is_file(), f"missing notebook: {NOTEBOOK_PATH}"


def test_notebook_is_valid_nbformat_v4() -> None:
    """The notebook is a valid nbformat-v4 envelope (JSON + required keys).

    Uses stdlib JSON so this runs offline without nbformat; when nbformat IS
    installed it additionally runs the official validator for a stricter check.
    """
    nb = _load_notebook()
    assert nb.get("nbformat") == 4
    assert "cells" in nb and isinstance(nb["cells"], list)
    # Every cell carries the required nbformat keys.
    for cell in nb["cells"]:
        assert cell.get("cell_type") in {"markdown", "code"}
        assert "source" in cell
    # A real deliverable has multiple cells (install, build, eval, proof...).
    assert len(nb["cells"]) >= 8

    if importlib.util.find_spec("nbformat") is not None:
        import nbformat  # noqa: PLC0415

        nbformat.validate(nbformat.read(str(NOTEBOOK_PATH), as_version=4))


def test_install_cell_pins_the_primary_fixed_stack() -> None:
    """An install cell pins the primary pre-Transformers-5 ColQwen2.5 stack."""
    source = _concatenated_source(_load_notebook())
    assert "colpali-engine==0.3.9" in source
    assert "transformers>=4.50,<4.51" in source
    assert "torch==2.6.0" in source
    assert "torchvision==0.21.0" in source
    assert "peft>=0.14,<0.15" in source
    assert "accelerate>=0.34,<1.4" in source
    assert "qdrant-client>=1.17,<2.0" in source
    # Fallback Option A is documented but not the default install path.
    assert "c23838d920a7c426ee297034211cff2f55da65dc" in source


def test_notebook_loads_the_locked_model() -> None:
    """The notebook references the locked ColQwen2.5 checkpoint + the load seam."""
    source = _concatenated_source(_load_notebook())
    assert "vidore/colqwen2.5-v0.2" in source
    assert "load_colqwen" in source


def test_notebook_has_load_report_acceptance_gate() -> None:
    """The notebook fails loudly on missing/unexpected ColQwen base or LoRA keys."""
    source = _concatenated_source(_load_notebook())
    assert "return_load_report=True" in source
    assert "LOAD_REPORT" in source
    assert "assert_colqwen_load_report_clean" in source
    assert "STRICT_ZERO_LOAD_MISSING" in source
    for token in ("missing_count", "unexpected_count", "mismatched_count"):
        assert token in source


def test_notebook_imports_shared_pure_builders() -> None:
    """The notebook imports the SAME pure builders the offline suite covers.

    This is the key_link guard: the notebook reuses src.retrieval.visual.* rather
    than re-implementing collection/pooling/querier/fusion/run plumbing.
    """
    source = _concatenated_source(_load_notebook())
    assert "src.retrieval.visual" in source
    for token in (
        "build_vectors_config",
        "collection_name",
        "build_upsert_point",
        "build_query_payload",
        "map_response_to_candidates",
        "rrf_fuse",
        "assert_fused_recall_not_below_text",
        "blob_to_image",
        "build_visual_index_run",
        "pooled_vectors_for_image",
    ):
        assert token in source, f"notebook must call shared builder {token!r}"


def test_notebook_embeds_from_image_blob_not_source_pdfs() -> None:
    """The notebook embeds pages from pages.image_blob (reproducible), not source PDFs."""
    source = _concatenated_source(_load_notebook())
    assert "image_blob" in source
    # The gitignored source-PDF directory must NOT be the embedding source.
    assert "Downloads" not in source


def test_notebook_proves_rq_ex3_pages() -> None:
    """The notebook has an explicit Example-3 proof for the rq_ex3 image-only pages."""
    source = _concatenated_source(_load_notebook())
    assert "rq_ex3" in source
    # The motivating image-only doc id appears in the proof narrative.
    assert "5543408c4dacc48b" in source


def test_notebook_runs_text_only_vs_visual_fused_eval() -> None:
    """The notebook evaluates BOTH modes with the unchanged metric functions."""
    source = _concatenated_source(_load_notebook())
    assert "compute_retrieval_recall_at_k" in source
    assert "compute_page_level_citation_accuracy" in source
    assert "text-only" in source and "visual-fused" in source
    assert "text_weight=4.0" in source
    assert "visual_weight=1.0" in source
    assert "rescue_weight=3.5" in source
    assert "Acceptance passed: fused recall@5/@10 is not below text-only" in source


def test_notebook_records_full_rank_report_and_rq_ex3_acceptance() -> None:
    """The notebook exports the diagnostic artifact and enforces the rq_ex3 gate."""
    source = _concatenated_source(_load_notebook())
    assert "VISUAL_SEARCH_LIMIT = len(pages)" in source
    assert "visual_hits_by_query" in source
    assert "per_query_target_ranks" in source
    assert "top10_visual_hits" in source
    assert "visual_retrieval_run_report.json" in source
    assert "visual_retrieval_run_report.md" in source
    assert "RQ_EX3_VISUAL_RANK_THRESHOLD = 10" in source
    assert "rq_ex3_rank_failures" in source


def test_notebook_carries_no_secrets() -> None:
    """The committed notebook contains NO secret-shaped strings (threat T-05-16).

    Greps the concatenated source for API-key / secret patterns; all must be
    ABSENT. Retrieval is provider-free, so no key is ever needed.
    """
    source = _concatenated_source(_load_notebook())
    secret_patterns = [
        r"sk-[A-Za-z0-9]{16,}",          # OpenAI/Anthropic-style keys
        r"AIza[0-9A-Za-z_\-]{20,}",      # Google API keys
        r"_SECRET_KEY\s*=\s*['\"][^'\"]+['\"]",  # assigned secret literal
        r"LANGFUSE_SECRET_KEY\s*=\s*['\"][^'\"]+['\"]",
    ]
    for pattern in secret_patterns:
        match = re.search(pattern, source)
        assert match is None, f"notebook leaks a secret-shaped string: {pattern!r}"


def test_notebook_cell_types_are_consistent() -> None:
    """Guard against scrambled cell types / leftover duplicate cells.

    A prior round of in-place cell edits swapped markdown/code types and left
    stale duplicate code cells (the old ``colpali_engine.__version__`` print that
    raises AttributeError). This test makes that class of corruption fail loudly
    instead of slipping through the grep-only checks above.
    """
    nb = _load_notebook()
    for cell in nb["cells"]:
        body = _cell_source(cell).lstrip()
        if cell.get("cell_type") == "markdown":
            assert not body.startswith(("!pip", "import ", "from ")), (
                f"markdown cell contains code: {body[:60]!r}"
            )
        if cell.get("cell_type") == "code":
            assert not body.startswith("## "), (
                f"code cell contains a markdown heading: {body[:60]!r}"
            )
    # The pip install must live in a CODE cell (else it never runs).
    install_cells = [c for c in nb["cells"] if "!pip install" in _cell_source(c)]
    assert install_cells, "no install cell found"
    assert all(c.get("cell_type") == "code" for c in install_cells)
    # colpali_engine exposes no __version__ — that stale pattern must be gone.
    assert "colpali_engine.__version__" not in _concatenated_source(nb)


def test_notebook_code_cells_parse_as_python_after_shell_lines_removed() -> None:
    """Catch broken code-cell strings that grep tests cannot see.

    Colab allows ``!pip`` shell escapes, so those lines are replaced with
    ``pass`` before parsing. The rest of each code cell must be valid Python.
    """
    nb = _load_notebook()
    for cell in nb["cells"]:
        if cell.get("cell_type") != "code":
            continue
        source = _cell_source(cell)
        parseable_lines = [
            "pass" if line.lstrip().startswith(("!", "%")) else line
            for line in source.splitlines()
        ]
        try:
            ast.parse("\n".join(parseable_lines))
        except SyntaxError as exc:  # pragma: no cover - assertion path
            raise AssertionError(f"code cell {cell.get('id')} is not parseable: {exc}") from exc
