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


# ---------------------------------------------------------------------------
# Global privacy mask (Task 2)
# ---------------------------------------------------------------------------

_QUESTION = "When does the Acme Pharma GMP certificate expire for lot 42?"
_EVIDENCE = "Acme Pharma GMP certificate valid until 2027-01-31 issued by EMA inspectorate page text"
_DRAFT = "The Acme Pharma GMP certificate expires on 2027-01-31 according to the cited page."
_CONTENT_KEYS = (
    "question",
    "snippet",
    "evidence_text",
    "page_text",
    "draft",
    "critic_feedback",
    "unsupported_claims",
    "field_value",
    "corrected_value",
    "note",
    "verbatim_span",
)


@dataclass(frozen=True)
class _HitLike:
    doc_id: str
    page_num: int
    snippet: str
    evidence_text: str
    score: float


def _all_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, inner in value.items():
            keys.add(key)
            keys |= _all_keys(inner)
    elif isinstance(value, (list, tuple)):
        for inner in value:
            keys |= _all_keys(inner)
    return keys


def test_mask_safe_keys_exclude_content_keys() -> None:
    assert tracing._MASK_SAFE_KEYS.isdisjoint(_CONTENT_KEYS)
    assert tracing._MASK_SAFE_KEYS.isdisjoint(_FORBIDDEN_TRACE_KEYS)


def test_mask_redacts_state() -> None:
    hit = _HitLike(doc_id="doc-1", page_num=3, snippet=_EVIDENCE[:40], evidence_text=_EVIDENCE, score=0.91)
    state = {
        "question": _QUESTION,
        "sub_queries": [_QUESTION, "Acme GMP expiry"],
        "evidence": (hit, hit),
        "draft": _DRAFT,
        "critic_feedback": "Claim about lot 42 unsupported by evidence text",
        "unsupported_claims": ["lot 42"],
        "retrieval_round": 2,
        "critic_score": 0.9,
        "reason_code": "answered",
        "run_id": "r1",
        "api_key": "sk-ant-SHOULD_NOT_APPEAR",
        "page_text": _EVIDENCE,
        "image_blob": b"\x89PNG....",
        "field_value": "2027-01-31",
        "note": "reviewer note",
    }
    masked = tracing.mask_trace_payload(data=state)

    assert masked == {"retrieval_round": 2, "critic_score": 0.9, "reason_code": "answered", "run_id": "r1"}
    keys = _all_keys(masked)
    assert keys.isdisjoint(_FORBIDDEN_TRACE_KEYS)
    assert keys.isdisjoint(_CONTENT_KEYS)
    rendered = repr(masked)
    for leaked in (_QUESTION, _EVIDENCE, _DRAFT, "SHOULD_NOT_APPEAR", "Acme", "lot 42", "PNG"):
        assert leaked not in rendered


def test_mask_nested_callback_handler_payload() -> None:
    payload = {
        "input": {"question": _QUESTION, "retrieval_round": 1, "sub_query_count": 2},
        "output": {"draft": _DRAFT, "critic_verdict": "supported", "citation_count": 2},
        "kwargs": {"question": _QUESTION},
    }
    masked = tracing.mask_trace_payload(data=payload)
    assert masked == {
        "input": {"retrieval_round": 1, "sub_query_count": 2},
        "output": {"critic_verdict": "supported", "citation_count": 2},
    }


def test_mask_primitives_and_empty() -> None:
    assert tracing.mask_trace_payload(data=None) is None
    assert tracing.mask_trace_payload(data={}) == {}
    assert tracing.mask_trace_payload(data="") == ""
    assert tracing.mask_trace_payload(data="doc-abc-0012") == "doc-abc-0012"
    long_text = "x" * 300
    assert tracing.mask_trace_payload(data=long_text) == "[redacted:len=300]"
    assert tracing.mask_trace_payload(data=b"raw image bytes") is None
    assert tracing.mask_trace_payload(data=bytearray(b"raw")) is None
    assert tracing.mask_trace_payload(data="Bearer abc.def") is None
    assert tracing.mask_trace_payload(data="sk-live-abc") is None
    assert tracing.mask_trace_payload(data=7) == 7
    assert tracing.mask_trace_payload(data=0.25) == 0.25
    assert tracing.mask_trace_payload(data=True) is True
    assert tracing.mask_trace_payload(data=float("nan")) is None
    assert tracing.mask_trace_payload(data=object()) is None
    assert tracing.mask_trace_payload(data=_HitLike("d", 1, "s", "e", 0.1)) is None
    assert tracing.mask_trace_payload(data=[]) == []

    rows = [{"doc_id": f"doc-{i}", "snippet": _EVIDENCE} for i in range(50)]
    masked_rows = tracing.mask_trace_payload(data=rows)
    assert isinstance(masked_rows, list)
    assert len(masked_rows) == tracing._TRACE_LIST_MAX_ITEMS
    assert masked_rows[0] == {"doc_id": "doc-0"}
    assert "snippet" not in repr(masked_rows)

    # None results are dropped from sequences.
    assert tracing.mask_trace_payload(data=[b"x", "ok", object()]) == ["ok"]
    # kwargs from the Langfuse MaskFunction protocol are accepted.
    assert tracing.mask_trace_payload(data="ok", extra="ignored") == "ok"


