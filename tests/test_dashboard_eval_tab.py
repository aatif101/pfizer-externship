"""Tests for the Eval dashboard tab adapter/renderer."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.dashboard.eval import load_eval_metrics, load_eval_runs, render_eval_tab
from src.db.schema import init_db
from src.eval.repository import create_eval_run, upsert_eval_metric


def prepare_eval_db(db_path: str) -> None:
    init_db(db_path)


def test_load_eval_runs_returns_empty_for_missing_database(tmp_path: Path) -> None:
    missing_db = tmp_path / "missing-eval.db"
    assert load_eval_runs(str(missing_db)) == []


def test_load_eval_runs_returns_empty_for_missing_table(tmp_db_path: str) -> None:
    conn = sqlite3.connect(tmp_db_path)
    conn.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    assert load_eval_runs(tmp_db_path) == []


def test_render_eval_tab_empty_state_does_not_crash(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr("src.dashboard.eval.st", fake_st)
    monkeypatch.setattr("src.dashboard.eval.render_empty_state", fake_st.render_empty_state)
    monkeypatch.setattr("src.dashboard.eval.render_tab_header", fake_st.render_tab_header)
    monkeypatch.setattr("src.dashboard.eval.load_eval_runs", lambda db_path: [])

    render_eval_tab("empty-eval.db")

    assert fake_st.info_messages == [
        "No evaluation runs yet. Run the evaluation CLI/tests to populate `eval_runs` and `eval_metrics` in the SQLite database."
    ]
    assert fake_st.subheaders[:1] == ["Evaluation"]
    assert fake_st.caption_messages == [
        "This tab is read-only: it surfaces persisted eval run history and metrics without triggering any evaluation computation.",
        "Looking for persisted runs in `empty-eval.db`.",
    ]
    assert fake_st.dataframes == []


def test_render_eval_tab_populated_displays_run_table_and_metrics(monkeypatch, tmp_db_path: str) -> None:
    prepare_eval_db(tmp_db_path)
    create_eval_run(
        tmp_db_path,
        run_id="run-eval-001",
        eval_type="extraction",
        pipeline_label="demo",
        params={"gold_set": "mini"},
    )
    upsert_eval_metric(tmp_db_path, "run-eval-001", "f1", 0.8)
    upsert_eval_metric(tmp_db_path, "run-eval-001", "precision", 0.75)
    upsert_eval_metric(tmp_db_path, "run-eval-001", "query_recall", 1.0, scope_type="query", scope_id="q1")

    # Primary run, compatible filter on, allow-any-type off, compare none.
    fake_st = FakeStreamlit(select_values=["run-eval-001", "(none)"])
    monkeypatch.setattr("src.dashboard.eval.st", fake_st)

    render_eval_tab(tmp_db_path)

    assert fake_st.subheaders[:2] == ["Run history", "Metrics"]
    assert len(fake_st.dataframes) >= 2

    run_table = fake_st.dataframes[0]
    assert run_table[0]["run_id"] == "run-eval-001"

    global_metrics = fake_st.dataframes[1]
    names = {row["metric"] for row in global_metrics}
    assert names == {"f1", "precision"}

    f1_row = next(row for row in global_metrics if row["metric"] == "f1")
    assert f1_row["value"] == "80.0%"
    assert f1_row["compare_value"] == ""
    assert f1_row["delta"] == ""


def test_load_eval_metrics_returns_empty_for_missing_table(tmp_db_path: str) -> None:
    conn = sqlite3.connect(tmp_db_path)
    conn.execute("CREATE TABLE eval_runs (run_id TEXT PRIMARY KEY)")
    conn.commit()
    conn.close()

    assert load_eval_metrics(tmp_db_path, run_id="missing") == []


def test_render_eval_tab_compare_two_runs_shows_deltas(monkeypatch, tmp_db_path: str) -> None:
    prepare_eval_db(tmp_db_path)

    create_eval_run(
        tmp_db_path,
        run_id="run-eval-001",
        eval_type="extraction",
        pipeline_label="demo",
        params={"gold_set": "mini"},
    )
    create_eval_run(
        tmp_db_path,
        run_id="run-eval-002",
        eval_type="extraction",
        pipeline_label="demo",
        params={"gold_set": "mini"},
    )

    upsert_eval_metric(tmp_db_path, "run-eval-001", "f1", 0.8)
    upsert_eval_metric(tmp_db_path, "run-eval-002", "f1", 0.9)
    upsert_eval_metric(tmp_db_path, "run-eval-001", "precision", 0.75)
    upsert_eval_metric(tmp_db_path, "run-eval-002", "precision", 0.70)

    fake_st = FakeStreamlit(
        select_values=["run-eval-001", "run-eval-002"],
        checkbox_values=[True, False, True, False],
    )
    monkeypatch.setattr("src.dashboard.eval.st", fake_st)

    render_eval_tab(tmp_db_path)

    assert "Compare runs" in fake_st.subheaders
    comparison_table = fake_st.dataframes[-1]
    f1_row = next(row for row in comparison_table if row["metric"] == "f1")
    assert f1_row["value_a"] == "80.0%"
    assert f1_row["value_b"] == "90.0%"
    assert f1_row["delta"] == "+10.0%"


def test_render_eval_tab_compare_filters_incompatible_types_by_default(monkeypatch, tmp_db_path: str) -> None:
    prepare_eval_db(tmp_db_path)

    create_eval_run(
        tmp_db_path,
        run_id="run-eval-001",
        eval_type="extraction",
        pipeline_label="demo",
        params={"gold_set": "mini"},
    )
    create_eval_run(
        tmp_db_path,
        run_id="run-eval-002",
        eval_type="retrieval",
        pipeline_label="demo",
        params={"gold_set": "mini"},
    )

    fake_st = FakeStreamlit(select_values=["run-eval-001", "(none)"], checkbox_values=[True, False])
    monkeypatch.setattr("src.dashboard.eval.st", fake_st)

    render_eval_tab(tmp_db_path)

    assert "Compare runs" in fake_st.subheaders
    assert fake_st.dataframes


class FakeStreamlit:
    def __init__(self, *, select_values: list[str] | None = None, checkbox_values: list[bool] | None = None) -> None:
        self.info_messages: list[str] = []
        self.caption_messages: list[str] = []
        self.dataframes: list[list[dict[str, object]]] = []
        self.subheaders: list[str] = []
        self.markdown_messages: list[str] = []
        self.warning_messages: list[str] = []
        self.expanders: list[str] = []
        self.checkbox_labels: list[str] = []
        self._select_values = list(select_values or [])
        self._checkbox_values = list(checkbox_values or [])

    def render_tab_header(self, title: str, caption: str | None = None) -> None:
        self.subheaders.append(title)
        if caption:
            self.caption_messages.append(caption)

    def render_empty_state(self, message: str, *, caption: str | None = None) -> None:
        self.info_messages.append(message)
        if caption:
            self.caption_messages.append(caption)

    def caption(self, message: str) -> None:
        self.caption_messages.append(message)

    def info(self, message: str) -> None:
        self.info_messages.append(message)

    def subheader(self, message: str) -> None:
        self.subheaders.append(message)

    def dataframe(self, rows, *, hide_index: bool, width: str) -> None:
        assert hide_index is True
        assert width == "stretch"
        self.dataframes.append(rows)

    def selectbox(self, label: str, *, options: list[str]) -> str:
        assert options
        if self._select_values:
            return self._select_values.pop(0)
        return options[0]

    def checkbox(self, label: str, *, value: bool = False) -> bool:
        self.checkbox_labels.append(label)
        if self._checkbox_values:
            return self._checkbox_values.pop(0)
        return value

    def markdown(self, message: str) -> None:
        self.markdown_messages.append(message)

    def warning(self, message: str) -> None:
        self.warning_messages.append(message)

    def expander(self, label: str, *, expanded: bool = False):
        self.expanders.append(label)
        return _FakeExpander()


class _FakeExpander:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False
