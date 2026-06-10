"""Presentation-level tests for the Chat tab (S05 polish).

We validate tab header/intro copy stays stable while preserving provider seams.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.dashboard.chat import render_chat_tab


class FakeContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeStreamlit:
    def __init__(self) -> None:
        self.session_state: dict[str, Any] = {}
        self.headers: list[str] = []
        self.captions: list[str] = []
        self.chat_inputs: list[str] = []

    def header(self, value: str) -> None:
        self.headers.append(value)

    def caption(self, value: str) -> None:
        self.captions.append(value)

    def chat_message(self, role: str) -> FakeContext:
        return FakeContext()

    def markdown(self, message: str) -> None:  # pragma: no cover - content not relevant here
        pass

    def expander(self, label: str, *, expanded: bool = False) -> FakeContext:  # pragma: no cover
        return FakeContext()

    def chat_input(self, placeholder: str):
        self.chat_inputs.append(placeholder)
        return None


def test_chat_tab_renders_consistent_header_and_tips(monkeypatch, tmp_path: Path) -> None:
    db_path = str(tmp_path / "chat.db")
    fake_st = FakeStreamlit()
    monkeypatch.setattr("src.dashboard.chat.st", fake_st)
    monkeypatch.setattr("src.dashboard.ui.st", fake_st)

    render_chat_tab(db_path, provider_factory=lambda: object(), answer_fn=lambda *_args, **_kwargs: None)

    assert fake_st.headers == ["Chat"]
    assert any("Answers cite source pages" in caption for caption in fake_st.captions)
    assert any(caption.startswith("Tips:") for caption in fake_st.captions)
    assert fake_st.chat_inputs == ["Ask about supplier documents"]
