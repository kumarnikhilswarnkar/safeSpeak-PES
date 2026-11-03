"""Dashboard metric definitions (they answer different questions and must not be confused):

- totals.escalated            = complaints escalated at least once (a complaint counts once)
- escalations.automatic/manual = escalation EVENTS (a complaint escalated twice counts twice)
- totals.ai_flagged_for_review = complaints the AI sent to human review at submission (ever)
- totals.pending_review        = complaints waiting for human review right now
- per_day                      = submissions per day in the display timezone (IST), last 14 days
"""
from datetime import datetime, timedelta

from sqlalchemy import select

from app.core.timeutil import utcnow
from app.models import Complaint
from app.services import complaint_service
from tests.workflow_fixtures import CONCERNS, submit, world  # noqa: F401

OVERVIEW = "/api/v1/analytics/overview"


def _expire(db, code):
    c = db.scalar(select(Complaint).where(Complaint.complaint_code == code))
    c.deadline_at = utcnow() - timedelta(minutes=5)
    db.commit()


def test_escalated_complaints_vs_escalation_events(client, db, world):
    world.model.set("Hostel", 0.9, "Medium", 0.9)
    code = submit(client, world)["complaint_id"]
    for _ in range(2):
        _expire(db, code)
        complaint_service.escalate_overdue(db, None)
    o = client.get(OVERVIEW, headers=world.h("admin")).json()
    assert o["totals"]["escalated"] == 1  # one complaint
    assert o["escalations"]["automatic"] == 2  # two escalation events


def test_flagged_ever_vs_pending_now(client, world):
    world.model.set("Hostel", 0.9, "High", 0.9)  # High -> human review
    code = submit(client, world)["complaint_id"]
    before = client.get(OVERVIEW, headers=world.h("admin")).json()["totals"]
    assert (before["ai_flagged_for_review"], before["pending_review"]) == (1, 1)
    client.post(f"{CONCERNS}/{code}/review", json={"action": "accept"}, headers=world.h("authority"))
    after = client.get(OVERVIEW, headers=world.h("admin")).json()["totals"]
    assert (after["ai_flagged_for_review"], after["pending_review"]) == (1, 0)


def test_submissions_per_day_use_the_display_timezone(client, db, settings, world):
    world.model.set("Hostel", 0.9, "Medium", 0.9)
    code = submit(client, world)["complaint_id"]
    # 01:00 IST today = 19:30 UTC yesterday: it must count on today's IST date.
    today_ist = utcnow().astimezone(settings.tz).date()
    local_1am = datetime(today_ist.year, today_ist.month, today_ist.day, 1, 0, tzinfo=settings.tz)
    c = db.scalar(select(Complaint).where(Complaint.complaint_code == code))
    c.created_at = local_1am
    db.commit()
    o = client.get(OVERVIEW, headers=world.h("admin")).json()
    by_day = {d["date"]: d["count"] for d in o["per_day"]}
    assert len(o["per_day"]) == 14 and by_day[today_ist.isoformat()] == 1
    assert o["latest_submission_at"] is not None
