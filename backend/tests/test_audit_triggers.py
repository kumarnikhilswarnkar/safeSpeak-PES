"""The database itself refuses to rewrite the audit trail or the original AI
recommendation (migration c7e4a9d2b310), on SQLite and on PostgreSQL.

These tests build the schema with Alembic (not create_all), so the triggers
exist, then run the normal workflow on top to show the triggers do not block it.
"""
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.config import BACKEND_DIR, Settings, get_settings
from tests.conftest import TEST_DATABASE_URL, reset_postgres_schema
from tests.workflow_fixtures import CONCERNS, submit, world  # noqa: F401


@pytest.fixture(params=["sqlite", "postgresql"])
def settings(request, tmp_path: Path, monkeypatch) -> Settings:
    if request.param == "postgresql":
        if not TEST_DATABASE_URL:
            pytest.skip("TEST_DATABASE_URL not set (PostgreSQL trigger test runs in CI/Docker)")
        reset_postgres_schema(TEST_DATABASE_URL)
        url = TEST_DATABASE_URL
    else:
        url = f"sqlite:///{(tmp_path / 'migrated.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.delenv("MIGRATION_DATABASE_URL", raising=False)
    get_settings.cache_clear()
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    get_settings.cache_clear()
    return Settings(
        _env_file=None,
        environment="test",
        database_url=url,
        jwt_secret_key="test-secret-key-that-is-long-enough-0123456789",
        allowed_email_domains="safespeak.test",
        bcrypt_rounds=4,
        confidence_threshold=0.5,
        demo_mode=True,
        tat_monitor_enabled=False,
    )


@pytest.fixture
def pending(client, world) -> dict:
    world.model.set("Other", 0.1, "Medium", 0.9)
    return submit(client, world)


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE complaint_events SET remarks = 'rewritten'",
        "DELETE FROM complaint_events",
        "UPDATE ai_predictions SET category = 'Hostel'",
        "DELETE FROM ai_predictions",
    ],
)
def test_database_refuses_to_rewrite_audit_and_ai_rows(app, pending, statement):
    with app.state.engine.connect() as conn:
        with pytest.raises(DBAPIError, match="append-only"):
            conn.execute(text(statement))
            conn.commit()
        conn.rollback()
        assert conn.execute(text("SELECT count(*) FROM complaint_events")).scalar() > 0
        assert conn.execute(text("SELECT count(*) FROM ai_predictions")).scalar() == 1


def test_workflow_still_works_with_triggers(client, app, world, pending):
    code = pending["complaint_id"]
    reviewed = client.post(f"{CONCERNS}/{code}/review", json={"action": "accept"}, headers=world.h("authority"))
    assert reviewed.status_code == 200
    assert client.post(f"{CONCERNS}/{code}/simulate_breach", headers=world.h("admin")).status_code == 200
    run = app.state.tat_monitor.run_once()
    assert run.escalated == [code]
    events = [e["action"] for e in client.get(f"{CONCERNS}/{code}", headers=world.h("admin")).json()["events"]]
    assert {"accepted", "tat_breached", "escalation_triggered"} <= set(events)
