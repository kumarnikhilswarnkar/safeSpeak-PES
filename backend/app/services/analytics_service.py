"""Dashboard numbers, computed from the live database for the complaints the
current user is allowed to see:

- complainants (student / teaching / non-teaching): their own complaints
- authorities: complaints currently assigned to them
- view-only authorities and administrators: their read-only scope

Volumes are small (a campus prototype), so aggregation is done in Python.
"""
from collections import Counter
from datetime import timedelta
from statistics import mean, median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import AUTHORITY_ROLES, Permission, has_permission
from app.core.taxonomy import CATEGORIES, PRIORITIES
from app.core.timeutil import utcnow
from app.models import OPEN_STATUSES, Complaint, ComplaintEvent, ComplaintStatus, DecisionSource, User
from app.services import complaint_service

CONFIDENCE_BINS = 10


def _scope(db: Session, user: User) -> tuple[str, list[Complaint]]:
    if has_permission(user.role, Permission.VIEW_SCOPED_COMPLAINTS):
        return "scope", complaint_service.list_scoped(db, user)
    if user.role in AUTHORITY_ROLES:
        return "assigned", complaint_service._list(db, Complaint.assigned_user_id == user.id)
    return "own", complaint_service.list_mine(db, user)


def overview(db: Session, user: User, threshold: float | None, model_name: str | None) -> dict:
    scope, complaints = _scope(db, user)
    now = utcnow()
    open_ = [c for c in complaints if c.status in OPEN_STATUSES]
    flagged = [c for c in complaints if c.ai_prediction and c.ai_prediction.flagged_for_review]
    human = [c for c in complaints if c.decision_source in (DecisionSource.HUMAN_ACCEPTED, DecisionSource.HUMAN_OVERRIDDEN)]
    resolved = [c for c in complaints if c.resolved_at is not None]
    resolution_hours = [(c.resolved_at - c.created_at).total_seconds() / 3600 for c in resolved]

    ids = [c.id for c in complaints]
    escalation_events = (
        list(
            db.scalars(
                select(ComplaintEvent).where(
                    ComplaintEvent.complaint_id.in_(ids),
                    ComplaintEvent.action.in_(("escalation_triggered", "escalation_exhausted")),
                )
            )
        )
        if ids
        else []
    )

    bins = [0] * CONFIDENCE_BINS
    for c in complaints:
        if c.ai_prediction:
            bins[min(int(c.ai_prediction.confidence * CONFIDENCE_BINS), CONFIDENCE_BINS - 1)] += 1

    category_changed = sum(1 for c in human if c.ai_prediction and c.category != c.ai_prediction.category)
    priority_changed = sum(1 for c in human if c.ai_prediction and c.priority != c.ai_prediction.priority)

    start = (now - timedelta(days=13)).date()
    per_day = Counter(c.created_at.date() for c in complaints if c.created_at.date() >= start)

    return {
        "scope": scope,
        "generated_at": now.isoformat(),
        "model": model_name,
        "threshold": threshold,
        "totals": {
            "total": len(complaints),
            "open": len(open_),
            "pending_review": sum(1 for c in complaints if c.status == ComplaintStatus.PENDING_REVIEW),
            "resolved": len(resolved),
            "overdue": sum(1 for c in open_ if c.deadline_at < now),
            "escalated": sum(1 for c in complaints if c.escalated),
            "needs_admin_attention": sum(1 for c in open_ if c.breached_at_top),
            "ai_flagged_for_review": len(flagged),
            "auto_routed": len(complaints) - len(flagged),
            "human_decisions": len(human),
        },
        "rates": {
            "human_review_rate": round(len(flagged) / len(complaints), 4) if complaints else None,
            "override_rate": round(
                sum(1 for c in human if c.decision_source == DecisionSource.HUMAN_OVERRIDDEN) / len(human), 4
            )
            if human
            else None,
        },
        "by_category": [{"label": k, "count": sum(1 for c in complaints if c.category == k)} for k in CATEGORIES],
        "by_priority": [{"label": k, "count": sum(1 for c in complaints if c.priority == k)} for k in PRIORITIES],
        "by_status": [
            {"label": s.value, "count": sum(1 for c in complaints if c.status == s)} for s in ComplaintStatus
        ],
        "decision_sources": [
            {"label": d.value, "count": sum(1 for c in complaints if c.decision_source == d)} for d in DecisionSource
        ],
        "ai_vs_human": {
            "reviewed": len(human),
            "accepted": sum(1 for c in human if c.decision_source == DecisionSource.HUMAN_ACCEPTED),
            "overridden": sum(1 for c in human if c.decision_source == DecisionSource.HUMAN_OVERRIDDEN),
            "category_changed": category_changed,
            "priority_changed": priority_changed,
        },
        "confidence_histogram": [
            {
                "from": round(i / CONFIDENCE_BINS, 2),
                "to": round((i + 1) / CONFIDENCE_BINS, 2),
                "count": n,
                "below_threshold": threshold is not None and (i + 1) / CONFIDENCE_BINS <= threshold,
            }
            for i, n in enumerate(bins)
        ],
        "resolution_hours": {
            "count": len(resolution_hours),
            "mean": round(mean(resolution_hours), 2) if resolution_hours else None,
            "median": round(median(resolution_hours), 2) if resolution_hours else None,
        },
        "escalations": {
            "total": sum(1 for e in escalation_events if e.action == "escalation_triggered"),
            "automatic": sum(1 for e in escalation_events if e.action == "escalation_triggered" and e.actor_user_id is None),
            "manual": sum(1 for e in escalation_events if e.action == "escalation_triggered" and e.actor_user_id is not None),
            "exhausted": sum(1 for e in escalation_events if e.action == "escalation_exhausted"),
        },
        "per_day": [
            {"date": (start + timedelta(days=i)).isoformat(), "count": per_day.get(start + timedelta(days=i), 0)}
            for i in range(14)
        ],
        "attention": [
            {"complaint_id": c.complaint_code, "category": c.category, "priority": c.priority, "level": c.escalation_level}
            for c in open_
            if c.breached_at_top
        ],
    }


