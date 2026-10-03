"""Application settings, loaded from environment variables and backend/.env."""
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]

_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
_PLACEHOLDER_MARKERS = ("changeme", "change_me", "change-me", "placeholder")


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "SafeSpeak PES API"
    environment: Literal["development", "test", "production"] = "development"

    database_url: str = "sqlite:///./safespeak_dev.db"

    jwt_secret_key: SecretStr
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    access_token_expire_minutes: int = Field(default=60, ge=5, le=1440)

    # Kept as raw comma-separated strings; use the parsed properties below.
    allowed_email_domains: str = ""
    cors_origins: str = "http://localhost:5173"

    display_timezone: str = "Asia/Kolkata"

    @field_validator("database_url")
    @classmethod
    def _anchor_relative_sqlite_path(cls, value: str) -> str:
        # A relative SQLite path would depend on the current working directory, so
        # uvicorn, Alembic and pytest could end up using different files.
        prefix = "sqlite:///"
        if value.startswith(prefix) and not value.startswith(prefix + "/") and ":memory:" not in value:
            path = Path(value[len(prefix):])
            if not path.is_absolute():
                return prefix + (BACKEND_DIR / path).resolve().as_posix()
        return value

    @field_validator("jwt_secret_key")
    @classmethod
    def _reject_weak_secret(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if len(secret) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters long")
        if any(marker in secret.lower() for marker in _PLACEHOLDER_MARKERS):
            raise ValueError("JWT_SECRET_KEY still contains a placeholder value")
        return value

    @field_validator("allowed_email_domains")
    @classmethod
    def _validate_domains(cls, value: str) -> str:
        domains = [d.lower().removeprefix("@") for d in _split_csv(value)]
        invalid = [d for d in domains if not _DOMAIN_RE.match(d)]
        if invalid:
            raise ValueError(f"Invalid email domain(s) in ALLOWED_EMAIL_DOMAINS: {', '.join(invalid)}")
        return ",".join(domains)

    @field_validator("display_timezone")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone: {value}") from exc
        return value

    @property
    def email_domains(self) -> tuple[str, ...]:
        return tuple(_split_csv(self.allowed_email_domains))

    @property
    def cors_origin_list(self) -> list[str]:
        return _split_csv(self.cors_origins)

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.display_timezone)

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
