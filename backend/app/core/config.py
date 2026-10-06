"""Application settings, loaded from environment variables and backend/.env."""
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent

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
    # Optional separate account for schema migrations (PostgreSQL owner role).
    # The running API uses DATABASE_URL, which in deployment is a least-privilege
    # role that can read and write rows but cannot change the schema or delete.
    migration_database_url: str | None = None

    jwt_secret_key: SecretStr
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    access_token_expire_minutes: int = Field(default=60, ge=5, le=1440)
    # bcrypt work factor. 12 is the default; tests lower it to stay fast.
    bcrypt_rounds: int = Field(default=12, ge=4, le=15)

    # Kept as raw comma-separated strings; use the parsed properties below.
    # An empty domain list disables sign-in entirely (fail closed).
    allowed_email_domains: str = ""
    cors_origins: str = "http://localhost:5173"

    display_timezone: str = "Asia/Kolkata"

    # AI triage. MODEL_DIR holds category.joblib, priority.joblib and metadata.json
    # produced by ml/train_triage.py.
    model_dir: Path = REPO_DIR / "ml" / "artifacts" / "v2"
    # Model evaluation report shown on the research page (ml/train_triage_v2.py).
    evaluation_report: Path = REPO_DIR / "ml" / "reports" / "evaluation.json"
    # Complaints whose category or priority confidence is below this go to human
    # review. Leave unset to use the threshold selected on validation data and
    # recorded in the model's metadata.json.
    confidence_threshold: float | None = Field(default=None, gt=0, le=1)
    # High and Critical AI priorities always require human review.
    review_high_severity: bool = True
    # Share of the TAT left at which a deadline is shown as "due soon".
    due_soon_fraction: float = Field(default=0.25, gt=0, lt=1)

    # Automatic TAT monitor: a background task inside the API process that checks
    # for overdue complaints and escalates them. Run the API with ONE worker
    # process so only one monitor runs.
    tat_monitor_enabled: bool = True
    tat_monitor_interval_seconds: int = Field(default=60, ge=5, le=3600)

    # Enables demo-only endpoints such as simulating a TAT breach. Never in production.
    demo_mode: bool = False

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

    @field_validator("demo_mode")
    @classmethod
    def _no_demo_mode_in_production(cls, value: bool, info) -> bool:
        if value and info.data.get("environment") == "production":
            raise ValueError("DEMO_MODE cannot be enabled in production")
        return value

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
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")


@lru_cache
def get_settings() -> Settings:
    return Settings()
