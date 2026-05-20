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

    max_pdf_mb: int = Field(default=100, description="Max PDF file size in MB before rejection")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached Settings instance. Call once; reuse everywhere."""
    return Settings()