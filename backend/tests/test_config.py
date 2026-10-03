import pytest
from pydantic import ValidationError

from app.core.config import BACKEND_DIR, Settings
from tests.conftest import TEST_SECRET


def make_settings(**overrides) -> Settings:
    values = {"jwt_secret_key": TEST_SECRET, **overrides}
    return Settings(_env_file=None, **values)


def test_jwt_secret_is_required(monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("secret", ["too-short", "changeme-changeme-changeme-changeme-1234"])
def test_weak_or_placeholder_jwt_secret_is_rejected(secret):
    with pytest.raises(ValidationError):
        make_settings(jwt_secret_key=secret)


def test_email_domains_default_to_none_configured():
    assert make_settings(allowed_email_domains="").email_domains == ()


def test_email_domains_are_normalised():
    settings = make_settings(allowed_email_domains=" @Example.EDU , campus.example.ac.in ")
    assert settings.email_domains == ("example.edu", "campus.example.ac.in")


@pytest.mark.parametrize("domains", ["not a domain", "example", "user@example.edu"])
def test_invalid_email_domains_are_rejected(domains):
    with pytest.raises(ValidationError):
        make_settings(allowed_email_domains=domains)


def test_relative_sqlite_path_is_anchored_to_backend_folder():
    settings = make_settings(database_url="sqlite:///./local.db")
    assert settings.database_url == "sqlite:///" + (BACKEND_DIR / "local.db").resolve().as_posix()


def test_non_sqlite_url_is_left_unchanged():
    url = "postgresql+psycopg://user:pw@localhost:5432/safespeak"
    assert make_settings(database_url=url).database_url == url


def test_unknown_timezone_is_rejected():
    with pytest.raises(ValidationError):
        make_settings(display_timezone="Mars/Olympus")
