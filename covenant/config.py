"""Global application settings and configuration."""

import os
from typing import Optional
from pathlib import Path
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
DEFAULT_DB_PATH = PROJECT_ROOT / "covenant.db"
SYNTHETIC_DATA_DIR = PROJECT_ROOT / "covenant" / "synthetic_data"


class Settings(BaseModel):
    """Application runtime configuration."""
    app_name: str = "Covenant"
    environment: str = Field(default_factory=lambda: os.getenv("COVENANT_ENV", os.getenv("ENVIRONMENT", "local")).lower())
    database_url: str = Field(default_factory=lambda: f"sqlite:///{DEFAULT_DB_PATH}")
    db_path: Path = DEFAULT_DB_PATH
    ollama_base_url: str = Field(default_factory=lambda: os.getenv("COVENANT_OLLAMA_BASE_URL", "http://127.0.0.1:11434"))
    ollama_model: str = Field(default_factory=lambda: os.getenv("COVENANT_OLLAMA_MODEL", "minimax-m3:cloud"))
    ollama_fallback_model: str = Field(default_factory=lambda: os.getenv("COVENANT_OLLAMA_FALLBACK_MODEL", "glm-5.2:cloud"))
    ollama_secondary_fallback_model: Optional[str] = Field(default_factory=lambda: os.getenv("COVENANT_OLLAMA_SECONDARY_FALLBACK_MODEL"))
    system_user_org: str = "Northstar Studio"
    system_user_name: str = "Alex North"
    system_user_email: str = "alex@northstarstudio.com"
    auto_scan_interval_seconds: int = 300

    # Server & Network Configuration
    host: str = Field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = Field(default_factory=lambda: int(os.getenv("PORT", "8000")))

    # Model Provider Configuration
    model_provider: str = Field(default_factory=lambda: os.getenv("COVENANT_MODEL_PROVIDER", "deterministic").lower())
    bedrock_model_id: Optional[str] = Field(default_factory=lambda: os.getenv("COVENANT_BEDROCK_MODEL_ID"))
    aws_region: str = Field(default_factory=lambda: os.getenv("COVENANT_AWS_REGION") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
    bedrock_temperature: float = Field(default_factory=lambda: float(os.getenv("COVENANT_BEDROCK_TEMPERATURE", "0.1")))
    bedrock_max_tokens: Optional[int] = Field(default_factory=lambda: int(os.getenv("COVENANT_BEDROCK_MAX_TOKENS")) if os.getenv("COVENANT_BEDROCK_MAX_TOKENS") else None)

    # Gemini Model Provider Configuration
    gemini_api_key: Optional[str] = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY"))
    gemini_model: str = Field(default_factory=lambda: os.getenv("COVENANT_GEMINI_MODEL", "gemini-2.5-flash-lite"))
    gemini_temperature: float = Field(default_factory=lambda: float(os.getenv("COVENANT_GEMINI_TEMPERATURE", "0.1")))
    gemini_max_tokens: Optional[int] = Field(default_factory=lambda: int(os.getenv("COVENANT_GEMINI_MAX_TOKENS")) if os.getenv("COVENANT_GEMINI_MAX_TOKENS") else None)

    # Simulation & Demo Security
    simulation_token: Optional[str] = Field(default_factory=lambda: os.getenv("COVENANT_SIMULATION_TOKEN"))

    @property
    def is_production(self) -> bool:
        return self.environment in ("production", "prod", "live")


settings = Settings()
