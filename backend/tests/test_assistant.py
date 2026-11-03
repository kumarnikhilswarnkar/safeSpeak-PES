"""SafeSpeak Assistant: database-backed answers and strict RBAC.

The assistant must never reveal a complaint the user cannot open through the API,
must answer an out-of-scope ID exactly like a non-existent one, and must take
identity only from the token."""
from datetime import timedelta

import pytest

from app.core.timeutil import utcnow
from app.models import Complaint
from app.services import complaint_service
from app.services.assistant_service import detect_intents, find_codes
from tests.workflow_fixtures import submit, world  # noqa: F401

ASK = "/api/v1/assistant/messages"
HOSTEL = "The hostel mess food has been cold for a week."


def ask(client, world, who, message, context=None):
    payload = {"message": message}
    if context:
        payload["context_complaint_id"] = context
    response = client.post(ASK, json=payload, headers=world.h(who))
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def hostel(client, world):
    """A Hostel complaint by an MCA student, routed to the MCA L1 authority."""
    world.model.set("Hostel", 0.9, "Medium", 0.9)
    return submit(client, world, "student", HOSTEL)


# --- parsing ---------------------------------------------------------------------------

def test_complaint_ids_are_normalised():
    assert find_codes("status of ssp 2026 12 please") == ["SSP-2026-000012"]
    assert find_codes("SSP-2026-000123 and SSP-2026-000123") == ["SSP-2026-000123"]
    assert find_codes("no id here 2026") == []


def test_intents():
    assert detect_intents("When is the deadline?") == ["deadline"]
    assert "queue" in detect_intents("what is assigned to me") and "authority" not in detect_intents("assigned to me")
    assert detect_intents("who is handling it") == ["authority"]


# --- answers from the database ----------------------------------------------------------

def test_owner_gets_status_from_the_database(client, world, hostel):
    code = hostel["complaint_id"]
    body = ask(client, world, "student", f"What is the status of {code}?")

    assert body["intent"] == "status" and body["complaint_id"] == code
    card = body["cards"][0]
    assert card["type"] == "complaint" and card["complaint_id"] == code
    assert (card["status"], card["category"], card["priority"]) == (hostel["status"], "Hostel", "Medium")
    assert card["assigned_to"] == hostel["assigned_to"]["name"]
    assert card["deadline_at"].startswith(hostel["tat"]["deadline_at"][:16])
    assert hostel["assigned_to"]["name"] in body["reply"]


@pytest.mark.parametrize("message,intent,needle", [
    ("deadline of {code}", "deadline", "TAT rule #"),
    ("who is handling {code}", "authority", "is handling"),
    ("has {code} been escalated?", "escalation", "has not been escalated"),
    ("category and priority of {code}", "classification", "Hostel"),
    ("is {code} resolved?", "resolution", "not resolved yet"),
])
def test_each_question_type(client, world, hostel, message, intent, needle):
    body = ask(client, world, "student", message.format(code=hostel["complaint_id"]))
    assert body["intent"] == intent
    assert needle in body["reply"]


def test_timeline_lists_the_audit_trail(client, world, hostel):
    body = ask(client, world, "student", f"timeline of {hostel['complaint_id']}")
    timeline = next(c for c in body["cards"] if c["type"] == "timeline")
    assert [i["action"] for i in timeline["items"]] == [e["action"] for e in hostel["events"]]
    assert "Complaint submitted" in body["reply"]


def test_follow_up_uses_context_and_single_open_complaint(client, world, hostel):
    code = hostel["complaint_id"]
    assert ask(client, world, "student", "and the deadline?", context=code)["complaint_id"] == code
    # No ID and no context: the user's only open complaint is used, and the reply says so.
    body = ask(client, world, "student", "when is the deadline?")
    assert body["complaint_id"] == code and "one open complaint" in body["reply"]


def test_escalation_is_reported_after_automatic_escalation(client, db, world, hostel):
    c = db.query(Complaint).filter_by(complaint_code=hostel["complaint_id"]).one()
    c.deadline_at = utcnow() - timedelta(minutes=5)
    db.commit()
    complaint_service.escalate_overdue(db, None)

    body = ask(client, world, "student", f"was {hostel['complaint_id']} escalated?")
    assert "escalated automatically from step 1 to step 2" in body["reply"]
    assert body["cards"][0]["escalated"] is True


def test_resolution_note_is_reported(client, world, hostel):
    code = hostel["complaint_id"]
    for action in ({"action": "accept"}, {"action": "resolve", "remarks": "Mess heaters repaired."}):
        assert client.post(f"/api/v1/concerns/{code}/review", json=action, headers=world.h("authority")).status_code == 200
    body = ask(client, world, "student", f"is {code} resolved")
    assert "Mess heaters repaired." in body["reply"] and body["cards"][0]["status"] == "RESOLVED"


