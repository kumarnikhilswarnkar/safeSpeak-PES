"""Alembic migrations build the same schema as the models."""
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect

from app.core.config import BACKEND_DIR, get_settings
from app.db.base import Base
from app.db.session import create_db_engine
from tests.conftest import TEST_DATABASE_URL, reset_postgres_schema


@pytest.fixture(params=["sqlite", "postgresql"])
def migrated_url(request, tmp_path: Path, monkeypatch):
    if request.param == "postgresql":
        if not TEST_DATABASE_URL:
            pytest.skip("TEST_DATABASE_URL not set (PostgreSQL migration test runs in CI/Docker)")
        reset_postgres_schema(TEST_DATABASE_URL)
        url = TEST_DATABASE_URL
    else:
        url = f"sqlite:///{(tmp_path / 'migrations.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.delenv("MIGRATION_DATABASE_URL", raising=False)
    get_settings.cache_clear()
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    command.upgrade(config, "head")
    yield url, config
    get_settings.cache_clear()


def test_upgrade_creates_tables(migrated_url):
    url, _ = migrated_url
    engine = create_db_engine(url)
    assert {"departments", "users", "alembic_version"} <= set(inspect(engine).get_table_names())
    engine.dispose()


def test_migrations_match_models(migrated_url):
    url, _ = migrated_url
    engine = create_db_engine(url)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    engine.dispose()
    assert diff == []


def test_downgrade_removes_tables(migrated_url):
    url, config = migrated_url
    command.downgrade(config, "base")
    engine = create_db_engine(url)
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    engine.dispose()
