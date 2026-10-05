"""TAT breach simulation, escalation, and read-endpoint authorization."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import create_app
from app.models import ComplaintEvent
from tests.workflow_fixtures import CONCERNS, actions, submit, world  # noqa: F401

ESCALATE = f"{CONCERNS}/escalate-overdue"


def breach(client, world, code, who="admin"):
    return client.post(f"{CONCERNS}/{code}/simulate_breach", headers=world.h(who))


@pytest.fixture
def assigned(client, world) -> dict:
    world.model.set("Hostel", 0.9, "Medium", 0.9)
    return submit(client, world)


def count_events(db, action):
    return db.scalar(select(func.count()).select_from(ComplaintEvent).where(ComplaintEvent.action == action))


# --- simulate breach -------------------------------------------------------------

def test_simulate_breach_moves_deadline_into_the_past(client, world, assigned):
    response = breach(client, world, assigned["complaint_id"])

    assert response.status_code == 200
    body = response.json()
    assert body["tat"]["state"] == "OVERDUE"
    event = next(e for e in body["events"] if e["action"] == "tat_breach_simulated")
    assert event["actor"]["id"] == world.users["admin"].id


@pytest.mark.parametrize("who", ["student", "authority", "dean", "viewer"])
def test_only_admin_can_simulate_breach(client, world, assigned, who):
    assert breach(client, world, assigned["complaint_id"], who).status_code == 403


def test_simulate_breach_is_hidden_without_demo_mode(settings, world, assigned):
    with TestClient(create_app(settings.model_copy(update={"demo_mode": False}))) as plain:
        response = plain.post(f"{CONCERNS}/{assigned['complaint_id']}/simulate_breach", headers=world.h("admin"))
    assert response.status_code == 404


# --- escalation -------------------------------------------------------------------

def test_overdue_complaint_escalates_to_next_authority(client, world, assigned):
    code = assigned["complaint_id"]
    breach(client, world, code)

    run = client.post(ESCALATE, headers=world.h("admin"))

    assert run.status_code == 200
    assert run.json()["processed"] == 1
    assert run.json()["outcomes"][0]["result"] == "escalated"
    body = client.get(f"{CONCERNS}/{code}", headers=world.h("admin")).json()
    assert body["assigned_to"]["id"] == world.users["dean"].id
    assert body["escalation_level"] == 2
    assert body["escalated"] is True
    assert body["status"] == "ASSIGNED"
    assert body["tat"]["state"] == "ON_TRACK"
    assert body["tat"]["hours"] == 48  # sample: Medium at level 2
    assert datetime.fromisoformat(body["tat"]["deadline_at"]) > datetime.fromisoformat(body["updated_at"])
    escalation = next(e for e in body["events"] if e["action"] == "escalation_triggered")
    assert escalation["previous_value"]["assigned_user"]["id"] == world.users["authority"].id
    assert escalation["new_value"]["assigned_user"]["id"] == world.users["dean"].id
    assert escalation["actor"]["id"] == world.users["admin"].id
    assert actions(body)[-2:] == ["tat_breached", "escalation_triggered"]
    # The new authority sees it in their queue; the old one does not.
    assert [c["complaint_id"] for c in client.get(f"{CONCERNS}/queue", headers=world.h("dean")).json()] == [code]
    assert client.get(f"{CONCERNS}/queue", headers=world.h("authority")).json() == []


def test_repeated_escalation_runs_do_not_duplicate(client, db, world, assigned):
    breach(client, world, assigned["complaint_id"])

    client.post(ESCALATE, headers=world.h("admin"))
    second = client.post(ESCALATE, headers=world.h("admin")).json()
    third = client.post(ESCALATE, headers=world.h("admin")).json()

    assert second["processed"] == third["processed"] == 0
    assert count_events(db, "escalation_triggered") == 1
    assert count_events(db, "tat_breached") == 1


def test_escalation_stops_at_top_of_chain_without_duplicates(client, db, world, assigned):
    code = assigned["complaint_id"]
    for expected_assignee in ("dean", "director"):
        breach(client, world, code)
        client.post(ESCALATE, headers=world.h("admin"))
        body = client.get(f"{CONCERNS}/{code}", headers=world.h("admin")).json()
        assert body["assigned_to"]["id"] == world.users[expected_assignee].id

    breach(client, world, code)
    first = client.post(ESCALATE, headers=world.h("admin")).json()
    repeat = client.post(ESCALATE, headers=world.h("admin")).json()

    assert first["outcomes"][0]["result"] == "exhausted"
    assert repeat["processed"] == 0
    body = client.get(f"{CONCERNS}/{code}", headers=world.h("admin")).json()
    assert body["breached_at_top"] is True
    assert body["assigned_to"]["id"] == world.users["director"].id
    assert count_events(db, "escalation_exhausted") == 1


def test_pending_review_complaint_also_escalates(client, world):
    world.model.set("Other", 0.2, "Medium", 0.7)
    code = submit(client, world)["complaint_id"]
    breach(client, world, code)

    client.post(ESCALATE, headers=world.h("admin"))

    body = client.get(f"{CONCERNS}/{code}", headers=world.h("dean")).json()
    assert body["status"] == "PENDING_REVIEW"
    assert body["tat"]["stage"] == "REVIEW"
    assert body["assigned_to"]["id"] == world.users["dean"].id


@pytest.mark.parametrize("who", ["student", "authority", "dean", "viewer"])
def test_only_admin_can_run_escalation(client, world, who):
    assert client.post(ESCALATE, headers=world.h(who)).status_code == 403


def test_resolved_complaints_never_escalate(client, world, assigned):
    code = assigned["complaint_id"]
    client.post(f"{CONCERNS}/{code}/review", json={"action": "resolve", "remarks": "Fixed"}, headers=world.h("authority"))

    assert breach(client, world, code).status_code == 409
    assert client.post(ESCALATE, headers=world.h("admin")).json()["processed"] == 0


# --- read endpoints -----------------------------------------------------------------

def test_mine_lists_only_own_complaints(client, world, assigned):
    submit(client, world, "student2")

    mine = client.get(f"{CONCERNS}/mine", headers=world.h("student")).json()

    assert [c["complaint_id"] for c in mine] == [assigned["complaint_id"]]


def test_other_users_cannot_read_a_complaint(client, world, assigned):
    code = assigned["complaint_id"]
    assert client.get(f"{CONCERNS}/{code}", headers=world.h("student2")).status_code == 404
    assert client.get(f"{CONCERNS}/{code}", headers=world.h("authority_cse")).status_code == 404
    assert client.get(f"{CONCERNS}/{code}", headers=world.h("viewer_cse")).status_code == 404
    assert client.get(f"{CONCERNS}/{code}").status_code == 401


def test_permitted_readers_can_read(client, world, assigned):
    code = assigned["complaint_id"]
    for who in ("student", "authority", "viewer", "admin"):
        assert client.get(f"{CONCERNS}/{code}", headers=world.h(who)).status_code == 200


def test_viewer_has_read_only_scoped_list(client, world, assigned):
    institution = client.get(CONCERNS, headers=world.h("viewer")).json()
    cse_only = client.get(CONCERNS, headers=world.h("viewer_cse")).json()

    assert [c["complaint_id"] for c in institution] == [assigned["complaint_id"]]
    assert cse_only == []
    assert client.post(
        f"{CONCERNS}/{assigned['complaint_id']}/review", json={"action": "accept"}, headers=world.h("viewer")
    ).status_code == 403


@pytest.mark.parametrize(
    ("path", "who"),
    [("/mine", "viewer"), ("/mine", "admin"), ("/queue", "student"), ("/pending-triage", "student"), ("", "student")],
)
def test_list_endpoints_enforce_permissions(client, world, path, who):
    assert client.get(f"{CONCERNS}{path}", headers=world.h(who)).status_code == 403
