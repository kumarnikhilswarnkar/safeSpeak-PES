import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_SECRET = "test-secret-key-that-is-long-enough-0123456789"

# app.main builds a module-level app from environment settings on import, so the
# test environment must be in place before anything imports it. Environment
# variables take precedence over a developer's backend/.env file.
os.environ["ENVIRONMENT"] = "test"
os.environ["JWT_SECRET_KEY"] = TEST_SECRET
os.environ["DATABASE_URL"] = "sqlite:///" + (Path(tempfile.gettempdir()) / "safespeak_import.db").as_posix()

from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        jwt_secret_key=TEST_SECRET,
    )


@pytest.fixture
def client(settings: Settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client