# --- in-app notifications --------------------------------------------------------------

NOTIFY_COMPLAINANT = {
    "sent_to_human_review", "assigned", "accepted", "overridden", "rerouted",
    "escalation_triggered", "resolved",
}
NOTIFY_ASSIGNEE = {"sent_to_human_review", "assigned", "rerouted", "escalation_triggered", "tat_breached", "deadline_recalculated"}
NOTIFY_ADMIN = {"escalation_triggered", "escalation_exhausted"}


def notifications(db: Session, user: User, limit: int = 30) -> list[dict]:
    """Recent audit events that concern this user (their complaints, complaints
    assigned to them, or — for administrators — escalations), excluding actions
    the user performed. Read/unread is tracked by the client."""
    is_admin = has_permission(user.role, Permission.MANAGE_RULES_AND_SETTINGS)
    rows = db.execute(
        select(ComplaintEvent, Complaint)
        .join(Complaint, Complaint.id == ComplaintEvent.complaint_id)
        .where(ComplaintEvent.created_at >= utcnow() - timedelta(days=30))
        .order_by(ComplaintEvent.id.desc())
        .limit(500)
    ).all()
    out = []
    for event, c in rows:
        if event.actor_user_id == user.id:
            continue
        mine = c.complainant_id == user.id and event.action in NOTIFY_COMPLAINANT
        assigned = c.assigned_user_id == user.id and event.action in NOTIFY_ASSIGNEE
        admin = is_admin and event.action in NOTIFY_ADMIN
        if not (mine or assigned or admin):
            continue
        out.append(
            {
                "id": event.id,
                "complaint_id": c.complaint_code,
                "action": event.action,
                "audience": "complainant" if mine else "assignee" if assigned else "admin",
                "created_at": event.created_at.isoformat(),
                "automatic": event.actor_user_id is None,
            }
        )
        if len(out) >= limit:
            break
    return out
