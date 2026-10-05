"""Submission, AI triage, confidence check, TAT and routing."""
import re
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models import AIPrediction, Complaint, ComplaintEvent, TATRule
from tests.conftest import bearer
from tests.workflow_fixtures import CONCERNS, actions, submit, world  # noqa: F401

CODE = re.compile(r"^SSP-\d{4}-\d{6}$")


def hours_between(start: str, end: str) -> float:
    return (datetime.fromisoformat(end) - datetime.fromisoformat(start)) / timedelta(hours=1)


def test_authenticated_student_can_submit_and_complaint_is_stored(client, db, world):
    body = submit(client, world)

    assert CODE.match(body["complaint_id"])
    stored = db.scalar(select(Complaint).where(Complaint.complaint_code == body["complaint_id"]))
    assert stored is not None
    assert stored.complainant_id == world.users["student"].id
    assert stored.description == "The projector in lab 3 has not worked for two weeks."
    assert body["complainant"]["id"] == world.users["student"].id


@pytest.mark.parametrize("who", ["teaching", "authority", "dean"])
def test_staff_and_authorities_can_also_submit(client, world, who):
    body = submit(client, world, who)
    assert body["complainant"]["role"] == world.users[who].role


def test_unauthenticated_user_cannot_submit(client, world):
    response = client.post(CONCERNS, json={"description": "Something is broken in the lab."})
    assert response.status_code == 401


@pytest.mark.parametrize("who", ["viewer", "admin"])
def test_roles_without_submit_permission_are_refused(client, world, who):
    response = client.post(CONCERNS, json={"description": "Something is broken in the lab."}, headers=world.h(who))
    assert response.status_code == 403


@pytest.mark.parametrize(
    "forged",
    [
        {"user_id": 999},
        {"complainant_id": 1},
        {"role": "admin"},
        {"status": "RESOLVED"},
        {"priority": "Low"},
        {"complaint_id": "SSP-2026-999999"},
    ],
)
def test_client_cannot_supply_identity_or_workflow_fields(client, world, forged):
    payload = {"description": "Something is broken in the lab.", **forged}
    assert client.post(CONCERNS, json=payload, headers=world.h("student")).status_code == 422


@pytest.mark.parametrize("description", ["", "short", "         "])
def test_description_is_validated(client, world, description):
    assert client.post(CONCERNS, json={"description": description}, headers=world.h("student")).status_code == 422


def test_complaint_ids_are_generated_server_side_and_unique(client, world):
    codes = [submit(client, world)["complaint_id"] for _ in range(5)]

    assert len(set(codes)) == 5
    numbers = [int(code.rsplit("-", 1)[1]) for code in codes]
    assert numbers == list(range(numbers[0], numbers[0] + 5))


def test_ai_recommendation_is_returned_and_stored_separately(client, db, world):
    world.model.set("Infrastructure and facilities", 0.81, "Medium", 0.66)

    body = submit(client, world)

    assert body["ai"]["category"] == "Infrastructure and facilities"
    assert body["ai"]["priority"] == "Medium"
    assert body["ai"]["category_confidence"] == 0.81
    assert body["ai"]["priority_confidence"] == 0.66
    assert body["ai"]["confidence"] == 0.66
    assert body["ai"]["model"] == "stub:test"
    prediction = db.scalar(select(AIPrediction).join(Complaint).where(Complaint.complaint_code == body["complaint_id"]))
    assert prediction.category_confidence == 0.81


def test_confident_routine_complaint_follows_normal_workflow(client, world):
    world.model.set("Hostel", 0.9, "Medium", 0.8)

    body = submit(client, world)

    assert body["status"] == "ASSIGNED"
    assert body["needs_review"] is False
    assert body["decision_source"] == "AI_AUTO"
    assert body["assigned_to"]["id"] == world.users["authority"].id
    assert body["escalation_level"] == 1
    assert body["tat"]["stage"] == "RESOLUTION"
    assert hours_between(body["tat"]["started_at"], body["tat"]["deadline_at"]) == pytest.approx(72)
    assert actions(body) == ["complaint_created", "ai_triaged", "assigned"]


