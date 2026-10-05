"""Complaint workflow: submit → AI triage → review check → routing → TAT →
human review (accept / override / reroute / resolve) → breach → escalation.

Every function receives the authenticated User from the API layer; identity,
role and reviewer are never taken from client input. Each state change writes
an audit event in the same transaction.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.core.permissions import AUTHORITY_ROLES, Permission, Role, has_permission
from app.core.timeutil import utcnow
from app.models import (
    OPEN_STATUSES,
    AIPrediction,
    Complaint,
    ComplaintEvent,
    ComplaintStatus,
    DecisionSource,
    TatStage,
    User,
)
from app.services import audit_service, routing_service, tat_service
from app.services.errors import (
    ConfigurationError,
    ConflictError,
    InvalidRequestError,
    NotFoundError,
    PermissionDeniedError,
)
from app.services.id_service import next_complaint_code
from app.services.triage_service import TriageModel, effective_threshold, review_reasons

HUMAN_DECISIONS = (DecisionSource.HUMAN_ACCEPTED, DecisionSource.HUMAN_OVERRIDDEN)


def _user_ref(user: User | None) -> dict | None:
    if user is None:
        return None
    return {"id": user.id, "name": user.name, "role": user.role, "authority_level": user.authority_level}


def _assignment_snapshot(c: Complaint) -> dict:
    return {
        "assigned_user": _user_ref(c.assigned_user),
        "handling_department_id": c.handling_department_id,
        "escalation_level": c.escalation_level,
        "status": c.status,
    }


def _assign(db: Session, c: Complaint, routing: routing_service.RoutingResult) -> None:
    c.assigned_user_id = routing.assignee.id
    c.assigned_user = routing.assignee
    c.escalation_level = routing.level
    c.handling_department_id = routing_service.department_for(routing.rule, c, routing.assignee)


def _set_deadline(db: Session, c: Complaint, stage: str, started_at: datetime) -> None:
    rule = tat_service.resolve_rule(db, stage, c.category, c.priority, c.escalation_level)
    tat_service.apply_deadline(c, rule, stage, started_at)


# --- queries -------------------------------------------------------------------

def _load(db: Session, code: str) -> Complaint | None:
    # populate_existing: sessions keep objects after commit, so force a fresh read
    # (otherwise a complaint loaded earlier in the request would show stale events).
    return db.scalar(
        select(Complaint)
        .where(Complaint.complaint_code == code)
        .execution_options(populate_existing=True)
        .options(
            selectinload(Complaint.ai_prediction),
            selectinload(Complaint.events).selectinload(ComplaintEvent.actor),
            selectinload(Complaint.assigned_user).selectinload(User.department),
            selectinload(Complaint.complainant),
            selectinload(Complaint.handling_department),
        )
    )


def can_view(user: User, c: Complaint) -> bool:
    if c.complainant_id == user.id or c.assigned_user_id == user.id:
        return True
    if has_permission(user.role, Permission.VIEW_SCOPED_COMPLAINTS):
        if user.role == Role.ADMIN or user.department_id is None:
            return True  # institution-wide read-only scope
        return user.department_id in (c.handling_department_id, c.complainant_department_id)
    return False


def get_visible(db: Session, user: User, code: str) -> Complaint:
    c = _load(db, code)
    # Same answer for "does not exist" and "not yours", so codes cannot be probed.
    if c is None or not can_view(user, c):
        raise NotFoundError("Complaint not found")
    return c


def _list(db: Session, *conditions) -> list[Complaint]:
    return list(
        db.scalars(
            select(Complaint)
            .where(*conditions)
            .options(
                selectinload(Complaint.ai_prediction),
                selectinload(Complaint.assigned_user).selectinload(User.department),
                selectinload(Complaint.complainant),
                selectinload(Complaint.handling_department),
            )
            .order_by(Complaint.id.desc())
        ).all()
    )


def list_mine(db: Session, user: User) -> list[Complaint]:
    return _list(db, Complaint.complainant_id == user.id)


def list_queue(db: Session, user: User) -> list[Complaint]:
    return sorted(
        _list(db, Complaint.assigned_user_id == user.id, Complaint.status.in_(OPEN_STATUSES)),
        key=lambda c: c.deadline_at,
    )


def list_pending_review(db: Session, user: User) -> list[Complaint]:
    return sorted(
        _list(db, Complaint.assigned_user_id == user.id, Complaint.status == ComplaintStatus.PENDING_REVIEW),
        key=lambda c: c.deadline_at,
    )


def list_scoped(db: Session, user: User) -> list[Complaint]:
    if user.role == Role.ADMIN or user.department_id is None:
        return _list(db)
    return _list(
        db,
        or_(
            Complaint.handling_department_id == user.department_id,
            Complaint.complainant_department_id == user.department_id,
        ),
    )


def reroute_targets(db: Session, reviewer: User, code: str) -> list[User]:
    c = _get_for_review(db, reviewer, code)
    return list(
        db.scalars(
            select(User)
            .where(
                User.is_active.is_(True),
                User.role.in_([r.value for r in AUTHORITY_ROLES]),
                User.id.not_in([c.complainant_id, c.assigned_user_id or 0]),
            )
            .options(selectinload(User.department))
            .order_by(User.authority_level, User.name)
        ).all()
    )


# --- submission ------------------------------------------------------------------

def submit(db: Session, settings: Settings, model: TriageModel, user: User, description: str) -> Complaint:
    if not has_permission(user.role, Permission.SUBMIT_COMPLAINT):
        raise PermissionDeniedError("Your account cannot submit complaints")

    result = model.predict(description)
    threshold, threshold_source = effective_threshold(settings, model)
    reasons = review_reasons(result, threshold, settings)
    flagged = bool(reasons)
    now = utcnow()

    c = Complaint(
        complaint_code=next_complaint_code(db, now, settings.tz),
        complainant_id=user.id,
        complainant=user,
        complainant_role=user.role,
        complainant_department_id=user.department_id,
        description=description,
        category=result.category,
        priority=result.priority,
        decision_source=DecisionSource.AI_PENDING_REVIEW if flagged else DecisionSource.AI_AUTO,
        status=ComplaintStatus.PENDING_REVIEW if flagged else ComplaintStatus.ASSIGNED,
        review_reasons=reasons,
        escalation_level=1,
        escalated=False,
        breached_at_top=False,
    )

    # Flagged complaints go to the first authority in the chain for the
    # AI-predicted category as their reviewer (decision D1).
    routing, skipped = routing_service.route_from_level(db, c, 1)
    if routing is None:
        raise ConfigurationError("No active authority is configured to receive this complaint")
    _assign(db, c, routing)
    _set_deadline(db, c, TatStage.REVIEW if flagged else TatStage.RESOLUTION, now)

    db.add(c)
    db.flush()

    db.add(
        AIPrediction(
            complaint_id=c.id,
            model_name=result.model_name,
            model_version=result.model_version,
            category=result.category,
            category_confidence=result.category_confidence,
            priority=result.priority,
            priority_confidence=result.priority_confidence,
            confidence=result.confidence,
            threshold=threshold,
            threshold_source=threshold_source,
            flagged_for_review=flagged,
            flag_reasons=reasons,
            probabilities=result.probabilities,
        )
    )

    audit_service.record(
        db, c, "complaint_created", user,
        new={"complaint_code": c.complaint_code, "complainant_role": user.role},
    )
    audit_service.record(
        db, c, "ai_triaged", None,
        new={
            "model": f"{result.model_name}:{result.model_version}",
            "category": result.category,
            "category_confidence": result.category_confidence,
            "priority": result.priority,
            "priority_confidence": result.priority_confidence,
            "confidence": result.confidence,
            "threshold": threshold,
        },
    )
    if flagged:
        audit_service.record(
            db, c, "sent_to_human_review", None,
            new={"reasons": reasons, "threshold": threshold, "threshold_source": threshold_source},
        )
    if skipped:
        audit_service.record(
            db, c, "routing_levels_skipped", None,
            new={"skipped_levels": skipped}, remarks="No active authority available at these levels",
        )
    audit_service.record(
        db, c, "assigned", None,
        new={**_assignment_snapshot(c), **tat_service.deadline_snapshot(c)},
    )
    db.commit()
    return _load(db, c.complaint_code)


# --- review ------------------------------------------------------------------------

def _get_for_review(db: Session, reviewer: User, code: str) -> Complaint:
    c = get_visible(db, reviewer, code)
    if not has_permission(reviewer.role, Permission.REVIEW_COMPLAINTS):
        raise PermissionDeniedError("Your account cannot review complaints")
    if c.complainant_id == reviewer.id:
        raise PermissionDeniedError("You cannot review your own complaint")
    if c.assigned_user_id != reviewer.id:
        raise PermissionDeniedError("Only the authority this complaint is assigned to can review it")
    if c.status not in OPEN_STATUSES:
        raise ConflictError(f"Complaint is {c.status} and can no longer be reviewed")
    return c


def _confirm_review(db: Session, c: Complaint, reviewer: User, now: datetime) -> None:
    """A flagged complaint has been decided by a human: route it for the final
    category and start the resolution clock."""
    previous = _assignment_snapshot(c)
    routing, skipped = routing_service.route_from_level(db, c, c.escalation_level)
    if routing is None:
        raise ConfigurationError("No active authority is configured for the reviewed category")
    _assign(db, c, routing)
    c.status = ComplaintStatus.ASSIGNED
    _set_deadline(db, c, TatStage.RESOLUTION, now)
    audit_service.record(
        db, c, "assigned", reviewer,
        previous=previous,
        new={**_assignment_snapshot(c), **tat_service.deadline_snapshot(c), "skipped_levels": skipped},
        remarks="Routed after human review",
    )


def review(
    db: Session,
    settings: Settings,
    reviewer: User,
    code: str,
    action: str,
    *,
    category: str | None = None,
    priority: str | None = None,
    target_user_id: int | None = None,
    remarks: str | None = None,
) -> Complaint:
    c = _get_for_review(db, reviewer, code)
    now = utcnow()
    was_pending = c.status == ComplaintStatus.PENDING_REVIEW

    if action == "accept":
        if c.decision_source in HUMAN_DECISIONS:
            raise ConflictError("A human decision has already been recorded for this complaint")
        previous = {"category": c.category, "priority": c.priority, "decision_source": c.decision_source}
        c.decision_source = DecisionSource.HUMAN_ACCEPTED
        audit_service.record(
            db, c, "accepted", reviewer,
            previous=previous,
            new={"category": c.category, "priority": c.priority, "decision_source": c.decision_source},
            remarks=remarks,
        )
        if was_pending:
            _confirm_review(db, c, reviewer, now)

    elif action == "override":
        if category is None and priority is None:
            raise InvalidRequestError("Override requires a new category and/or priority")
        new_category = category or c.category
        new_priority = priority or c.priority
        if (new_category, new_priority) == (c.category, c.priority):
            raise InvalidRequestError("Override must change the category or the priority")
        previous = {"category": c.category, "priority": c.priority, "decision_source": c.decision_source}
        c.category, c.priority = new_category, new_priority
        c.decision_source = DecisionSource.HUMAN_OVERRIDDEN
        audit_service.record(
            db, c, "overridden", reviewer,
            previous=previous,
            new={"category": c.category, "priority": c.priority, "decision_source": c.decision_source},
            remarks=remarks,
        )
        if was_pending:
            _confirm_review(db, c, reviewer, now)
        elif previous["priority"] != c.priority or previous["category"] != c.category:
            # Same clock, new allowance: the deadline follows the decided priority.
            before = tat_service.deadline_snapshot(c)
            _set_deadline(db, c, c.tat_stage, c.stage_started_at)
            audit_service.record(
                db, c, "deadline_recalculated", reviewer,
                previous=before, new=tat_service.deadline_snapshot(c),
            )

    elif action == "reroute":
        if target_user_id is None:
            raise InvalidRequestError("Reroute requires target_user_id")
        target = db.get(User, target_user_id)
        if (
            target is None
            or not target.is_active
            or target.role not in AUTHORITY_ROLES
            or target.id in (c.complainant_id, c.assigned_user_id)
        ):
            raise InvalidRequestError("Reroute target must be a different, active authority")
        previous = {**_assignment_snapshot(c), **tat_service.deadline_snapshot(c)}
        c.assigned_user_id = target.id
        c.assigned_user = target
        c.handling_department_id = target.department_id
        # The new authority gets a fresh allowance for the current stage.
        _set_deadline(db, c, c.tat_stage, now)
        audit_service.record(
            db, c, "rerouted", reviewer,
            previous=previous,
            new={**_assignment_snapshot(c), **tat_service.deadline_snapshot(c)},
            remarks=remarks,
        )

    elif action == "resolve":
        if was_pending:
            raise ConflictError("Review the complaint (accept or override) before resolving it")
        if not remarks or not remarks.strip():
            raise InvalidRequestError("A resolution note (remarks) is required to resolve")
        previous_status = c.status
        c.status = ComplaintStatus.RESOLVED
        c.resolved_at = now
        c.resolution_note = remarks.strip()
        audit_service.record(
            db, c, "resolved", reviewer,
            previous={"status": previous_status}, new={"status": c.status, "resolved_at": now.isoformat()},
            remarks=c.resolution_note,
        )
    else:
        raise InvalidRequestError(f"Unknown action: {action}")

    db.commit()
    return _load(db, code)


# --- TAT breach and escalation ------------------------------------------------------

def simulate_breach(db: Session, actor: User, code: str) -> Complaint:
    """Demo/testing only (enabled by DEMO_MODE): move the deadline into the past so
    the escalation job can be shown without waiting. Recorded in the audit trail."""
    c = get_visible(db, actor, code)
    if c.status not in OPEN_STATUSES:
        raise ConflictError(f"Complaint is {c.status}; only open complaints can breach their TAT")
    previous = tat_service.deadline_snapshot(c)
    c.deadline_at = utcnow() - timedelta(minutes=1)
    audit_service.record(
        db, c, "tat_breach_simulated", actor,
        previous=previous, new=tat_service.deadline_snapshot(c),
        remarks="Demo mode: deadline moved into the past",
    )
    db.commit()
    return _load(db, code)


@dataclass(frozen=True)
class EscalationOutcome:
    complaint_code: str
    result: str  # "escalated" | "exhausted"
    from_level: int
    to_level: int | None
    new_assignee: dict | None


def escalate_overdue(db: Session, triggered_by: User | None, now: datetime | None = None) -> list[EscalationOutcome]:
    """Escalate every open complaint whose deadline has passed.

    Safe to call repeatedly: an escalated complaint gets a new future deadline,
    and one that has run out of levels is marked breached_at_top, so neither is
    picked up (or audited) again.
    """
    now = now or utcnow()
    overdue = db.scalars(
        select(Complaint)
        .where(
            Complaint.status.in_(OPEN_STATUSES),
            Complaint.deadline_at < now,
            Complaint.breached_at_top.is_(False),
        )
        .order_by(Complaint.deadline_at)
        .with_for_update()
    ).all()

    outcomes = []
    for c in overdue:
        trigger = {"triggered_by": _user_ref(triggered_by) if triggered_by else "scheduler"}
        previous = {**_assignment_snapshot(c), **tat_service.deadline_snapshot(c)}
        audit_service.record(db, c, "tat_breached", triggered_by, previous=previous, new=trigger)

        routing, skipped = routing_service.route_from_level(db, c, c.escalation_level + 1)
        if routing is None:
            c.breached_at_top = True
            audit_service.record(
                db, c, "escalation_exhausted", triggered_by,
                previous=previous, new={"breached_at_top": True, "skipped_levels": skipped, **trigger},
                remarks="No higher authority is configured; needs administrator attention",
            )
            outcomes.append(EscalationOutcome(c.complaint_code, "exhausted", c.escalation_level, None, None))
            continue

        from_level = c.escalation_level
        _assign(db, c, routing)
        c.escalated = True
        if c.status == ComplaintStatus.IN_PROGRESS:
            c.status = ComplaintStatus.ASSIGNED  # the new authority has not started yet
        _set_deadline(db, c, c.tat_stage, now)
        audit_service.record(
            db, c, "escalation_triggered", triggered_by,
            previous=previous,
            new={**_assignment_snapshot(c), **tat_service.deadline_snapshot(c), "skipped_levels": skipped, **trigger},
        )
        outcomes.append(
            EscalationOutcome(c.complaint_code, "escalated", from_level, c.escalation_level, _user_ref(c.assigned_user))
        )

    db.commit()
    return outcomes
