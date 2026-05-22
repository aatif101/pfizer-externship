"""Presentation-level tests for the Compliance tab (S05 polish).

These tests focus on stable empty-state/header copy rather than DB plumbing.
"""

from __future__ import annotations

from src.dashboard.compliance import render_compliance_tab


def test_compliance_tab_empty_state_uses_shared_copy(monkeypatch) -> None:
    """Assert empty-state guidance stays stable and actionable."""

    from tests.test_compliance_dashboard import FakeStreamlit

    fake_st = FakeStreamlit()
    fake_st.headers = []

    def header(message: str) -> None:
        fake_st.headers.append(message)

    fake_st.header = header  # type: ignore[attr-defined]

    monkeypatch.setattr("src.dashboard.compliance.st", fake_st)
    monkeypatch.setattr("src.dashboard.ui.st", fake_st)
    monkeypatch.setattr("src.dashboard.compliance.load_compliance_rows", lambda db_path: [])

    render_compliance_tab("empty-dashboard.db")

    assert fake_st.headers == ["Compliance"]
    assert fake_st.info_messages == ["No compliance records are available yet."]
    assert fake_st.caption_messages == [
        "Review extracted compliance status and risk signals with source evidence.",
        "Ingest documents and run extraction to populate this SQLite-backed dashboard. "
        "Looking for persisted records in `empty-dashboard.db`.",
    ]