def test_mask_depth_is_capped() -> None:
    deep: Any = {"count": 1}
    for _ in range(10):
        deep = {"input": deep}
    masked = tracing.mask_trace_payload(data=deep)
    rendered = repr(masked)
    assert "count" not in rendered  # beyond depth cap -> dropped


def test_mask_never_raises() -> None:
    class _ExplodingMapping(dict):
        def items(self) -> Any:  # type: ignore[override]
            raise RuntimeError("boom")

    assert tracing.mask_trace_payload(data=_ExplodingMapping(a=1)) is None


def test_mask_wired_into_client(monkeypatch: pytest.MonkeyPatch) -> None:
    constructed: list[dict[str, Any]] = []

    class _RecordingLangfuse:
        def __init__(self, **kwargs: Any) -> None:
            constructed.append(kwargs)

    monkeypatch.setattr(tracing, "_Langfuse", _RecordingLangfuse)
    monkeypatch.setattr(tracing, "_LANGFUSE_AVAILABLE", True)
    _use_settings(
        monkeypatch,
        langfuse_enabled=True,
        langfuse_public_key="pk-lf-test",
        langfuse_secret_key="sk-lf-test",
    )
    assert tracing._ensure_langfuse_initialized() is True
    assert constructed and constructed[-1]["mask"] is tracing.mask_trace_payload


# ---------------------------------------------------------------------------
# Span / generation helpers (Task 2)
# ---------------------------------------------------------------------------


@dataclass
class _FakeSpanContext:
    span_updates: list[dict[str, Any]] = field(default_factory=list)
    generation_updates: list[dict[str, Any]] = field(default_factory=list)
    raise_on_update: bool = False

    def update_current_span(self, **kwargs: Any) -> None:
        if self.raise_on_update:
            raise RuntimeError("span backend down")
        self.span_updates.append(kwargs)

    def update_current_generation(self, **kwargs: Any) -> None:
        if self.raise_on_update:
            raise RuntimeError("generation backend down")
        self.generation_updates.append(kwargs)


def test_safe_update_current_span_allowlist() -> None:
    fake = _FakeSpanContext()
    sent = tracing.safe_update_current_span(
        metadata={
            "retrieval_round": 2,
            "critic_score": 0.85,
            "doc_id": "doc-1",
            "question": _QUESTION,
            "evidence_text": _EVIDENCE,
        },
        allowed_metadata_keys=frozenset({"retrieval_round", "critic_score", "doc_id"}),
        context=fake,
    )
    assert sent is True
    assert fake.span_updates == [{"metadata": {"retrieval_round": 2, "critic_score": 0.85, "doc_id": "doc-1"}}]

    # Nothing safe remains -> no update.
    assert tracing.safe_update_current_span(
        metadata={"question": _QUESTION},
        allowed_metadata_keys=frozenset({"retrieval_round"}),
        context=fake,
    ) is False
    assert tracing.safe_update_current_span(
        metadata=None, allowed_metadata_keys=frozenset({"retrieval_round"}), context=fake
    ) is False
    # Context without the method.
    assert tracing.safe_update_current_span(
        metadata={"retrieval_round": 1}, allowed_metadata_keys=frozenset({"retrieval_round"}), context=object()
    ) is False
    # Context that raises.
    assert tracing.safe_update_current_span(
        metadata={"retrieval_round": 1},
        allowed_metadata_keys=frozenset({"retrieval_round"}),
        context=_FakeSpanContext(raise_on_update=True),
    ) is False


def test_safe_update_current_generation() -> None:
    fake = _FakeSpanContext()
    assert tracing.safe_update_current_generation(
        model="gemini-2.5-flash", input_tokens=10, output_tokens=5, context=fake
    ) is True
    assert fake.generation_updates[-1] == {
        "model": "gemini-2.5-flash",
        "usage_details": {"input": 10, "output": 5},
    }

    assert tracing.safe_update_current_generation(
        model="claude-sonnet-4-6", input_tokens="10", output_tokens=-3, context=fake
    ) is True
    assert fake.generation_updates[-1] == {"model": "claude-sonnet-4-6"}

    assert tracing.safe_update_current_generation(
        model=None, input_tokens=True, output_tokens=4, context=fake
    ) is True
    assert fake.generation_updates[-1] == {"usage_details": {"output": 4}}

    assert tracing.safe_update_current_generation(model=None, context=fake) is False
    assert tracing.safe_update_current_generation(model="m", input_tokens=1, context=object()) is False
    assert tracing.safe_update_current_generation(
        model="m", input_tokens=1, context=_FakeSpanContext(raise_on_update=True)
    ) is False
    assert tracing.safe_update_current_generation(model="sk-ant-secret", context=fake) is False
