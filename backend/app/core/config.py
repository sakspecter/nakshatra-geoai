"""Application configuration loaded from environment / ``.env``.

Uses :mod:`pydantic_settings` (Pydantic v2). Any secret can be overridden via
environment variables at deploy time; the constructor prioritises an explicit
``POSTGRES_ASYNC_URL``.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global typed settings for the backend.

    Environment file location and the var-prefix toggle are configured through
    ``SettingsConfigDict``. Because ``env_file=None`` is NOT set, pydantic-settings
    automatically reads the nearest ``.env``/``.env.example`` unless overridden.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------ project
    PROJECT_NAME: str = "Project Nakshatra"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False
    VERSION: str = "0.1.0"

    # --------------------------------------------------------------- database
    # The primary async connection string. Kept optional in type so that
    # :meth:`postgres_async_url` can compose it from individual credentials when
    # the fully-assembled URL is not supplied (common in CI).
    POSTGRES_ASYNC_URL: Optional[PostgresDsn] = Field(
        default=None,
        description="Full asyncpg DSN, e.g. postgresql+asyncpg://user:pw@host:5432/nk",
    )

    # Split credentials (fallback path for composing the DSN)
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "nakshatra"
    POSTGRES_DRIVER: str = "postgresql+asyncpg"

    # ------------------------------------------------------------ pool settings
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800
    DB_ECHO: bool = False

    # ------------------------------------------------------------- provenance
    # Rule 6: default version pins carried on every record the API creates when
    # the caller does not supply them. Prevents an "unversioned" insert drift.
    DEFAULT_DATASET_VERSION: str = "dataset.unknown"
    DEFAULT_MODEL_VERSION: str = "model.none"
    DEFAULT_SCENARIO_VERSION: str = "scenario.baseline"
    DEFAULT_RISK_CONFIG_VERSION: str = "risk_cfg.v1"

    # --------------------------------------------------------------- CORS / API
    BACKEND_CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # ------------------------------------------------------------- engine pins
    # Whether the Hazard/Vulnerability engines are permitted to run against NULL
    # feature inputs. Hard-wired False: Rule 2 forbids fabricating safe values.
    ALLOW_SCORING_ON_MISSING: bool = False

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def _assemble_cors(cls, value: object) -> object:
        """Accept either a JSON list in env or a plain string fallback."""
        if isinstance(value, str) and not value.startswith("["):
            return [host.strip() for host in value.split(",")]
        return value

    @property
    def postgres_async_url_resolved(self) -> str:
        """Return the effective async database DSN.

        Respects an explicit ``POSTGRES_ASYNC_URL`` first; otherwise composes a
        sane connection string from the split credential fields.
        """
        if self.POSTGRES_ASYNC_URL:
            return str(self.POSTGRES_ASYNC_URL)
        return (
            f"{self.POSTGRES_DRIVER}://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cache a single Settings instance for the lifetime of the process."""
    return Settings()


settings = get_settings()
