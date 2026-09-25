"""Agentic RAG pipeline (Phase 6, RAG-03): bounded LangGraph graph over the
existing retrieval gate and answer-provider seams.

Not imported from ``src.rag`` so the linear path never loads langgraph.
"""
from __future__ import annotations

from src.rag.agentic.graph import answer_question_agentic, build_agentic_graph

__all__ = ["answer_question_agentic", "build_agentic_graph"]
