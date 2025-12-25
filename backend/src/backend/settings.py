"""
Application settings using pydantic-settings.

Settings are loaded from environment variables and .env file.
"""

import os
from functools import lru_cache

from pydantic import Field, PostgresDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def set_api_keys_to_env(self) -> "Settings":
        """
        Set API keys to os.environ so that pydantic-ai can read them.

        pydantic-ai's providers read API keys directly from os.environ,
        not from our settings object. This validator ensures the keys
        loaded from .env are available in the environment.
        """
        if self.openai_api_key and "OPENAI_API_KEY" not in os.environ:
            os.environ["OPENAI_API_KEY"] = self.openai_api_key
        if self.gemini_api_key and "GEMINI_API_KEY" not in os.environ:
            os.environ["GEMINI_API_KEY"] = self.gemini_api_key
        return self

    # LLM Configuration
    llm_model: str = Field(
        default="openai:gpt-5-mini",
        description="LLM model to use (e.g., 'openai:gpt-5-mini', 'google-gla:gemini-2.5-flash')",
    )

    # API Keys (optional - pydantic-ai reads these directly from env)
    openai_api_key: str | None = Field(
        default=None,
        description="OpenAI API key",
    )
    gemini_api_key: str | None = Field(
        default=None,
        description="Google Gemini API key",
    )

    # Database Configuration
    database_url: PostgresDsn = Field(
        default="postgresql://postgres:postgres@localhost:54320/pydantic_ai_sql_gen",
        description="PostgreSQL database URL",
    )

    # CORS Configuration
    cors_origins: list[str] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"],
        description="Allowed CORS origins",
    )

    # Data Store Configuration
    csv_data_ttl_minutes: int = Field(
        default=30,
        description="TTL in minutes for CSV export data",
    )

    # SQL Safety Configuration
    sql_max_limit: int = Field(
        default=1000,
        description="Maximum LIMIT value for SQL queries",
    )

    @property
    def database_server_dsn(self) -> str:
        """Get the database server DSN (without database name)."""
        url = str(self.database_url)
        # Remove database name from URL
        if "/" in url.rsplit("@", 1)[-1]:
            return url.rsplit("/", 1)[0]
        return url

    @property
    def database_name(self) -> str:
        """Get the database name from the URL."""
        url = str(self.database_url)
        if "/" in url.rsplit("@", 1)[-1]:
            db_part = url.rsplit("/", 1)[1]
            return db_part.split("?")[0]  # Remove query params
        return "pydantic_ai_sql_gen"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
