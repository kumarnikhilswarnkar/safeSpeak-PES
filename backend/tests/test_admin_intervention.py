"""Administrator intervention for complaints whose escalation chain is exhausted, and the
related fix: a human-chosen assignee (reroute or intervention) is kept when the review is
confirmed without a category change."""
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.timeutil import utcnow
from app.models import AIPrediction, Complaint, ComplaintEvent, TATRule
from app.services import complaint_service
from tests.workflow_fixtures import CONCERNS, actions, submit, world  # noqa: F401

HOSTEL = "The hostel water supply has been off for two days on the second floor."


def _expire_deadline(db, code):
    c = db.scalar(select(Complaint).where(Complaint.complaint_code == code))
    c.deadline_at = utcnow() - timedelta(minutes=5)
    db.commit()


@pytest.fixture
def exhausted(client, db, world):
    """A High-priority Hostel complaint (human review required) escalated through the whole
    default chain (MCA L1 -> Dean -> Director) and then exhausted."""
    world.model.set("Hostel", 0.9, "High", 0.9)
    body = submit(client, world, "student", HOSTEL)
    code = body["complaint_id"]
    assert body["status"] == "PENDING_REVIEW" and body["review_reasons"] == ["HIGH_SEVERITY"]
    for _ in range(3):
        _expire_deadline(db, code)
        complaint_service.escalate_overdue(db, None)
    detail = client.get(f"{CONCERNS}/{code}", headers=world.h("admin")).json()
    assert detail["breached_at_top"] is True and detail["assigned_to"]["id"] == world.users["director"].id
    assert [h["result"] for h in detail["escalation"]["history"]] == ["escalated", "escalated", "exhausted"]
    return detail


def reassign(client, world, code, who="admin", **overrides):
    body = {"target_user_id": world.users["authority_cse"].id, "reason": "CSE warden office handles this block.",
            "expected_assignee_id": world.users["director"].id, **overrides}
    return client.post(f"{CONCERNS}/{code}/admin-reassign", json=body, headers=world.h(who))


def test_escalation_levels_are_chain_steps_with_correct_assignees(exhausted, world):
    # Steps 1 -> 2 -> 3 of the default chain; step 2 is the Dean (authority level 3), step 3 the Director (level 4).
    h = exhausted["escalation"]["history"]
    assert (h[0]["from_level"], h[0]["to_level"], h[0]["to_assignee"]["id"]) == (1, 2, world.users["dean"].id)
    assert (h[1]["from_level"], h[1]["to_level"], h[1]["to_assignee"]["id"]) == (2, 3, world.users["director"].id)
    assert h[0]["to_assignee"]["authority_level"] == 3 and h[1]["to_assignee"]["authority_level"] == 4
    assert exhausted["escalation_level"] == 3


def test_options_list_eligible_authorities_and_rule_based_tat(client, db, world, exhausted):
    body = client.get(f"{CONCERNS}/{exhausted['complaint_id']}/intervention-options", headers=world.h("admin")).json()
    ids = {c["id"] for c in body["candidates"]}
    assert world.users["director"].id not in ids and world.users["student"].id not in ids
    assert {world.users["authority"].id, world.users["authority_cse"].id, world.users["dean"].id} <= ids
    rule = db.get(TATRule, body["tat"]["rule_id"])
    assert body["new_stage"] == "REVIEW" and rule.stage == "REVIEW" and body["tat"]["hours"] == rule.tat_hours
    assert {d["code"] for d in body["departments"]} >= {"MCA", "CSE"}


