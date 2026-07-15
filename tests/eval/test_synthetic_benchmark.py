"""Freeze and tamper-detection tests for the public synthetic benchmark."""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest


pytestmark = pytest.mark.phase3_required

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "benchmarks" / "sdf-synthetic-v1"
GENERATOR = BENCHMARK / "generate.py"


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sdf_synthetic_v1_generate", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _copy_benchmark(tmp_path: Path) -> Path:
    target = tmp_path / "sdf-synthetic-v1"
    shutil.copytree(BENCHMARK, target, ignore=shutil.ignore_patterns("generated", "__pycache__"))
    return target


def _rewrite_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")


def test_exact_frozen_contract_and_referential_integrity() -> None:
    generator = _load_generator()
    summary = generator.validate_dataset(BENCHMARK)
    assert summary == {
        "documents": 84,
        "pages": 252,
        "development_documents": 24,
        "development_queries": 120,
        "holdout_documents": 60,
        "holdout_queries": 300,
        "holdout_answerable": 180,
        "holdout_unanswerable": 120,
        "extraction_holdout_cells": 360,
        "document_types": 6,
        "layout_families": 5,
        "render_modes": 3,
    }


def test_document_first_splits_and_strata_are_disjoint() -> None:
    documents = _jsonl(BENCHMARK / "spec" / "documents.jsonl")
    queries = _jsonl(BENCHMARK / "spec" / "queries.jsonl")
    splits = json.loads((BENCHMARK / "spec" / "splits.json").read_text(encoding="utf-8"))

    dev_docs = set(splits["development"]["document_ids"])
    holdout_docs = set(splits["holdout"]["document_ids"])
    assert len(dev_docs) == 24
    assert len(holdout_docs) == 60
    assert dev_docs.isdisjoint(holdout_docs)
    assert dev_docs | holdout_docs == {row["document_id"] for row in documents}
    assert {row["document_id"] for row in queries if row["split"] == "development"} == dev_docs
    assert {row["document_id"] for row in queries if row["split"] == "holdout"} == holdout_docs
    assert all(len(row["pages"]) == 3 for row in documents)
    assert len({row["document_type"] for row in documents}) == 6
    assert len({row["layout_family"] for row in documents}) == 5
    assert len({row["render_mode"] for row in documents}) == 3
    assert len({row["leakage_key"] for row in documents}) == 84


def test_labels_are_complete_and_review_status_is_honest() -> None:
    documents = _jsonl(BENCHMARK / "spec" / "documents.jsonl")
    queries = _jsonl(BENCHMARK / "spec" / "queries.jsonl")
    facts = _jsonl(BENCHMARK / "spec" / "gold-facts.jsonl")
    cells = _jsonl(BENCHMARK / "spec" / "extraction-gold.jsonl")

    assert {row["annotation_status"] for row in documents + queries + facts + cells} == {"synthetic_authoring"}
    assert all(row["subject_scope"] for row in queries)
    assert all(row["graded_pages"] for row in queries)
    assert all("answerable" in row and "tags" in row for row in queries)
    assert all(row["required_fact_ids"] and not row["abstention_reason"] for row in queries if row["answerable"])
    assert all(not row["required_fact_ids"] and row["abstention_reason"] for row in queries if not row["answerable"])
    assert all(row["evidence_text"] and row["accepted_normalizations"] for row in facts)
    assert len({row["cell_id"] for row in cells}) == 360
    assert {row["split"] for row in cells} == {"extraction_holdout"}


def test_generator_check_is_deterministic_and_does_not_rewrite_tracked_files() -> None:
    before = {
        path.relative_to(BENCHMARK).as_posix(): (path.stat().st_mtime_ns, path.read_bytes())
        for path in BENCHMARK.rglob("*")
        if path.is_file() and "generated" not in path.parts and "__pycache__" not in path.parts
    }
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "sdf-synthetic-v1 verified" in result.stdout
    after = {
        path.relative_to(BENCHMARK).as_posix(): (path.stat().st_mtime_ns, path.read_bytes())
        for path in BENCHMARK.rglob("*")
        if path.is_file() and "generated" not in path.parts and "__pycache__" not in path.parts
    }
    assert after == before


def test_checksum_manifest_detects_one_byte_tampering(tmp_path: Path) -> None:
    generator = _load_generator()
    target = _copy_benchmark(tmp_path)
    documents_path = target / "spec" / "documents.jsonl"
    documents_path.write_bytes(documents_path.read_bytes() + b" ")
    with pytest.raises(generator.BenchmarkValidationError, match="checksum mismatch"):
        generator.validate_dataset(target)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("count", "holdout query count"),
        ("duplicate_id", "duplicate query_id"),
        ("split_overlap", "document split overlap"),
        ("annotation_status", "annotation_status"),
        ("private_content", "forbidden private identifier"),
    ],
)
def test_semantic_tampering_is_rejected(tmp_path: Path, mutation: str, message: str) -> None:
    generator = _load_generator()
    target = _copy_benchmark(tmp_path)

    if mutation in {"count", "duplicate_id"}:
        path = target / "spec" / "queries.jsonl"
        rows = _jsonl(path)
        if mutation == "count":
            rows.pop()
        else:
            rows[1]["query_id"] = rows[0]["query_id"]
        _rewrite_jsonl(path, rows)
    elif mutation == "split_overlap":
        path = target / "spec" / "splits.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["holdout"]["document_ids"].append(payload["development"]["document_ids"][0])
        path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    elif mutation == "annotation_status":
        path = target / "spec" / "gold-facts.jsonl"
        rows = _jsonl(path)
        rows[0]["annotation_status"] = "human_reviewed"
        _rewrite_jsonl(path, rows)
    else:
        path = target / "spec" / "documents.jsonl"
        rows = _jsonl(path)
        rows[0]["supplier_name"] = "Pfizer private source"
        _rewrite_jsonl(path, rows)

    with pytest.raises(generator.BenchmarkValidationError, match=message):
        generator.validate_dataset(target, verify_checksums=False)


def test_license_rubric_and_readme_disclose_scope_and_review_limits() -> None:
    license_text = (BENCHMARK / "LICENSE.md").read_text(encoding="utf-8")
    rubric = (BENCHMARK / "ANNOTATION-RUBRIC.md").read_text(encoding="utf-8")
    readme = (BENCHMARK / "README.md").read_text(encoding="utf-8")
    assert "CC0-1.0" in license_text
    assert "independent" in rubric.casefold() and "adjudicat" in rubric.casefold()
    assert "synthetic_authoring" in rubric
    assert "fictional" in readme.casefold()
    assert "not clinical or regulatory evidence" in readme.casefold()
