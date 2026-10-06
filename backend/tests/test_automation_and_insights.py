"""Automatic TAT monitor, routing reasons, escalation summary, human decision,
dashboards, notifications, model evidence and the evaluation report."""
import asyncio

import pytest

from app.services.keyword_features import keyword_category, keyword_priority
from app.services.tat_monitor import TatMonitor
from app.services.triage_service import load_triage_model
from tests.workflow_fixtures import CONCERNS, actions, submit, world  # noqa: F401

AUTOMATION = "/api/v1/system/automation"


def breach(client, world, code):
    assert client.post(f"{CONCERNS}/{code}/simulate_breach", headers=world.h("admin")).status_code == 200


def detail(client, world, code, who="admin"):
    response = client.get(f"{CONCERNS}/{code}", headers=world.h(who))
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def assigned(client, world) -> dict:
    world.model.set("Hostel", 0.9, "Medium", 0.9)
    return submit(client, world)


# --- automatic TAT monitor ------------------------------------------------------------

def test_monitor_escalates_overdue_complaint_without_any_user_action(client, app, world, assigned):
    code = assigned["complaint_id"]
    breach(client, world, code)

    run = app.state.tat_monitor.run_once()  # what the background loop calls

    assert run.trigger == "automatic" and run.escalated == [code]
    body = detail(client, world, code)
    escalation = next(e for e in body["events"] if e["action"] == "escalation_triggered")
    assert escalation["actor"] is None  # system actor
    assert escalation["new_value"]["triggered_by"] == "automatic TAT monitor"
    assert body["escalation_level"] == 2 and body["assigned_to"]["id"] == world.users["dean"].id
    step = body["escalation"]["history"][0]
    assert step["automatic"] is True and (step["from_level"], step["to_level"]) == (1, 2)
    assert step["from_assignee"]["id"] == world.users["authority"].id
    assert body["escalation"]["original_deadline_at"] is not None
    assert body["escalation"]["overdue_seconds"] is None  # new deadline is in the future


def test_monitor_never_escalates_the_same_breach_twice(client, app, world, assigned):
    breach(client, world, assigned["complaint_id"])
    monitor = app.state.tat_monitor

    first, second = monitor.run_once(), monitor.run_once()

    assert len(first.escalated) == 1 and second.processed == 0
    events = actions(detail(client, world, assigned["complaint_id"]))
    assert events.count("escalation_triggered") == 1


def test_monitor_marks_top_of_chain_as_exhausted_once(client, app, world, assigned):
    code = assigned["complaint_id"]
    monitor = app.state.tat_monitor
    for _ in range(3):  # L1 -> L2 -> L3 -> exhausted
        breach(client, world, code)
        monitor.run_once()

    body = detail(client, world, code)
    assert body["breached_at_top"] is True and body["escalation_level"] == 3
    assert body["escalation"]["history"][-1]["result"] == "exhausted"
    assert monitor.run_once().processed == 0  # flagged once, never again
    overview = client.get("/api/v1/analytics/overview", headers=world.h("admin")).json()
    assert overview["totals"]["needs_admin_attention"] == 1
    assert overview["attention"][0]["complaint_id"] == code


def test_background_loop_runs_checks_on_its_own(app):
    monitor = TatMonitor(session_factory=app.state.session_factory, interval_seconds=0.02, enabled=True)

    async def scenario():
        monitor.start()
        await asyncio.sleep(0.3)
        assert monitor.running and monitor.next_run_at is not None
        await monitor.stop()

    asyncio.run(scenario())
    assert monitor.total_runs >= 2
    assert all(r.trigger == "automatic" and r.error is None for r in monitor.runs)
    assert not monitor.running


def test_disabled_monitor_does_not_start(app):
    monitor = TatMonitor(session_factory=app.state.session_factory, interval_seconds=1, enabled=False)

    async def scenario():
        monitor.start()
        assert not monitor.running

    asyncio.run(scenario())


def test_automation_status_and_manual_run_permissions(client, world, assigned):
    breach(client, world, assigned["complaint_id"])

    assert client.post(f"{AUTOMATION}/run", headers=world.h("student")).status_code == 403
    assert client.post(f"{AUTOMATION}/run", headers=world.h("authority")).status_code == 403
    ran = client.post(f"{AUTOMATION}/run", headers=world.h("admin"))
    assert ran.status_code == 200
    assert ran.json()["recent_runs"][0]["escalated"] == [assigned["complaint_id"]]

    # Others may see that the monitor works, but not which complaints it touched.
    seen_by_student = client.get(AUTOMATION, headers=world.h("student")).json()
    assert seen_by_student["total_escalated"] == 1
    assert seen_by_student["recent_runs"][0]["escalated"] == []
    assert client.get(AUTOMATION).status_code == 401


def test_manual_endpoint_and_monitor_share_state(client, app, world, assigned):
    breach(client, world, assigned["complaint_id"])
    response = client.post(f"{CONCERNS}/escalate-overdue", headers=world.h("admin"))
    assert response.json()["processed"] == 1
    assert app.state.tat_monitor.last_run.trigger == "manual"


# --- routing reason and human decision ---------------------------------------------------

def test_routing_reason_is_recorded_and_shown(client, world, assigned):
    body = detail(client, world, assigned["complaint_id"], "student")

    routing = body["routing"]
    assert routing["chain_kind"] == "default"
    assert [step["level"] for step in routing["chain"]] == [1, 2, 3]
    decision = routing["last_decision"]
    assert decision["level"] == 1 and decision["target_scope"] == "COMPLAINANT_DEPARTMENT"
    assert decision["rule_label"].startswith("L1")
    assert decision["category"] == "Hostel"