def test_admin_reassigns_exhausted_complaint(client, db, world, exhausted):
    code = exhausted["complaint_id"]
    ai_before = db.scalar(select(AIPrediction).join(Complaint).where(Complaint.complaint_code == code))
    ai_snapshot = (ai_before.category, ai_before.priority, ai_before.confidence)
    events_before = exhausted["events"]

    r = reassign(client, world, code)
    assert r.status_code == 200, r.text
    after = r.json()

    target = world.users["authority_cse"]
    assert after["assigned_to"]["id"] == target.id
    assert after["handling_department"]["code"] == "CSE"
    assert after["status"] == "PENDING_REVIEW"  # never resolved by reassignment; review still required
    assert after["breached_at_top"] is False and after["tat"]["state"] == "ON_TRACK"
    assert after["tat"]["stage"] == "REVIEW"

    # Append-only: every earlier event is unchanged, one intervention event is added.
    assert after["events"][: len(events_before)] == events_before
    event = after["events"][-1]
    assert event["action"] == "admin_reassigned" and event["actor"]["id"] == world.users["admin"].id
    assert event["remarks"] == "CSE warden office handles this block."
    assert event["previous_value"]["assigned_user"]["id"] == world.users["director"].id
    assert event["previous_value"]["breached_at_top"] is True
    assert event["new_value"]["assigned_user"]["id"] == target.id
    assert event["new_value"]["deadline_at"] != event["previous_value"]["deadline_at"]
    step = after["escalation"]["history"][-1]
    assert step["result"] == "admin_reassigned" and step["reason"] == "CSE warden office handles this block."

    # The original AI recommendation is untouched.
    db.expire_all()
    ai_after = db.scalar(select(AIPrediction).join(Complaint).where(Complaint.complaint_code == code))
    assert (ai_after.category, ai_after.priority, ai_after.confidence) == ai_snapshot

    # Student sees the new assignment; the new authority has it in their review queue and is notified.
    mine = client.get(f"{CONCERNS}/{code}", headers=world.h("student")).json()
    assert mine["assigned_to"]["id"] == target.id and mine["status"] == "PENDING_REVIEW"
    queue = client.get(f"{CONCERNS}/pending-triage", headers=world.h("authority_cse")).json()
    assert code in [c["complaint_id"] for c in queue]
    notes = client.get("/api/v1/notifications", headers=world.h("authority_cse")).json()
    assert any(n["complaint_id"] == code and n["action"] == "admin_reassigned" for n in notes)
    student_notes = client.get("/api/v1/notifications", headers=world.h("student")).json()
    assert any(n["complaint_id"] == code and n["action"] == "admin_reassigned" for n in student_notes)
    # The previous (top) authority no longer has it.
    assert client.get(f"{CONCERNS}/{code}", headers=world.h("director")).status_code == 404
    # No longer on the admin attention list.
    overview = client.get("/api/v1/analytics/overview", headers=world.h("admin")).json()
    assert code not in [a["complaint_id"] for a in overview["attention"]]
    assert overview["escalations"]["admin_interventions"] == 1


def test_new_authority_review_keeps_the_admin_chosen_assignee(client, world, exhausted):
    code = exhausted["complaint_id"]
    assert reassign(client, world, code).status_code == 200
    r = client.post(f"{CONCERNS}/{code}/review", json={"action": "accept"}, headers=world.h("authority_cse"))
    assert r.status_code == 200
    body = r.json()
    assert body["assigned_to"]["id"] == world.users["authority_cse"].id
    assert body["status"] == "ASSIGNED" and body["tat"]["stage"] == "RESOLUTION"
    assert body["decision_source"] == "HUMAN_ACCEPTED"
    assert body["events"][-1]["new_value"]["kept_manual_assignment"] == "admin_reassigned"


def test_duplicate_or_stale_reassignment_is_refused(client, db, world, exhausted):
    code = exhausted["complaint_id"]
    assert reassign(client, world, code).status_code == 200
    # The same request again: the chain is no longer exhausted -> conflict, no second event.
    assert reassign(client, world, code).status_code == 409
    assert reassign(client, world, code, expected_assignee_id=world.users["authority_cse"].id,
                    target_user_id=world.users["dean"].id).status_code == 409
    n = db.query(ComplaintEvent).join(Complaint).filter(
        Complaint.complaint_code == code, ComplaintEvent.action == "admin_reassigned").count()
    assert n == 1
    assert actions(client.get(f"{CONCERNS}/{code}", headers=world.h("admin")).json()).count("admin_reassigned") == 1


def test_stale_view_is_refused(client, world, exhausted):
    r = reassign(client, world, exhausted["complaint_id"], expected_assignee_id=world.users["dean"].id)
    assert r.status_code == 409 and "changed since you opened it" in r.json()["detail"]


@pytest.mark.parametrize("overrides,expected", [
    ({"reason": "too short"}, 422),
    ({"reason": "          "}, 422),
    ({"target_user_id": None}, 422),
])
def test_reason_and_target_are_validated(client, world, exhausted, overrides, expected):
    assert reassign(client, world, exhausted["complaint_id"], **overrides).status_code == expected


