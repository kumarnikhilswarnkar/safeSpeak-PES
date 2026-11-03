"""Regression tests for findings verified during the Phase 3 inspection:

- direct-API complaint isolation between students, departments and roles (no leaks in 404s);
- category-specific routing to a fixed office (the SSP-2026-000017 case: an Infrastructure
  complaint goes to the Facilities Office authority, not to the complainant's department
  authority, who correctly cannot see it);
- a human override that changes the category re-routes, restarts the TAT, keeps the
  original AI output, records who/when/why, and is what the complainant and the
  Assistant see afterwards.
"""
import pytest

from app.core.permissions import Role
from app.models import Department, DepartmentKind
from app.services.user_service import create_user
from seed.prototype_rules import seed_demo_routing
from tests.conftest import TEST_DOMAIN, TEST_PASSWORD, bearer
from tests.workflow_fixtures import CONCERNS, actions, submit, world  # noqa: F401

HOSTEL = "The hostel mess food has been cold for a week."


@pytest.fixture
def facilities(client, db, settings, world):
    """Add the sample Facilities Office, its L1 authority and the office chain (as the demo seed does)."""
    office = Department(code="FACILITIES", name="Facilities Office", kind=DepartmentKind.OFFICE.value)
    db.add(office)
    db.flush()
    user = create_user(db, settings, name="Facilities Authority", email=f"facilities@{TEST_DOMAIN}", password=TEST_PASSWORD,
                       role=Role.DEPARTMENT_AUTHORITY, department_id=office.id, authority_level=1)
    assert seed_demo_routing(db, {"FACILITIES": office}) == 3
    db.commit()
    token = client.post("/api/v1/auth/login", json={"email": user.email, "password": TEST_PASSWORD}).json()["access_token"]
    return {"user": user, "office": office, "headers": bearer(token)}


@pytest.fixture
def hostel(client, world):
    world.model.set("Hostel", 0.9, "Medium", 0.9)
    return submit(client, world, "student", HOSTEL)


# --- C. direct API isolation ------------------------------------------------------------------

def test_student_cannot_read_another_students_complaint_and_nothing_leaks(client, world, hostel):
    code = hostel["complaint_id"]
    own = client.get(f"{CONCERNS}/{code}", headers=world.h("student"))
    other = client.get(f"{CONCERNS}/{code}", headers=world.h("student2"))
    missing = client.get(f"{CONCERNS}/SSP-2099-999999", headers=world.h("student2"))
    assert own.status_code == 200
    assert other.status_code == missing.status_code == 404
    assert other.json() == missing.json() == {"detail": "Complaint not found"}
    assert HOSTEL not in other.text and "Hostel" not in other.text
    assert code not in [c["complaint_id"] for c in client.get(f"{CONCERNS}/mine", headers=world.h("student2")).json()]


def test_authority_outside_scope_cannot_read_or_act(client, world, hostel):
    code = hostel["complaint_id"]
    h = world.h("authority_cse")  # CSE authority; the complaint is MCA's
    assert client.get(f"{CONCERNS}/{code}", headers=h).status_code == 404
    assert client.post(f"{CONCERNS}/{code}/review", json={"action": "accept"}, headers=h).status_code == 404
    assert client.get(f"{CONCERNS}/{code}/reroute-targets", headers=h).status_code == 404
    assert code not in [c["complaint_id"] for c in client.get(f"{CONCERNS}/queue", headers=h).json()]


def test_admin_reads_in_scope_but_cannot_take_authority_actions(client, world, hostel):
    code = hostel["complaint_id"]
    h = world.h("admin")
    assert client.get(f"{CONCERNS}/{code}", headers=h).status_code == 200
    assert client.post(f"{CONCERNS}/{code}/review", json={"action": "accept"}, headers=h).status_code == 403
    assert client.post(f"{CONCERNS}/{code}/review", json={"action": "resolve", "remarks": "x"}, headers=h).status_code == 403
    assert client.get(f"{CONCERNS}/{code}/reroute-targets", headers=h).status_code == 403


# --- D. routing to a fixed office ---------------------------------------------------------------

def test_infrastructure_complaint_routes_to_the_facilities_office(client, world, facilities):
    world.model.set("Infrastructure and facilities", 0.9, "High", 0.9)  # High: human review required
    body = submit(client, world, "student", "The lab projector is broken.")
    code = body["complaint_id"]

    assert body["assigned_to"]["id"] == facilities["user"].id
    assert body["handling_department"]["code"] == "FACILITIES"
    assert body["routing"]["last_decision"]["target_scope"] == "FIXED_DEPARTMENT"

    # The complainant's own department authority is not in scope: same 404 as any other complaint.
    assert client.get(f"{CONCERNS}/{code}", headers=world.h("authority")).status_code == 404
    assert client.get(f"{CONCERNS}/queue", headers=world.h("authority")).json() == []

    # The Facilities authority sees it in their queue and can act on it.
    queue = client.get(f"{CONCERNS}/pending-triage", headers=facilities["headers"]).json()
    assert [c["complaint_id"] for c in queue] == [code]
    assert client.post(f"{CONCERNS}/{code}/review", json={"action": "accept"}, headers=facilities["headers"]).status_code == 200


# --- A + F. human override reroutes and is reflected everywhere --------------------------------

def test_category_override_reroutes_restarts_tat_and_is_visible_to_student_and_assistant(client, world, facilities):
    world.model.set("Hostel", 0.4, "Medium", 0.9)  # low category confidence -> human review
    pending = submit(client, world, "student", "The corridor light near our room is broken.")
    code = pending["complaint_id"]
    assert pending["status"] == "PENDING_REVIEW" and pending["assigned_to"]["id"] == world.users["authority"].id

    r = client.post(f"{CONCERNS}/{code}/review", headers=world.h("authority"), json={
        "action": "override", "category": "Infrastructure and facilities", "remarks": "Electrical fault, not hostel admin."})
    assert r.status_code == 200
    after = r.json()

    # Re-routed for the decided category, with a new resolution deadline.
    assert after["category"] == "Infrastructure and facilities"
    assert after["decision_source"] == "HUMAN_OVERRIDDEN"
    assert after["assigned_to"]["id"] == facilities["user"].id
    assert after["tat"]["stage"] == "RESOLUTION" and after["tat"]["deadline_at"] != pending["tat"]["deadline_at"]

    # Original AI recommendation and the human decision are recorded separately.
    assert after["ai"]["category"] == "Hostel"
    decision = after["human_decision"]
    assert decision["action"] == "overridden" and decision["reviewer"]["id"] == world.users["authority"].id
    assert decision["remarks"] == "Electrical fault, not hostel admin." and decision["at"]
    assert decision["previous"]["category"] == "Hostel" and decision["new"]["category"] == "Infrastructure and facilities"
    assert actions(after)[-2:] == ["overridden", "assigned"]

    # The student's case file shows the current decision and assignment...
    mine = client.get(f"{CONCERNS}/{code}", headers=world.h("student")).json()
    assert (mine["category"], mine["assigned_to"]["id"]) == ("Infrastructure and facilities", facilities["user"].id)

    # ...and so does the Assistant.
    reply = client.post("/api/v1/assistant/messages", headers=world.h("student"),
                        json={"message": f"who is handling {code}?"}).json()
    assert "Facilities Authority" in reply["reply"]
    assert reply["cards"][0]["category"] == "Infrastructure and facilities"
    # The previous reviewer no longer has it and cannot read it.
    assert client.get(f"{CONCERNS}/{code}", headers=world.h("authority")).status_code == 404
