"""End-to-end lifecycle: submission -> AI -> human review -> assignment -> TAT -> resolution,
for both an accepted and an overridden AI recommendation, and the guarantee that a resolved
complaint cannot be moved back into an open state."""
import pytest

from tests.workflow_fixtures import CONCERNS, actions, submit, world  # noqa: F401


def review(client, world, who, code, **body):
    return client.post(f"{CONCERNS}/{code}/review", json=body, headers=world.h(who))


@pytest.mark.parametrize("decision", ["accept", "override"])
def test_full_lifecycle(client, world, decision):
    world.model.set("Hostel", 0.9, "High", 0.9)  # High -> mandatory human review
    created = submit(client, world)
    code = created["complaint_id"]
    assert created["status"] == "PENDING_REVIEW" and created["tat"]["stage"] == "REVIEW"
    assert created["ai"]["category"] == "Hostel" and created["ai"]["priority"] == "High"

    if decision == "accept":
        r = review(client, world, "authority", code, action="accept", remarks="Confirmed.")
        expected = ("Hostel", "High", "HUMAN_ACCEPTED")
    else:
        r = review(client, world, "authority", code, action="override", priority="Medium", remarks="Only one room.")
        expected = ("Hostel", "Medium", "HUMAN_OVERRIDDEN")
    assert r.status_code == 200
    body = r.json()
    assert (body["category"], body["priority"], body["decision_source"]) == expected
    assert body["status"] == "ASSIGNED" and body["tat"]["stage"] == "RESOLUTION"
    # The AI recommendation is preserved separately from the human decision.
    assert (body["ai"]["category"], body["ai"]["priority"]) == ("Hostel", "High")

    resolved = review(client, world, "authority", code, action="resolve", remarks="Fixed by maintenance.").json()
    assert resolved["status"] == "RESOLVED" and resolved["tat"]["state"] == "STOPPED"

    # Student and administrator see the same final state.
    for who in ("student", "admin"):
        view = client.get(f"{CONCERNS}/{code}", headers=world.h(who)).json()
        assert (view["status"], view["category"], view["priority"], view["decision_source"]) == ("RESOLVED", *expected[:2], expected[2])
        assert view["resolution_note"] == "Fixed by maintenance."
    assert actions(resolved)[-1] == "resolved"


def test_resolved_complaint_cannot_return_to_an_open_state(client, world):
    world.model.set("Hostel", 0.9, "Medium", 0.9)
    code = submit(client, world)["complaint_id"]
    assert review(client, world, "authority", code, action="resolve", remarks="Done.").status_code == 200
    for body in ({"action": "accept"}, {"action": "override", "priority": "High"},
                 {"action": "reroute", "target_user_id": world.users["authority_cse"].id},
                 {"action": "resolve", "remarks": "Again."}):
        assert review(client, world, "authority", code, **body).status_code == 409, body
    assert client.post(f"{CONCERNS}/{code}/simulate_breach", headers=world.h("admin")).status_code == 409
    final = client.get(f"{CONCERNS}/{code}", headers=world.h("student")).json()
    assert final["status"] == "RESOLVED"


def test_records_survive_an_application_restart(app, client, settings, world):
    """A fresh application instance on the same database sees every complaint, its AI
    output, its human decision and its full audit trail."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    world.model.set("Hostel", 0.9, "High", 0.9)
    code = submit(client, world)["complaint_id"]
    review(client, world, "authority", code, action="override", priority="Medium", remarks="Kept after restart.")
    before = client.get(f"{CONCERNS}/{code}", headers=world.h("student")).json()

    restarted = create_app(settings)  # new engine, new sessions, same database
    restarted.state.triage_model = world.model
    try:
        with TestClient(restarted) as second:
            after = second.get(f"{CONCERNS}/{code}", headers=world.h("student")).json()
    finally:
        restarted.state.engine.dispose()
    for key in ("status", "category", "priority", "decision_source", "ai", "human_decision", "events", "assigned_to"):
        assert after[key] == before[key], key
