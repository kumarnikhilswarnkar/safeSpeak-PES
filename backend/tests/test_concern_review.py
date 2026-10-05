"""Human review (accept / override / reroute / resolve), authorization and audit."""
import pytest
from sqlalchemy import select

from app.models import AIPrediction, ComplaintEvent, ImmutableRecordError
from tests.workflow_fixtures import CONCERNS, actions, submit, world  # noqa: F401


def review(client, world, who, code, **payload):
    return client.post(f"{CONCERNS}/{code}/review", json=payload, headers=world.h(who))


@pytest.fixture
def pending(client, world) -> dict:
    """A low-confidence complaint waiting for the MCA authority's review."""
    world.model.set("Other", 0.2, "Medium", 0.7)
    return submit(client, world)


@pytest.fixture
def assigned(client, world) -> dict:
    """A confident routine complaint already assigned to the MCA authority."""
    world.model.set("Hostel", 0.9, "Medium", 0.9)
    return submit(client, world)


# --- authorization -------------------------------------------------------------

@pytest.mark.parametrize("who", ["student", "student2", "teaching", "viewer", "admin"])
def test_roles_without_review_permission_cannot_review(client, world, pending, who):
    response = review(client, world, who, pending["complaint_id"], action="accept")
    assert response.status_code == 403


def test_authority_not_assigned_cannot_review(client, world, pending):
    # authority_cse can review in general, but this complaint is not theirs.
    response = review(client, world, "authority_cse", pending["complaint_id"], action="accept")
    assert response.status_code == 404


def test_review_requires_authentication(client, world, pending):
    response = client.post(f"{CONCERNS}/{pending['complaint_id']}/review", json={"action": "accept"})
    assert response.status_code == 401


@pytest.mark.parametrize(
    "forged",
    [{"reviewer_id": 1}, {"actor": "warden-demo"}, {"role": "admin"}, {"user_id": 1}],
)
def test_forged_reviewer_fields_are_rejected(client, world, pending, forged):
    response = review(client, world, "authority", pending["complaint_id"], action="accept", **forged)
    assert response.status_code == 422


def test_unknown_complaint_is_404(client, world):
    assert review(client, world, "authority", "SSP-2026-999999", action="accept").status_code == 404


# --- accept ----------------------------------------------------------------------

def test_reviewer_can_accept_pending_complaint(client, world, pending):
    response = review(client, world, "authority", pending["complaint_id"], action="accept", remarks="Looks right")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ASSIGNED"
    assert body["decision_source"] == "HUMAN_ACCEPTED"
    assert body["tat"]["stage"] == "RESOLUTION"
    accepted = next(e for e in body["events"] if e["action"] == "accepted")
    assert accepted["actor"]["id"] == world.users["authority"].id
    assert accepted["actor_role"] == "department_authority"
    assert accepted["previous_value"]["decision_source"] == "AI_PENDING_REVIEW"
    assert accepted["new_value"]["decision_source"] == "HUMAN_ACCEPTED"
    assert accepted["remarks"] == "Looks right"
    assert actions(body)[-1] == "assigned"


def test_accept_twice_is_a_conflict(client, world, pending):
    review(client, world, "authority", pending["complaint_id"], action="accept")
    assert review(client, world, "authority", pending["complaint_id"], action="accept").status_code == 409


# --- override --------------------------------------------------------------------

def test_reviewer_can_override_and_ai_prediction_is_unchanged(client, db, world, pending):
    response = review(
        client, world, "authority", pending["complaint_id"],
        action="override", category="Exam", priority="High", remarks="Hall ticket issue",
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["category"], body["priority"]) == ("Exam", "High")
    assert body["decision_source"] == "HUMAN_OVERRIDDEN"
    assert (body["ai"]["category"], body["ai"]["priority"]) == ("Other", "Medium")
    event = next(e for e in body["events"] if e["action"] == "overridden")
    assert event["previous_value"]["category"] == "Other"
    assert event["new_value"] == {"category": "Exam", "priority": "High", "decision_source": "HUMAN_OVERRIDDEN"}


