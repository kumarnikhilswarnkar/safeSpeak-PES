"""PostgreSQL-specific behaviour. Skipped unless TEST_DATABASE_URL points at a
PostgreSQL test database (CI service container, Docker/Codespaces stack)."""
import threading
import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.core.config import BACKEND_DIR, REPO_DIR, get_settings
from app.models import ComplaintEvent
from app.services import complaint_service
from tests.conftest import TEST_DATABASE_URL, reset_postgres_schema
from tests.workflow_fixtures import CONCERNS, submit, world  # noqa: F401

pytestmark = pytest.mark.skipif(
    not (TEST_DATABASE_URL or "").startswith("postgresql"),
    reason="TEST_DATABASE_URL is not a PostgreSQL database",
)

GRANTS_SQL = REPO_DIR / "deploy" / "postgres" / "app_role_grants.sql"


@pytest.fixture
def migrated(monkeypatch):
    reset_postgres_schema(TEST_DATABASE_URL)
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.delenv("MIGRATION_DATABASE_URL", raising=False)
    get_settings.cache_clear()
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    get_settings.cache_clear()
    engine = create_engine(TEST_DATABASE_URL)
    yield engine
    engine.dispose()


def test_json_documents_are_jsonb(migrated):
    columns = {c["name"]: c["type"] for c in inspect(migrated).get_columns("ai_predictions")}
    for name in ("probabilities", "flag_reasons", "explanation"):
        assert type(columns[name]).__name__ == "JSONB", name


def test_append_only_triggers_also_block_truncate(migrated):
    with migrated.connect() as conn, pytest.raises(DBAPIError, match="append-only"):
        conn.execute(text("TRUNCATE complaint_events"))


def _apply_grants(conn, owner: str, app: str) -> None:
    sql = GRANTS_SQL.read_text(encoding="utf-8")
    sql = sql.replace(':"owner"', f'"{owner}"').replace(':"app"', f'"{app}"')
    statements = [s for s in (part.strip() for part in "\n".join(
        line for line in sql.splitlines() if not line.strip().startswith("--")
    ).split(";")) if s]
    for statement in statements:
        conn.execute(text(statement))


def test_app_role_cannot_delete_or_change_schema(migrated):
    app_role = f"safespeak_app_test_{uuid.uuid4().hex[:8]}"
    password = uuid.uuid4().hex
    with migrated.begin() as conn:
        owner = conn.execute(text("SELECT current_user")).scalar()
        try:
            conn.execute(text(f"CREATE ROLE \"{app_role}\" LOGIN PASSWORD '{password}'"))
        except ProgrammingError:
            pytest.skip("test account may not create roles (needs CREATEROLE, as in CI)")
        database = conn.execute(text("SELECT current_database()")).scalar()
        conn.execute(text(f'GRANT CONNECT ON DATABASE "{database}" TO "{app_role}"'))
        _apply_grants(conn, owner, app_role)
    app_url = make_url(TEST_DATABASE_URL).set(username=app_role, password=password)
    app_engine = create_engine(app_url)
    try:
        with app_engine.connect() as conn:
            conn.execute(text("SELECT count(*) FROM complaints"))
            conn.execute(text("UPDATE id_counters SET last_value = last_value WHERE false"))
            for statement in (
                "DELETE FROM complaints",
                "TRUNCATE id_counters",
                "CREATE TABLE should_not_exist (x int)",
                "DROP TABLE complaints",
            ):
                with pytest.raises(DBAPIError):
                    conn.execute(text(statement))
                conn.rollback()
    finally:
        app_engine.dispose()
        with migrated.begin() as conn:
            conn.execute(text(f'REASSIGN OWNED BY "{app_role}" TO "{owner}"'))
            conn.execute(text(f'DROP OWNED BY "{app_role}"'))
            conn.execute(text(f'DROP ROLE "{app_role}"'))


def test_concurrent_escalation_checks_escalate_once(client, app, world):
    world.model.set("Hostel", 0.9, "Medium", 0.9)
    code = submit(client, world)["complaint_id"]
    assert client.post(f"{CONCERNS}/{code}/simulate_breach", headers=world.h("admin")).status_code == 200

    # Two checks at the same moment, bypassing the in-process lock: PostgreSQL
    # row locks (SELECT ... FOR UPDATE) must still prevent a double escalation.
    barrier = threading.Barrier(2)
    results = []

    def check():
        with app.state.session_factory() as db:
            barrier.wait()
            results.append(complaint_service.escalate_overdue(db, None))

    threads = [threading.Thread(target=check) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(len(r) for r in results) == [0, 1]
    with app.state.session_factory() as db:
        count = db.scalar(select(func.count()).select_from(ComplaintEvent).where(ComplaintEvent.action == "escalation_triggered"))
    assert count == 1


def test_complaint_ids_are_sequential_under_postgres(client, world):
    codes = [submit(client, world)["complaint_id"] for _ in range(3)]
    numbers = [int(c.rsplit("-", 1)[1]) for c in codes]
    assert numbers == list(range(numbers[0], numbers[0] + 3))
