import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_SECRET = "test-secret-key-that-is-long-enough-0123456789"
TEST_DOMAIN = "safespeak.test"
TEST_PASSWORD = "correct-horse-battery"
# Optional: run the suite against PostgreSQL (CI, Docker/Codespaces), e.g.
# TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5433/safespeak_test
# Every test gets a freshly created schema. Without it, each test uses its own SQLite file.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

# app.main builds a module-level app from environment settings on import, so the
# test environment must be in place before anything imports it. Environment
# variables take precedence over a developer's backend/.env file.
os.environ["ENVIRONMENT"] = "test"
os.environ["JWT_SECRET_KEY"] = TEST_SECRET
os.environ["DATABASE_URL"] = "sqlite:///" + (Path(tempfile.gettempdir()) / "safespeak_import.db").as_posix()

from app.core.config import Settings  # noqa: E402
from app.core.permissions import Role  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Department, DepartmentKind  # noqa: E402
from app.services.user_service import create_user  # noqa: E402


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_url=TEST_DATABASE_URL or f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        jwt_secret_key=TEST_SECRET,
        allowed_email_domains=TEST_DOMAIN,
        bcrypt_rounds=4,
        confidence_threshold=0.5,
        demo_mode=True,
        # Tests drive the monitor directly instead of waiting for the background loop.
        tat_monitor_enabled=False,
    )


def reset_postgres_schema(url: str) -> None:
    """Drop and recreate the public schema of the (dedicated) test database."""
    from sqlalchemy import create_engine, text

    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()


@pytest.fixture
def app(settings: Settings):
    if settings.is_postgres:
        reset_postgres_schema(settings.database_url)
    application = create_app(settings)
    Base.metadata.create_all(application.state.engine)
    yield application
    application.state.engine.dispose()


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db(app):
    with app.state.session_factory() as session:
        yield session


@pytest.fixture
def department(db) -> Department:
    dept = Department(code="MCA", name="Computer Applications", kind=DepartmentKind.ACADEMIC.value)
    db.add(dept)
    db.commit()
    return dept


# Department and authority level each role needs to be a valid account.
_ROLE_DEFAULTS = {
    Role.STUDENT: (True, None),
    Role.TEACHING_STAFF: (True, None),
    Role.NON_TEACHING_STAFF: (True, None),
    Role.DEPARTMENT_AUTHORITY: (True, 1),
    Role.HIGHER_AUTHORITY: (False, 3),
    Role.VIEWER: (False, None),
    Role.ADMIN: (False, None),
}


@pytest.fixture
def make_user(db, settings, department):
    def factory(role: Role, *, email: str | None = None, is_active: bool = True):
        needs_department, level = _ROLE_DEFAULTS[role]
        user = create_user(
            db,
            settings,
            name=f"Test {role.value}",
            email=email or f"{role.value}@{TEST_DOMAIN}",
            password=TEST_PASSWORD,
            role=role,
            department_id=department.id if needs_department else None,
            authority_level=level,
            is_active=is_active,
        )
        db.commit()
        return user

    return factory


@pytest.fixture
def login(client):
    def do_login(email: str, password: str = TEST_PASSWORD) -> str:
        response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert response.status_code == 200, response.text
        return response.json()["access_token"]

    return do_login


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