def test_override_of_assigned_complaint_recalculates_deadline(client, world, assigned):
    response = review(client, world, "authority", assigned["complaint_id"], action="override", priority="High")

    body = response.json()
    assert body["tat"]["hours"] == 24  # sample: High at level 1
    assert "deadline_recalculated" in actions(body)


@pytest.mark.parametrize(
    "payload",
    [
        {},  # nothing to change
        {"category": "Other", "priority": "Medium"},  # same as current
        {"category": "Not a category"},
        {"priority": "Urgent"},
    ],
)
def test_override_requires_valid_new_values(client, world, pending, payload):
    response = review(client, world, "authority", pending["complaint_id"], action="override", **payload)
    assert response.status_code == 422


# --- reroute ---------------------------------------------------------------------

def test_reviewer_can_reroute_to_another_authority(client, world, assigned):
    target = world.users["authority_cse"]

    response = review(client, world, "authority", assigned["complaint_id"], action="reroute", target_user_id=target.id)

    assert response.status_code == 200
    body = response.json()
    assert body["assigned_to"]["id"] == target.id
    assert body["handling_department"]["code"] == "CSE"
    event = next(e for e in body["events"] if e["action"] == "rerouted")
    assert event["previous_value"]["assigned_user"]["id"] == world.users["authority"].id
    assert event["new_value"]["assigned_user"]["id"] == target.id
    # The previous reviewer no longer has it; the new one does.
    assert client.get(f"{CONCERNS}/queue", headers=world.h("authority")).json() == []
    assert [c["complaint_id"] for c in client.get(f"{CONCERNS}/queue", headers=world.h("authority_cse")).json()] == [
        assigned["complaint_id"]
    ]


@pytest.mark.parametrize("target", ["student", "viewer", "admin", "authority", "nobody", "inactive_dean"])
def test_reroute_to_invalid_target_is_rejected(client, db, world, assigned, target):
    if target == "inactive_dean":
        world.users["dean"].is_active = False
        db.commit()
        target_id = world.users["dean"].id
    elif target == "nobody":
        target_id = 99999
    else:
        target_id = world.users[target].id

    response = review(client, world, "authority", assigned["complaint_id"], action="reroute", target_user_id=target_id)

    assert response.status_code == 422


def test_reroute_targets_lists_only_valid_authorities(client, world, assigned):
    response = client.get(f"{CONCERNS}/{assigned['complaint_id']}/reroute-targets", headers=world.h("authority"))

    ids = {u["id"] for u in response.json()}
    assert ids == {world.users[k].id for k in ("authority_cse", "dean", "director")}


# --- resolve ---------------------------------------------------------------------

def test_resolve_requires_review_and_a_note(client, world, pending):
    code = pending["complaint_id"]
    assert review(client, world, "authority", code, action="resolve", remarks="Done").status_code == 409

    review(client, world, "authority", code, action="accept")
    assert review(client, world, "authority", code, action="resolve").status_code == 422

    body = review(client, world, "authority", code, action="resolve", remarks="Fixed the issue").json()
    assert body["status"] == "RESOLVED"
    assert body["resolved_at"] is not None
    assert body["tat"]["state"] == "STOPPED"
    assert review(client, world, "authority", code, action="accept").status_code == 409


# --- audit immutability ------------------------------------------------------------

def test_ai_predictions_and_events_cannot_be_modified(client, db, world, pending):
    prediction = db.scalar(select(AIPrediction))
    prediction.category = "Exam"
    with pytest.raises(ImmutableRecordError):
        db.flush()
    db.rollback()

    event = db.scalar(select(ComplaintEvent))
    db.delete(event)
    with pytest.raises(ImmutableRecordError):
        db.flush()
    db.rollback()