@pytest.mark.parametrize("target", ["student", "director", "viewer", "admin"])
def test_target_must_be_another_active_authority(client, world, exhausted, target):
    r = reassign(client, world, exhausted["complaint_id"], target_user_id=world.users[target].id)
    assert r.status_code == 422


def test_inactive_authority_cannot_be_chosen(client, db, world, exhausted):
    world.users["authority_cse"].is_active = False
    db.commit()
    assert reassign(client, world, exhausted["complaint_id"]).status_code == 422


@pytest.mark.parametrize("who", ["student", "teaching", "authority", "dean", "director", "viewer"])
def test_only_admin_can_intervene(client, world, exhausted, who):
    code = exhausted["complaint_id"]
    assert client.get(f"{CONCERNS}/{code}/intervention-options", headers=world.h(who)).status_code == 403
    assert reassign(client, world, code, who=who).status_code == 403
    assert client.post(f"{CONCERNS}/{code}/admin-reassign", json={}).status_code == 401


def test_intervention_requires_exhausted_open_complaint(client, world):
    world.model.set("Hostel", 0.9, "Medium", 0.9)
    code = submit(client, world, "student", HOSTEL)["complaint_id"]
    assert client.get(f"{CONCERNS}/{code}/intervention-options", headers=world.h("admin")).status_code == 409
    assert reassign(client, world, code, expected_assignee_id=world.users["authority"].id).status_code == 409


def test_resolved_complaint_cannot_be_reassigned(client, db, world, exhausted):
    code = exhausted["complaint_id"]
    for action in ({"action": "accept"}, {"action": "resolve", "remarks": "Water restored."}):
        assert client.post(f"{CONCERNS}/{code}/review", json=action, headers=world.h("director")).status_code == 200
    c = db.scalar(select(Complaint).where(Complaint.complaint_code == code))
    assert c.status == "RESOLVED"
    r = reassign(client, world, code)
    assert r.status_code == 409


def test_reassigned_complaint_continues_and_can_exhaust_again(client, db, world, exhausted):
    code = exhausted["complaint_id"]
    assert reassign(client, world, code).status_code == 200
    _expire_deadline(db, code)
    outcomes = complaint_service.escalate_overdue(db, None)
    assert [(o.complaint_code, o.result) for o in outcomes] == [(code, "exhausted")]
    detail = client.get(f"{CONCERNS}/{code}", headers=world.h("admin")).json()
    assert detail["breached_at_top"] is True and detail["assigned_to"]["id"] == world.users["authority_cse"].id
    # Repeated checks do not duplicate the exhaustion.
    assert complaint_service.escalate_overdue(db, None) == []


def test_reroute_then_accept_keeps_the_rerouted_authority(client, world):
    """Regression: accepting a rerouted pending complaint used to re-route it by the chain,
    sending it back to the original reviewer."""
    world.model.set("Hostel", 0.4, "Medium", 0.9)
    code = submit(client, world)["complaint_id"]
    target = world.users["authority_cse"].id
    r = client.post(f"{CONCERNS}/{code}/review", json={"action": "reroute", "target_user_id": target, "remarks": "CSE"},
                    headers=world.h("authority"))
    assert r.json()["assigned_to"]["id"] == target
    r = client.post(f"{CONCERNS}/{code}/review", json={"action": "accept"}, headers=world.h("authority_cse"))
    assert r.status_code == 200 and r.json()["assigned_to"]["id"] == target and r.json()["status"] == "ASSIGNED"


def test_category_change_after_reroute_routes_by_the_new_category(client, world):
    world.model.set("Hostel", 0.4, "Medium", 0.9)
    code = submit(client, world)["complaint_id"]
    client.post(f"{CONCERNS}/{code}/review", json={"action": "reroute", "target_user_id": world.users["authority_cse"].id,
                                                   "remarks": "CSE"}, headers=world.h("authority"))
    r = client.post(f"{CONCERNS}/{code}/review", json={"action": "override", "category": "Safety and welfare"},
                    headers=world.h("authority_cse"))
    assert r.status_code == 200
    # Category changed: routed by the Safety chain (step 1 = complainant's department, MCA).
    assert r.json()["assigned_to"]["id"] == world.users["authority"].id
