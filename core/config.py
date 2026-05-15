"""
Application configuration loaded from environment variables.
Uses pydantic-settings to read from a .env file and environment variables.
"""

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings backed by environment variables / .env file.

    Fields:
        app_name: Human-readable service name shown in docs and health checks.
        app_host: Host address the uvicorn server binds to.
        app_port: Port the uvicorn server listens on.
        task_db_path: Path to the SQLite database file for task persistence.
        storage_dir: Directory for runtime artifacts (images, screenshots).
        fb_ad_dry_run: When True, ad creation stops after payload normalization
            and returns a preview without calling any Meta API.
        meta_api_version: Meta Graph API version string (e.g. "v21.0").
        meta_access_token: Meta developer access token for API calls.
        meta_ad_account_id: Default Meta ad account ID (numeric string).
        meta_default_page_id: Default Facebook page ID for ad creatives.
        meta_default_pixel_id: Default Meta Pixel ID for conversion tracking.
        meta_default_currency_multiplier: Multiplier to convert budget amounts
            into the currency subunit (e.g. 100 for dollars to cents).
        cors_origins: List of allowed origins for CORS middleware.
    """

    # ---- application ----
    app_name: str = "Facebook Ad Backend (Material + Catalog)"
    app_host: str = "0.0.0.0"
    app_port: int = 7790

    # ---- storage ----
    task_db_path: str = "storage/tasks.sqlite3"
    storage_dir: str = "storage"

    # ---- Facebook ad ----
    fb_ad_dry_run: bool = True
    meta_api_version: str = "v21.0"
    meta_access_token: str = ""
    meta_ad_account_id: str = ""
    meta_default_page_id: str = ""
    meta_default_pixel_id: str = ""
    meta_default_currency_multiplier: int = 100

    # ---- Meta app credentials (for catalog ads via facebook-business SDK) ----
    meta_app_id: str = ""
    meta_app_secret: str = ""
    fb_token_map_path: str = ""

    # ---- CORS ----
    cors_origins: List[str] = ["*"]

    model_config = SettingsConfigDict(
        env_file=(".env",),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def storage_path(self) -> Path:
        """Return the storage directory as a Path object."""
        return Path(self.storage_dir)

    @property
    def task_db_file(self) -> Path:
        """Return the task database file path as a Path object."""
        return Path(self.task_db_path)


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (singleton)."""
    return Settings()


# Module-level settings instance for convenient import
settings = get_settings()
