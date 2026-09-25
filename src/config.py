"""Project-wide configuration loaded from environment variables / .env file."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    db_path: str = Field(default="compliance.db", description="SQLite database file path")
    hf_home: str = Field(default="~/.cache/huggingface", description="HuggingFace model cache dir")

    langfuse_public_key: str = Field(default="", description="Langfuse public API key")
    langfuse_secret_key: str = Field(default="", description="Langfuse secret API key")
    langfuse_host: str = Field(default="https://cloud.langfuse.com", description="Langfuse host URL")
    langfuse_enabled: bool = Field(default=True, description="Enable/disable Langfuse tracing")

    gemini_api_key: str = Field(default="", description="Gemini API key for live extraction and answer providers")
    gemini_model: str = Field(default="gemini-2.5-flash", description="Gemini model for live SDF extraction and answers")
    extraction_low_confidence_threshold: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="Confidence below which extracted fields require human review",
    )

    anthropic_api_key: str = Field(default="", description="Anthropic API key for the Claude faithfulness critic")
    critic_provider: str = Field(
        default="anthropic",
        description=(
            "'anthropic' (default) or 'gemini'. 'gemini' is an explicit opt-in only; there is NO "
            "automatic fallback. With no Anthropic key the agentic critic abstains (fail closed, D-02)."
        ),
    )
    critic_model: str = Field(default="claude-sonnet-4-6", description="Model id for the faithfulness critic")
    critic_min_faithfulness: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Minimum critic faithfulness score (0..1) for a draft answer to be accepted",
    )
    rag_pipeline: str = Field(
        default="agentic",
        description=(
            "Chat tab default pipeline: 'agentic' (phase2, LangGraph) or 'linear' (phase1 baseline). "
            "The eval harness stays linear unless explicitly told otherwise (D-03)."
        ),
    )
    pipeline_phase: str = Field(
        default="phase2",
        description="Phase tag for non-RAG entry points (extraction/retrieval/ingestion CLIs, review).",
    )

    max_pdf_mb: int = Field(default=100, description="Max PDF file size in MB before rejection")

    retrieval_mode: str = Field(
        default="text-only",
        description=(
            "Retrieval mode: 'text-only' (Phase 1 SQLite-FTS baseline) or "
            "'visual-fused' (ColQwen2.5 visual tier fused with text via RRF). "
            "Default 'text-only' keeps existing behavior; 'visual-fused' is the "
            "Phase 7 benchmark mode and requires a built sdf_page_images index + GPU."
        ),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached Settings instance. Call once; reuse everywhere."""
    return Settings()