def test_low_confidence_complaint_enters_human_review(client, world):
    world.model.set("Other", 0.21, "Medium", 0.7)

    body = submit(client, world)

    assert body["status"] == "PENDING_REVIEW"
    assert body["needs_review"] is True
    assert body["review_reasons"] == ["LOW_CATEGORY_CONFIDENCE"]
    assert body["decision_source"] == "AI_PENDING_REVIEW"
    assert body["ai"]["threshold"] == 0.5
    assert body["ai"]["threshold_source"] == "CONFIG"
    # Review TAT: the sample REVIEW rule for Medium is 12 hours.
    assert body["tat"]["stage"] == "REVIEW"
    assert hours_between(body["tat"]["started_at"], body["tat"]["deadline_at"]) == pytest.approx(12)
    assert "sent_to_human_review" in actions(body)

    queue = client.get(f"{CONCERNS}/pending-triage", headers=world.h("authority")).json()
    assert [c["complaint_id"] for c in queue] == [body["complaint_id"]]


@pytest.mark.parametrize("priority", ["High", "Critical"])
def test_high_severity_requires_review_even_when_confident(client, world, priority):
    world.model.set("Hostel", 0.95, priority, 0.95)

    body = submit(client, world)

    assert body["status"] == "PENDING_REVIEW"
    assert body["review_reasons"] == ["HIGH_SEVERITY"]


def test_deadline_comes_from_most_specific_tat_rule(client, db, world):
    # Sample rule "Infrastructure and facilities + Medium = 48 h" beats "Medium at level 1 = 72 h".
    world.model.set("Infrastructure and facilities", 0.9, "Medium", 0.9)

    body = submit(client, world)

    rule = db.get(TATRule, body["tat"]["rule_id"])
    assert (rule.category, rule.priority, rule.tat_hours) == ("Infrastructure and facilities", "Medium", 48)
    assert hours_between(body["tat"]["started_at"], body["tat"]["deadline_at"]) == pytest.approx(48)
    assert body["tat"]["state"] == "ON_TRACK"


def test_missing_tat_rule_is_an_explicit_error_and_nothing_is_stored(client, db, world):
    db.query(TATRule).filter(TATRule.stage == "RESOLUTION", TATRule.priority == "Low").update({"is_active": False})
    db.commit()
    world.model.set("Hostel", 0.9, "Low", 0.9)

    response = client.post(CONCERNS, json={"description": "Dustbins are needed near the library."}, headers=world.h("student"))

    assert response.status_code == 503
    assert "No TAT rule" in response.json()["detail"]
    assert db.scalar(select(func.count()).select_from(Complaint)) == 0


def test_unavailable_level_is_skipped_and_audited(client, db, world):
    world.users["authority"].is_active = False
    db.commit()
    world.model.set("Hostel", 0.9, "Medium", 0.9)

    body = submit(client, world)

    assert body["assigned_to"]["id"] == world.users["dean"].id
    assert body["escalation_level"] == 2
    assert "routing_levels_skipped" in actions(body)


def test_authority_never_handles_own_complaint(client, world):
    world.model.set("Hostel", 0.9, "Medium", 0.9)

    body = submit(client, world, "authority")

    assert body["assigned_to"]["id"] != world.users["authority"].id
    assert body["assigned_to"]["id"] == world.users["dean"].id


def test_submission_events_are_recorded_with_server_side_actor(client, db, world):
    body = submit(client, world)

    created = db.scalar(select(ComplaintEvent).where(ComplaintEvent.action == "complaint_created"))
    assert created.actor_user_id == world.users["student"].id
    assert created.actor_role == "student"
    triaged = db.scalar(select(ComplaintEvent).where(ComplaintEvent.action == "ai_triaged"))
    assert triaged.actor_user_id is None  # system
    assert body["events"][0]["actor"]["id"] == world.users["student"].id


def test_model_unavailable_refuses_submission(client, app, world):
    app.state.triage_model = None
    response = client.post(CONCERNS, json={"description": "Something is broken in the lab."}, headers=world.h("student"))
    assert response.status_code == 503


def test_token_role_claim_cannot_unlock_submission(client, settings, world):
    from app.core.security import create_access_token

    forged, _ = create_access_token(world.users["viewer"].id, "student", settings)
    response = client.post(CONCERNS, json={"description": "Something is broken in the lab."}, headers=bearer(forged))
    assert response.status_code == 403
