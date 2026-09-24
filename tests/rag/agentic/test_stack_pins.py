"""Pin guard for the Phase 6 agentic stack (D-01 / D028).

langgraph>=1.1 requires langchain-core>=1.0, which breaks RAGAS 0.4.3. These
tests fail loudly if a future install drifts off the pinned combination.
"""
from __future__ import annotations

import operator
from importlib.metadata import version
from typing import Annotated

from typing_extensions import TypedDict


def test_langgraph_pinned_to_1_0_1() -> None:
    assert version("langgraph") == "1.0.1", (
        "langgraph must stay ==1.0.1 (D028): every >=1.1 release needs langchain-core>=1.0."
    )


def test_langchain_core_stays_0_3() -> None:
    core_version = version("langchain-core")
    assert core_version.startswith("0.3."), (
        f"langchain-core {core_version!r} is not 0.3.x; RAGAS 0.4.3 needs langchain-core<1."
    )


def test_langfuse_is_v3_with_propagate_attributes() -> None:
    langfuse_version = version("langfuse")
    major, minor = (int(part) for part in langfuse_version.split(".")[:2])
    assert major == 3, f"langfuse {langfuse_version!r} must stay on v3"
    assert minor >= 9, f"langfuse {langfuse_version!r} must be >=3.9 (propagate_attributes)"


def test_ragas_still_imports() -> None:
    import ragas  # noqa: PLC0415,F401


def test_trivial_state_graph_compiles_and_invokes() -> None:
    from langgraph.graph import END, START, StateGraph  # noqa: PLC0415

    class _State(TypedDict, total=False):
        value: int
        steps: Annotated[list[str], operator.add]

    builder = StateGraph(_State)
    builder.add_node("bump", lambda state: {"value": state.get("value", 0) + 1, "steps": ["bump"]})
    builder.add_edge(START, "bump")
    builder.add_edge("bump", END)
    graph = builder.compile()

    final = graph.invoke({"value": 1, "steps": []})

    assert final["value"] == 2
    assert final["steps"] == ["bump"]
