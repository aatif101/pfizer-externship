"""Grounded RAG answer service package."""

from src.rag.models import (
    AnswerCitation,
    AnswerDiagnostics,
    AnswerReasonCode,
    AnswerResult,
    AnswerStatus,
)
from src.rag.providers import (
    AnswerConfigurationError,
    AnswerProvider,
    AnswerProviderError,
    AnswerProviderRequest,
    AnswerProviderResult,
    AnswerValidationError,
    GeminiAnswerProvider,
    GeminiAnswerProviderDiagnostics,
)
from src.rag.service import answer_question

__all__ = [
    "AnswerCitation",
    "AnswerConfigurationError",
    "AnswerDiagnostics",
    "AnswerProvider",
    "AnswerProviderError",
    "AnswerProviderRequest",
    "AnswerProviderResult",
    "AnswerReasonCode",
    "AnswerResult",
    "AnswerStatus",
    "AnswerValidationError",
    "GeminiAnswerProvider",
    "GeminiAnswerProviderDiagnostics",
    "answer_question",
]