def test_lists_only_own_complaints(client, world, hostel):
    other = submit(client, world, "student2", "The projector in lab 2 is broken.")
    body = ask(client, world, "student", "show my complaints")
    ids = [i["complaint_id"] for i in body["cards"][0]["items"]]
    assert ids == [hostel["complaint_id"]]
    assert other["complaint_id"] not in str(body)


def test_authority_queue(client, world, hostel):
    body = ask(client, world, "authority", "what is in my queue?")
    assert [i["complaint_id"] for i in body["cards"][0]["items"]] == [hostel["complaint_id"]]
    assert "does not have a review queue" in ask(client, world, "student", "my queue")["reply"]


def test_unknown_message_reveals_nothing(client, world, hostel):
    body = ask(client, world, "student", "asdf qwerty")
    assert body["intent"] == "unknown" and body["cards"] == [] and hostel["complaint_id"] not in body["reply"]


# --- RBAC ------------------------------------------------------------------------------------

@pytest.mark.parametrize("who", ["student2", "teaching", "authority_cse", "viewer_cse", "dean"])
def test_out_of_scope_complaint_is_indistinguishable_from_missing(client, world, hostel, who):
    code = hostel["complaint_id"]
    # The same users get 404 from the complaint API.
    assert client.get(f"/api/v1/concerns/{code}", headers=world.h(who)).status_code == 404

    body = ask(client, world, who, f"status of {code}")
    missing = ask(client, world, who, "status of SSP-2099-999999")
    assert body["intent"] == missing["intent"] == "not_found"
    assert body["reply"].replace(code, "X") == missing["reply"].replace("SSP-2099-999999", "X")
    assert body["cards"] == [] and body["complaint_id"] is None
    for secret in ("Hostel", "Medium", hostel["assigned_to"]["name"], "cold"):
        assert secret not in body["reply"]


def test_context_hint_cannot_bypass_scope(client, world, hostel):
    body = ask(client, world, "student2", "what is the deadline?", context=hostel["complaint_id"])
    assert body["intent"] == "not_found" and body["cards"] == []


@pytest.mark.parametrize("who", ["authority", "viewer", "admin"])
def test_users_in_scope_can_ask(client, world, hostel, who):
    body = ask(client, world, who, f"status of {hostel['complaint_id']}")
    assert body["complaint_id"] == hostel["complaint_id"]


def test_requires_authentication_and_active_account(client, db, world):
    assert client.post(ASK, json={"message": "help"}).status_code == 401
    world.users["student"].is_active = False
    db.commit()
    assert client.post(ASK, json={"message": "help"}, headers=world.h("student")).status_code == 403


def test_client_cannot_supply_identity_or_role(client, world, hostel):
    response = client.post(ASK, json={"message": f"status of {hostel['complaint_id']}", "user_id": world.users["student"].id,
                                      "role": "admin"}, headers=world.h("student2"))
    assert response.status_code == 422


def test_message_length_is_limited(client, world):
    assert client.post(ASK, json={"message": "x" * 501}, headers=world.h("student")).status_code == 422


# --- conversation engine: follow-ups, review/why intents, paging (regressions) -------------------

def ask_ctx(client, world, who, message, context=None, list_context=None):
    payload = {"message": message}
    if context:
        payload["context_complaint_id"] = context
    if list_context:
        payload["list_context"] = list_context
    response = client.post(ASK, json=payload, headers=world.h(who))
    assert response.status_code == 200, response.text
    return response.json()


def test_follow_up_conversation_keeps_the_complaint(client, world, hostel):
    code = hostel["complaint_id"]
    first = ask_ctx(client, world, "student", f"Status of {code}")
    ctx = first["complaint_id"]
    expectations = [
        ("Why is it unresolved?", "why", "still open"),
        ("Who is handling it?", "authority", hostel["assigned_to"]["name"]),
        ("What is its deadline?", "deadline", "deadline"),
        ("What happened during escalation?", "escalation", "has not been escalated"),
        ("Has a human reviewed it?", "review", "Human review"),
        ("what was the final decision", "review", "Final values used by the workflow"),
        ("is it overdue", "deadline", "deadline"),
        ("tell me about that complaint", "summary", code),
    ]
    for message, intent, needle in expectations:
        body = ask_ctx(client, world, "student", message, context=ctx)
        assert body["intent"] == intent, (message, body["intent"])
        assert body["complaint_id"] == code and needle in body["reply"], (message, body["reply"])