def test_category_chain_is_used_for_its_category(client, world):
    world.model.set("Safety and welfare", 0.9, "Medium", 0.9)
    body = submit(client, world)
    assert body["routing"]["chain_kind"] == "category"
    assert len(body["routing"]["chain"]) == 2


def test_human_decision_keeps_ai_recommendation_separate(client, world):
    world.model.set("Other", 0.1, "Medium", 0.9)
    code = submit(client, world)["complaint_id"]

    response = client.post(
        f"{CONCERNS}/{code}/review",
        json={"action": "override", "category": "Hostel", "priority": "High", "remarks": "Mess hygiene issue"},
        headers=world.h("authority"),
    )

    body = response.json()
    assert body["ai"]["category"] == "Other" and body["ai"]["priority"] == "Medium"
    assert (body["category"], body["priority"]) == ("Hostel", "High")
    decision = body["human_decision"]
    assert decision["action"] == "overridden" and decision["remarks"] == "Mess hygiene issue"
    assert decision["reviewer"]["id"] == world.users["authority"].id
    assert decision["previous"]["category"] == "Other" and decision["new"]["category"] == "Hostel"
    assert body["routing"]["last_decision"]["category"] == "Hostel"


# --- dashboards and notifications ----------------------------------------------------------

def test_overview_is_scoped_to_the_caller(client, world):
    world.model.set("Hostel", 0.9, "Medium", 0.9)
    submit(client, world, "student")
    world.model.set("Exam", 0.1, "Low", 0.9)
    submit(client, world, "student2")

    mine = client.get("/api/v1/analytics/overview", headers=world.h("student")).json()
    everything = client.get("/api/v1/analytics/overview", headers=world.h("admin")).json()
    assigned = client.get("/api/v1/analytics/overview", headers=world.h("authority")).json()

    assert (mine["scope"], mine["totals"]["total"]) == ("own", 1)
    assert (everything["scope"], everything["totals"]["total"]) == ("scope", 2)
    assert (assigned["scope"], assigned["totals"]["total"]) == ("assigned", 2)
    assert everything["totals"]["ai_flagged_for_review"] == 1
    assert everything["rates"]["human_review_rate"] == 0.5
    assert sum(b["count"] for b in everything["confidence_histogram"]) == 2
    assert {c["label"]: c["count"] for c in everything["by_category"]}["Exam"] == 1


def test_notifications_reach_the_right_people(client, world):
    world.model.set("Other", 0.1, "Medium", 0.9)
    code = submit(client, world)["complaint_id"]

    authority_inbox = client.get("/api/v1/notifications", headers=world.h("authority")).json()
    assert any(n["complaint_id"] == code and n["action"] == "sent_to_human_review" for n in authority_inbox)
    assert client.get("/api/v1/notifications", headers=world.h("student2")).json() == []

    client.post(f"{CONCERNS}/{code}/review", json={"action": "accept"}, headers=world.h("authority"))
    student_inbox = client.get("/api/v1/notifications", headers=world.h("student")).json()
    assert any(n["action"] == "accepted" for n in student_inbox)
    # The reviewer is not notified about their own action.
    assert not any(
        n["action"] == "accepted" for n in client.get("/api/v1/notifications", headers=world.h("authority")).json()
    )


# --- model evidence and evaluation ------------------------------------------------------------

def test_real_model_returns_calibrated_confidence_and_evidence(settings):
    model = load_triage_model(settings)
    result = model.predict("The projector in the classroom is broken and the wifi is not working.")

    assert model.calibrated
    assert abs(sum(result.probabilities["category"].values()) - 1) < 0.01
    terms = result.explanation["category_terms"]
    assert terms and all(t["weight"] > 0 for t in terms)
    assert any("projector" in t["term"] or "wifi" in t["term"] for t in terms)
    assert result.explanation["keyword_baseline"]["category"] == "Infrastructure and facilities"


def test_vague_complaint_goes_to_human_review_with_real_model(settings):
    model = load_triage_model(settings)
    result = model.predict("There is some issue, please check.")
    assert result.confidence < model.recommended_threshold


def test_keyword_baseline_rules():
    assert keyword_category("The hostel mess food is cold") == "Hostel"
    assert keyword_category("nothing matches here") == "Other"
    assert keyword_priority("I was harassed near the gate") == "Critical"
    assert keyword_priority("a small suggestion") == "Low"
    assert keyword_priority("the bench is old") == "Medium"


def test_research_report_is_served_with_live_settings(client, world):
    body = client.get("/api/v1/research/evaluation", headers=world.h("viewer")).json()
    assert "keyword_baseline" in body["test"]["category"]
    assert body["selected"]["category"]["model"] in body["test"]["category"]
    assert body["live"]["threshold"] == 0.5  # the test settings' configured threshold
    assert client.get("/api/v1/research/evaluation").status_code == 401


def test_rules_are_readable_configuration(client, world):
    body = client.get("/api/v1/system/rules", headers=world.h("student")).json()
    assert any(r["stage"] == "REVIEW" for r in body["tat_rules"])
    assert {r["category"] for r in body["escalation_rules"]} >= {None, "Safety and welfare"}
    assert client.get("/api/v1/system/rules").status_code == 401
