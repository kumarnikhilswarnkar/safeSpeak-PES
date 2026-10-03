from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.conftest import TEST_SECRET


def test_health_reports_database_ok(client):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["environment"] == "test"
    assert body["server_time_utc"].endswith("Z") or body["server_time_utc"].endswith("+00:00")


def test_health_returns_503_when_database_unreachable(tmp_path: Path):
    unreachable = tmp_path / "missing-folder" / "test.db"
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=f"sqlite:///{unreachable.as_posix()}",
        jwt_secret_key=TEST_SECRET,
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 503
    assert response.json()["database"] == "unavailable"