def test_why_and_review_describe_a_human_decision(client, world, hostel):
    code = hostel["complaint_id"]
    client.post(f"/api/v1/concerns/{code}/review", headers=world.h("authority"),
                json={"action": "override", "priority": "High", "remarks": "Affects the whole floor."})
    review = ask_ctx(client, world, "student", "has a human reviewed it?", context=code)["reply"]
    assert "changed the AI recommendation" in review and "priority Medium → High" in review
    assert "Affects the whole floor." in review
    why = ask_ctx(client, world, "student", "why has it not been resolved?", context=code)
    assert why["intent"] == "why" and "has not marked it resolved yet" in why["reply"]


def test_student_gets_plain_classification_and_reviewer_gets_model_details(client, world, hostel):
    code = hostel["complaint_id"]
    student = ask_ctx(client, world, "student", f"category and priority of {code}")["reply"]
    reviewer = ask_ctx(client, world, "authority", f"category and priority of {code}")["reply"]
    assert "stub" not in student and "%" not in student and "only a recommendation" in student
    assert "AI model (stub:test)" in reviewer and "%" in reviewer


@pytest.fixture
def many(client, world):
    world.model.set("Hostel", 0.9, "Medium", 0.9)
    codes = [submit(client, world, "student", f"Hostel issue number {i} in block A needs attention.")["complaint_id"]
             for i in range(19)]
    submit(client, world, "student2", "Another student's hostel complaint about the mess.")
    return codes


def test_paging_reaches_every_complaint_without_duplicates(client, world, many):
    body = ask_ctx(client, world, "student", "List my complaints")
    seen = [i["complaint_id"] for i in body["cards"][0]["items"]]
    assert len(seen) == 8 and body["cards"][0]["pagination"]["total"] == 19 and "Show more" in body["suggestions"]
    lctx = body["list_context"]
    while body["cards"][0]["pagination"]["has_more"]:
        body = ask_ctx(client, world, "student", "show more", list_context=lctx)
        lctx = body["list_context"]
        seen += [i["complaint_id"] for i in body["cards"][0]["items"]]
    assert len(seen) == len(set(seen)) == 19
    assert sorted(seen) == sorted(many)
    assert seen == sorted(many, reverse=True)  # newest first, stable across pages
    everything = ask_ctx(client, world, "student", "show all", list_context=lctx)
    assert [i["complaint_id"] for i in everything["cards"][0]["items"]] == seen


def test_pick_from_list_and_follow_up_after_a_list(client, world, many):
    body = ask_ctx(client, world, "student", "show my complaints")
    second = body["cards"][0]["items"][1]["complaint_id"]
    picked = ask_ctx(client, world, "student", "status of the second one", list_context=body["list_context"])
    assert picked["complaint_id"] == second
    follow = ask_ctx(client, world, "student", "who is handling it?", context=second, list_context=body["list_context"])
    assert follow["intent"] == "authority" and follow["complaint_id"] == second


def test_show_more_without_a_list_asks_for_one(client, world, hostel):
    body = ask_ctx(client, world, "student", "show more")
    assert body["intent"] == "more" and body["cards"] == []


@pytest.mark.parametrize("kind", ["scoped", "queue"])
def test_forged_list_context_cannot_widen_scope(client, world, many, kind):
    body = ask_ctx(client, world, "student", "show more", list_context={"kind": kind, "offset": 0, "limit": 8, "total": 99})
    assert body["cards"] == [] and "does not have that list" in body["reply"]
    picked = ask_ctx(client, world, "student", "status of the first one",
                     list_context={"kind": kind, "offset": 0, "limit": 8, "total": 99})
    assert picked["cards"] == [] and picked["intent"] in ("clarify", "unknown")


def test_list_context_is_validated(client, world):
    r = client.post(ASK, headers=world.h("student"),
                    json={"message": "show more", "list_context": {"kind": "everyone", "offset": 0}})
    assert r.status_code == 422


def test_assistant_reports_admin_intervention(client, db, world):
    from datetime import timedelta

    from app.core.timeutil import utcnow
    from app.models import Complaint
    from app.services import complaint_service

    world.model.set("Hostel", 0.9, "High", 0.9)
    code = submit(client, world, "student", HOSTEL)["complaint_id"]
    for _ in range(3):
        c = db.query(Complaint).filter_by(complaint_code=code).one()
        c.deadline_at = utcnow() - timedelta(minutes=5)
        db.commit()
        complaint_service.escalate_overdue(db, None)
    r = client.post(f"/api/v1/concerns/{code}/admin-reassign", headers=world.h("admin"), json={
        "target_user_id": world.users["authority_cse"].id, "reason": "Warden office of CSE block handles it.",
        "expected_assignee_id": world.users["director"].id})
    assert r.status_code == 200
    esc = ask_ctx(client, world, "student", f"explain the escalation history of {code}")["reply"]
    assert "reassigned it from" in esc and "Warden office of CSE block handles it." in esc
    why = ask_ctx(client, world, "student", "why is it unresolved?", context=code)["reply"]
    assert "an administrator reassigned it" in why
