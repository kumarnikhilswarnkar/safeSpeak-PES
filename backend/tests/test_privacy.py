"""Personal data is not returned or logged unnecessarily, and database
failures do not leak data."""
import json
import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.session import create_db_engine
from app.main import create_app
from tests.conftest import TEST_PASSWORD
from tests.workflow_fixtures import CONCERNS, submit, world  # noqa: F401

SECRET_TEXT = "ZQX-private-detail-7781 my roommate's medical condition"


def test_complaint_responses_never_contain_email_addresses(client, world):
    world.model.set("Other", 0.1, "Medium", 0.9)
    code = submit(client, world, description=SECRET_TEXT)["complaint_id"]
    client.post(f"{CONCERNS}/{code}/review", json={"action": "accept", "remarks": "checked"}, headers=world.h("authority"))

    responses = [
        client.get(f"{CONCERNS}/{code}", headers=world.h("student")),
        client.get(f"{CONCERNS}/{code}", headers=world.h("authority")),
        client.get(f"{CONCERNS}/mine", headers=world.h("student")),
        client.get(f"{CONCERNS}/queue", headers=world.h("authority")),
        client.get(CONCERNS, headers=world.h("admin")),
        client.get("/api/v1/notifications", headers=world.h("student")),
        client.get(f"{CONCERNS}/{code}/reroute-targets", headers=world.h("authority")),
    ]
    for response in responses:
        assert response.status_code == 200, response.text
        body = json.dumps(response.json())
        assert "@safespeak.test" not in body
        assert "password" not in body.lower()


def test_complaint_text_and_passwords_are_not_logged(client, world, caplog):
    caplog.set_level(logging.DEBUG)
    client.post("/api/v1/auth/login", json={"email": world.users["student"].email, "password": TEST_PASSWORD})
    world.model.set("Other", 0.1, "Medium", 0.9)
    code = submit(client, world, description=SECRET_TEXT)["complaint_id"]
    client.post(
        f"{CONCERNS}/{code}/review",
        json={"action": "override", "category": "Hostel", "remarks": SECRET_TEXT},
        headers=world.h("authority"),
    )

    assert "ZQX-private-detail-7781" not in caplog.text
    assert TEST_PASSWORD not in caplog.text


def test_sql_errors_do_not_expose_bound_values(tmp_path):
    engine = create_db_engine(f"sqlite:///{(tmp_path / 'p.db').as_posix()}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE t (x TEXT NOT NULL UNIQUE)"))
        conn.execute(text("INSERT INTO t VALUES (:x)"), {"x": SECRET_TEXT})
    with engine.connect() as conn, pytest.raises(DBAPIError) as caught:
        conn.execute(text("INSERT INTO t VALUES (:x)"), {"x": SECRET_TEXT})
    assert "ZQX-private-detail-7781" not in str(caught.value)
    engine.dispose()


def test_unreachable_database_returns_503_not_a_stack_trace(settings):
    # Port 1 on localhost: connection refused immediately.
    broken = settings.model_copy(update={"database_url": "postgresql+psycopg://nobody:x@127.0.0.1:1/none"})
    with TestClient(create_app(broken), raise_server_exceptions=False) as client:
        response = client.post("/api/v1/auth/login", json={"email": "student@safespeak.test", "password": "x" * 12})
    assert response.status_code == 503
    assert response.json() == {"detail": "The database is temporarily unavailable. Please try again shortly."}
