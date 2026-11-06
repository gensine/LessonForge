"""Application configuration loaded from environment variables."""

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# Load .env file from project root
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


class Settings(BaseSettings):
    """Central configuration for the Lesson Creator application."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # LLM settings
    llm_provider: str = "gemini"  # gemini | openai | claude
    llm_api_key: str = ""
    llm_model: str = "gemini-2.0-flash"

    # Web search
    tavily_api_key: str = ""

    # YouTube
    youtube_api_key: str = ""

    # Google Books (optional)
    google_books_api_key: str = ""

    # Database
    database_url: str = "sqlite:///./lesson_creator.db"

    # App
    log_level: str = "INFO"

    # Paths
    base_dir: Path = Path(__file__).resolve().parent.parent
    prompts_dir: Path = Path(__file__).resolve().parent / "prompts"
    exports_dir: Path = Path(__file__).resolve().parent.parent / "exports"
    logs_dir: Path = Path(__file__).resolve().parent.parent / "logs"


settings = Settings()

# Ensure required directories exist
settings.exports_dir.mkdir(parents=True, exist_ok=True)
settings.logs_dir.mkdir(parents=True, exist_ok=True)

