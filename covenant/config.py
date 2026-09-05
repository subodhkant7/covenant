"""Global application settings and configuration."""

from pathlib import Path
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
DEFAULT_DB_PATH = PROJECT_ROOT / "covenant.db"
SYNTHETIC_DATA_DIR = PROJECT_ROOT / "covenant" / "synthetic_data"


class Settings(BaseModel):
    """Application runtime configuration."""
    app_name: str = "Covenant"
    environment: str = "local"
    database_url: str = Field(default_factory=lambda: f"sqlite:///{DEFAULT_DB_PATH}")
    db_path: Path = DEFAULT_DB_PATH
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3:latest"
    system_user_org: str = "Northstar Studio"
    system_user_name: str = "Alex North"
    system_user_email: str = "alex@northstarstudio.com"
    auto_scan_interval_seconds: int = 300


settings = Settings()
