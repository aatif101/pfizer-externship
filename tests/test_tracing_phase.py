"""Offline tests for Phase 6 tracing primitives (OBS-01).

Covers: Phase 6 Settings, phase-tagged ``trace_session`` (Langfuse v3
``propagate_attributes``), automatic phase tags on every ``safe_update_current_trace``,
the LangGraph CallbackHandler factory, and the no-raise flush helper.

All tests are hermetic: Settings are built with ``_env_file=None`` and Langfuse is
never contacted (seams are monkeypatched).
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest
from pydantic import ValidationError

import src.tracing as tracing
from src.config import Settings, get_settings
from tests.test_tracing import _FORBIDDEN_TRACE_KEYS, _FakeLangfuseContext

_ENV_KEYS = (
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_ENABLED",
    "LANGFUSE_HOST",
    "ANTHROPIC_API_KEY",
    "CRITIC_PROVIDER",
    "CRITIC_MODEL",
    "CRITIC_MIN_FAITHFULNESS",
    "RAG_PIPELINE",
    "PIPELINE_PHASE",
)


@pytest.fixture(autouse=True)
def _clean_settings(monkeypatch: pytest.MonkeyPatch) -> Any:
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _use_settings(monkeypatch: pytest.MonkeyPatch, **overrides: Any) -> Settings:
    settings = Settings(_env_file=None, **overrides)
    monkeypatch.setattr(tracing, "get_settings", lambda: settings)
    return settings


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def test_settings_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.rag_pipeline == "agentic"
    assert settings.pipeline_phase == "phase2"
    assert settings.critic_provider == "anthropic"
    assert settings.critic_model == "claude-sonnet-4-6"
    assert settings.critic_min_faithfulness == 0.8
    assert settings.anthropic_api_key == ""

    with pytest.raises(ValidationError):
        Settings(_env_file=None, critic_min_faithfulness=1.5)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, critic_min_faithfulness=-0.1)


def test_phase_tags_mapping() -> None:
    assert tracing.PHASE_TAGS == {"linear": "phase1", "agentic": "phase2"}


# ---------------------------------------------------------------------------
# trace_session
# ---------------------------------------------------------------------------


def test_trace_session_noop_without_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_settings(monkeypatch, langfuse_public_key="", langfuse_secret_key="")
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(tracing, "_propagate_attributes_factory", lambda **kw: calls.append(kw))

    assert tracing.current_phase() is None
    with tracing.trace_session(phase="phase2"):
        assert tracing.current_phase() == "phase2"
    assert tracing.current_phase() is None
    assert calls == []  # no Langfuse keys -> propagate never built


def test_trace_session_empty_tags_and_no_session_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_settings(monkeypatch, langfuse_enabled=False)
    entered = False
    with tracing.trace_session(phase="phase1", session_id=None, tags=(), metadata=None):
        entered = True
        assert tracing.current_phase() == "phase1"
    assert entered is True
    assert tracing.current_phase() is None


def test_trace_session_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tracing, "_ensure_langfuse_initialized", lambda: True)

    def _exploding_factory(**_: Any) -> Any:
        raise RuntimeError("propagate backend unavailable")

    monkeypatch.setattr(tracing, "_propagate_attributes_factory", _exploding_factory)
    ran = False
    with tracing.trace_session(phase="phase2", session_id="s-1", tags=("chat",)):
        ran = True
        assert tracing.current_phase() == "phase2"
    assert ran is True
    assert tracing.current_phase() is None


def test_trace_session_enter_failure_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tracing, "_ensure_langfuse_initialized", lambda: True)

    class _BadCtx:
        def __enter__(self) -> Any:
            raise RuntimeError("enter failed")

        def __exit__(self, *exc: Any) -> bool:
            return False

    monkeypatch.setattr(tracing, "_propagate_attributes_factory", lambda **_: _BadCtx())
    ran = False
    with tracing.trace_session(phase="phase2"):
        ran = True
    assert ran is True
    assert tracing.current_phase() is None


def test_trace_session_body_exceptions_propagate_and_reset_phase(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_settings(monkeypatch, langfuse_enabled=False)
    with pytest.raises(ValueError, match="body error"):
        with tracing.trace_session(phase="phase2"):
            raise ValueError("body error")
    assert tracing.current_phase() is None


def test_trace_session_uses_propagate_attributes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tracing, "_ensure_langfuse_initialized", lambda: True)
    recorded: list[dict[str, Any]] = []
    state = {"entered": False, "exited": False}

    @contextmanager
    def _recording_factory(**kwargs: Any) -> Any:
        recorded.append(kwargs)
        state["entered"] = True
        try:
            yield
        finally:
            state["exited"] = True

    monkeypatch.setattr(tracing, "_propagate_attributes_factory", _recording_factory)

    with tracing.trace_session(
        phase="phase2",
        session_id="s-1",
        tags=("chat", "phase2"),
        metadata={
            "pipeline": "agentic",
            "entry_point": "chat",
            "command": 7,
            "question": "What is the expiry date of Acme?",
            "api_key": "sk-SHOULD_NOT_APPEAR",
        },
    ):
        assert state["entered"] is True
    assert state["exited"] is True

    assert len(recorded) == 1
    kwargs = recorded[0]
    assert kwargs["tags"] == ["phase2", "chat"]
    assert kwargs["session_id"] == "s-1"
    assert kwargs["metadata"] == {
        "phase": "phase2",
        "pipeline": "agentic",
        "entry_point": "chat",
        "command": "7",
    }
    assert all(isinstance(v, str) for v in kwargs["metadata"].values())
    assert "question" not in kwargs["metadata"]
    assert "SHOULD_NOT_APPEAR" not in repr(kwargs)


def test_trace_session_drops_unsafe_tags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tracing, "_ensure_langfuse_initialized", lambda: True)
    recorded: list[dict[str, Any]] = []

    @contextmanager
    def _recording_factory(**kwargs: Any) -> Any:
        recorded.append(kwargs)
        yield

    monkeypatch.setattr(tracing, "_propagate_attributes_factory", _recording_factory)
    with tracing.trace_session(phase="phase1", tags=("review", 5, "token=abc", "review", None)):  # type: ignore[arg-type]
        pass
    assert recorded[0]["tags"] == ["phase1", "review"]


def test_ordered_unique_tags_is_deterministic() -> None:
    assert tracing._ordered_unique_tags(["phase2", "rag", "phase2", "answer", "rag"]) == ["phase2", "rag", "answer"]
    assert tracing._ordered_unique_tags([]) == []


# ---------------------------------------------------------------------------
# Automatic phase tag on safe_update_current_trace
# ---------------------------------------------------------------------------


def test_phase_tag_on_all_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_settings(monkeypatch, langfuse_enabled=False)
    fake = _FakeLangfuseContext()

    # Outside a session: legacy behavior, exactly the module tags.
    assert tracing.safe_update_current_trace(tags=["retrieval", "evidence"], context=fake) is True
    assert fake.updates[-1]["tags"] == ["retrieval", "evidence"]
    # Outside a session with nothing to send: still a no-op.
    assert tracing.safe_update_current_trace(context=fake) is False

    with tracing.trace_session(phase="phase2"):
        assert tracing.safe_update_current_trace(tags=["retrieval", "evidence"], context=fake) is True
        assert fake.updates[-1]["tags"] == ["phase2", "retrieval", "evidence"]

        # Adjacency: module tags already containing the phase -> no duplicate.
        assert tracing.safe_update_current_trace(tags=["phase2", "rag"], context=fake) is True
        assert fake.updates[-1]["tags"] == ["phase2", "rag"]

        assert tracing.safe_update_current_trace(tags=["rag", "phase2"], context=fake) is True
        assert fake.updates[-1]["tags"] == ["phase2", "rag"]

        # Empty input: active phase alone produces an update with exactly [phase].
        assert tracing.safe_update_current_trace(context=fake) is True
        assert fake.updates[-1] == {"tags": ["phase2"]}

        # Metadata still allowlisted alongside the phase tag.
        assert tracing.safe_update_current_trace(
            tags=["extraction"],
            metadata={"boundary": "extract", "page_text": "raw text"},
            allowed_metadata_keys=frozenset({"boundary"}),
            context=fake,
        ) is True
        assert fake.updates[-1] == {"tags": ["phase2", "extraction"], "metadata": {"boundary": "extract"}}

    assert tracing.safe_update_current_trace(tags=["ingestion"], context=fake) is True
    assert fake.updates[-1]["tags"] == ["ingestion"]


def test_nested_trace_sessions_restore_outer_phase(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_settings(monkeypatch, langfuse_enabled=False)
    with tracing.trace_session(phase="phase2"):
        with tracing.trace_session(phase="phase1"):
            assert tracing.current_phase() == "phase1"
        assert tracing.current_phase() == "phase2"
    assert tracing.current_phase() is None


# ---------------------------------------------------------------------------
# CallbackHandler factory
# ---------------------------------------------------------------------------


def test_callback_handler_wiring(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    monkeypatch.setattr(tracing, "_callback_handler_factory", lambda: sentinel)

    _use_settings(monkeypatch, langfuse_enabled=False, langfuse_public_key="pk-lf-x", langfuse_secret_key="sk-lf-y")
    assert tracing.build_callback_handler() is None

    _use_settings(monkeypatch, langfuse_enabled=True, langfuse_public_key="", langfuse_secret_key="")
    assert tracing.build_callback_handler() is None

    monkeypatch.setattr(tracing, "_ensure_langfuse_initialized", lambda: True)
    assert tracing.build_callback_handler() is sentinel

    def _exploding() -> Any:
        raise RuntimeError("langchain-core missing")

    monkeypatch.setattr(tracing, "_callback_handler_factory", _exploding)
    assert tracing.build_callback_handler() is None


# ---------------------------------------------------------------------------
# flush
# ---------------------------------------------------------------------------


def test_flush_traces_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raising_client() -> Any:
        raise RuntimeError("no client")

    monkeypatch.setattr(tracing, "get_client", _raising_client)
    assert tracing.flush_traces() is False

    @dataclass
    class _FlushClient:
        flushed: list[bool] = field(default_factory=list)

        def flush(self) -> None:
            self.flushed.append(True)

    client = _FlushClient()
    monkeypatch.setattr(tracing, "get_client", lambda: client)
    assert tracing.flush_traces() is True
    assert client.flushed == [True]

    monkeypatch.setattr(tracing, "_LANGFUSE_AVAILABLE", False)
    assert tracing.flush_traces() is False


def test_forbidden_keys_fixture_is_shared() -> None:
    assert "question" in _FORBIDDEN_TRACE_KEYS
