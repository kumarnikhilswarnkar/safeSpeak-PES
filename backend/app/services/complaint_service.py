"""Complaint workflow: submit → AI triage → review check → routing → TAT →
human review (accept / override / reroute / resolve) → breach → escalation.

Every function receives the authenticated User from the API layer; identity,
role and reviewer are never taken from client input. Each state change writes
an audit event in the same transaction.
"""
import logging
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
from app.services.keyword_features import keyword_category, keyword_priority
from app.services.triage_service import (
    MODEL_UNAVAILABLE,
    TriageModel,
    TriageResult,
    effective_priority_threshold,
    effective_threshold,
    review_reasons,
)

logger = logging.getLogger("safespeak.complaints")

HUMAN_DECISIONS = (DecisionSource.HUMAN_ACCEPTED, DecisionSource.HUMAN_OVERRIDDEN)
FALLBACK_MODEL_NAME = "model-unavailable"
FALLBACK_MODEL_VERSION = "keyword-fallback"


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


def _routing_snapshot(c: Complaint, routing: routing_service.RoutingResult) -> dict:
    """Why this authority was chosen, kept in the audit event (shown as the routing reason)."""
    return {
        "routing": {
            "rule_id": routing.rule.id,
            "rule_label": routing.rule.label,
            "chain": "category" if routing.rule.category else "default",
            "category": c.category,
            "level": routing.level,
            "target_scope": routing.rule.target_scope,
            "skipped_levels": routing.skipped_levels,
        }
    }


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

@dataclass(frozen=True)
class _Triage:
    result: TriageResult
    threshold: float
    threshold_source: str
    priority_threshold: float
    priority_threshold_source: str
    reasons: list[str]


def _triage(settings: Settings, model: TriageModel | None, description: str) -> _Triage:
    """AI triage, or - if the model is not loaded or inference fails - a safe fallback:
    the complaint is still accepted, labelled provisionally by the frozen keyword rules
    (only so it can be routed to a first reviewer), and ALWAYS sent to human review.
    The fallback is recorded openly (model name, zero confidence, reason)."""
    if model is not None:
        try:
            result = model.predict(description)
            threshold, source = effective_threshold(settings, model)
            p_threshold, p_source = effective_priority_threshold(settings, model)
            return _Triage(result, threshold, source, p_threshold, p_source,
                           review_reasons(result, threshold, settings, p_threshold))
        except Exception as exc:  # an inference failure must never lose a complaint
            logger.error("AI triage failed, using the human-review fallback: %s", type(exc).__name__)
    category, priority = keyword_category(description), keyword_priority(description)
    result = TriageResult(
        model_name=FALLBACK_MODEL_NAME,
        model_version=FALLBACK_MODEL_VERSION,
        category=category,
        category_confidence=0.0,
        priority=priority,
        priority_confidence=0.0,
        probabilities={},
        explanation={
            "fallback": True,
            "note": "The AI model was unavailable. Category and priority are provisional values from the "
                    "frozen keyword rules, used only to route the complaint to a human reviewer.",
            "keyword_baseline": {"category": category, "priority": priority},
        },
    )
    threshold = settings.confidence_threshold or 1.0
    p_threshold = settings.priority_confidence_threshold or threshold
    return _Triage(result, threshold, MODEL_UNAVAILABLE, p_threshold, MODEL_UNAVAILABLE, [MODEL_UNAVAILABLE])


def submit(db: Session, settings: Settings, model: TriageModel | None, user: User, description: str) -> Complaint:
    if not has_permission(user.role, Permission.SUBMIT_COMPLAINT):
        raise PermissionDeniedError("Your account cannot submit complaints")

    triage = _triage(settings, model, description)
    result, reasons = triage.result, triage.reasons
    threshold, threshold_source = triage.threshold, triage.threshold_source
    priority_threshold, priority_threshold_source = triage.priority_threshold, triage.priority_threshold_source
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
            # threshold/threshold_source columns hold the category threshold; the
            # independently selected priority threshold is kept with the explanation
            # (no schema change).
            explanation={
                **(result.explanation or {}),
                "priority_threshold": priority_threshold,
                "priority_threshold_source": priority_threshold_source,
            },
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
            "priority_threshold": priority_threshold,
        },
    )
    if flagged:
        audit_service.record(
            db, c, "sent_to_human_review", None,
            new={"reasons": reasons, "threshold": threshold, "threshold_source": threshold_source,
                 "priority_threshold": priority_threshold, "priority_threshold_source": priority_threshold_source},
        )
    if skipped:
        audit_service.record(
            db, c, "routing_levels_skipped", None,
            new={"skipped_levels": skipped}, remarks="No active authority available at these levels",
        )
    audit_service.record(
        db, c, "assigned", None,
        new={**_assignment_snapshot(c), **tat_service.deadline_snapshot(c), **_routing_snapshot(c, routing)},
        remarks="Automatic routing from the configured escalation chain",
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


# Audit actions that (re)assign a complaint, and those among them chosen by a person.
ASSIGNMENT_ACTIONS = ("assigned", "escalation_triggered", "rerouted", "admin_reassigned")
MANUAL_ASSIGNMENT_ACTIONS = ("rerouted", "admin_reassigned")


def _manually_assigned(c: Complaint) -> str | None:
    """The action that produced the current assignment, if a person chose the assignee
    (a reviewer's reroute or an administrator's intervention); otherwise None."""
    last = next((e for e in reversed(c.events) if e.action in ASSIGNMENT_ACTIONS), None)
    return last.action if last is not None and last.action in MANUAL_ASSIGNMENT_ACTIONS else None


def _confirm_review(db: Session, c: Complaint, reviewer: User, now: datetime, category_changed: bool) -> None:
    """A flagged complaint has been decided by a human: route it for the final
    category and start the resolution clock.

    If a person chose the current assignee (reroute or administrator intervention)
    and the decision did not change the category, that choice is kept: re-routing
    by the chain would silently send the complaint back to someone else."""
    previous = _assignment_snapshot(c)
    manual = _manually_assigned(c)
    if manual and not category_changed:
        c.status = ComplaintStatus.ASSIGNED
        _set_deadline(db, c, TatStage.RESOLUTION, now)
        audit_service.record(
            db, c, "assigned", reviewer,
            previous=previous,
            new={**_assignment_snapshot(c), **tat_service.deadline_snapshot(c), "kept_manual_assignment": manual},
            remarks="Kept the authority chosen by "
            + ("a reviewer's reroute" if manual == "rerouted" else "the administrator's intervention"),
        )
        return
    routing, skipped = routing_service.route_from_level(db, c, c.escalation_level)
    if routing is None:
        raise ConfigurationError("No active authority is configured for the reviewed category")
    _assign(db, c, routing)
    c.status = ComplaintStatus.ASSIGNED
    _set_deadline(db, c, TatStage.RESOLUTION, now)
    audit_service.record(
        db, c, "assigned", reviewer,
        previous=previous,
        new={
            **_assignment_snapshot(c),
            **tat_service.deadline_snapshot(c),
            "skipped_levels": skipped,
            **_routing_snapshot(c, routing),
        },
        remarks="Routed automatically for the reviewed category",
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
            _confirm_review(db, c, reviewer, now, category_changed=False)

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
            _confirm_review(db, c, reviewer, now, category_changed=previous["category"] != c.category)
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
        trigger = {"triggered_by": _user_ref(triggered_by) if triggered_by else "automatic TAT monitor"}
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
            new={
                **_assignment_snapshot(c),
                **tat_service.deadline_snapshot(c),
                "skipped_levels": skipped,
                **_routing_snapshot(c, routing),
                **trigger,
            },
        )
        outcomes.append(
            EscalationOutcome(c.complaint_code, "escalated", from_level, c.escalation_level, _user_ref(c.assigned_user))
        )

    db.commit()
    return outcomes


# --- routing context (shown on the complaint page) -----------------------------------

def routing_context(db: Session, c: Complaint) -> dict:
    """The configured chain for the complaint's current category, the level it is
    at now, and the most recent automatic routing decision recorded in the audit trail."""
    chain = routing_service.chain_for(db, c.category)
    last = next(
        (e for e in reversed(c.events) if e.new_value and "routing" in e.new_value),
        None,
    )
    manual = next(
        (e for e in reversed(c.events) if e.action == "rerouted"),
        None,
    )
    return {
        "chain_kind": "category" if chain and chain[0].category else "default",
        "chain": [
            {
                "level": r.escalation_level,
                "label": r.label,
                "target_role": r.target_role,
                "target_authority_level": r.target_authority_level,
                "target_scope": r.target_scope,
                "target_department": r.target_department.code if r.target_department else None,
            }
            for r in chain
        ],
        "current_level": c.escalation_level,
        "last_decision": {**last.new_value["routing"], "at": last.created_at.isoformat(), "action": last.action}
        if last
        else None,
        "manually_rerouted": manual is not None and (last is None or manual.id > last.id),
    }


# --- administrator intervention (exhausted escalation chain) -------------------------------

INTERVENTION_REASON_MIN = 10


def _intervention_target(c: Complaint) -> tuple[str, str]:
    """The stage the new authority works in, and the status the complaint gets.
    Reassignment never resolves a complaint: a complaint still waiting for human
    review stays in review; otherwise the new authority has not started yet."""
    if c.status == ComplaintStatus.PENDING_REVIEW:
        return TatStage.REVIEW, ComplaintStatus.PENDING_REVIEW
    return TatStage.RESOLUTION, ComplaintStatus.ASSIGNED


def _get_for_intervention(db: Session, admin: User, code: str) -> Complaint:
    if not has_permission(admin.role, Permission.INTERVENE_EXHAUSTED):
        raise PermissionDeniedError("Only an administrator can reassign an exhausted complaint")
    c = get_visible(db, admin, code)
    if c.status not in OPEN_STATUSES:
        raise ConflictError(f"Complaint is {c.status}; only open complaints can be reassigned")
    if not c.breached_at_top:
        raise ConflictError("Administrator intervention is only for complaints whose escalation chain is exhausted")
    return c


def _intervention_candidates(db: Session, c: Complaint) -> list[User]:
    """Active authorities other than the complainant and the current assignee."""
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


def intervention_options(db: Session, admin: User, code: str, now: datetime | None = None) -> dict:
    """What the administrator needs to decide: the eligible authorities (grouped by
    department/office in the UI) and the new TAT that the configured rules give."""
    c = _get_for_intervention(db, admin, code)
    now = now or utcnow()
    stage, status = _intervention_target(c)
    rule = tat_service.resolve_rule(db, stage, c.category, c.priority, c.escalation_level)
    candidates = _intervention_candidates(db, c)
    departments = {u.department.id: u.department for u in candidates if u.department is not None}
    return {
        "complaint_id": c.complaint_code,
        "current_assignee": _user_ref(c.assigned_user),
        "category": c.category,
        "priority": c.priority,
        "escalation_level": c.escalation_level,
        "new_stage": stage,
        "new_status": status,
        "tat": {
            "rule_id": rule.id,
            "hours": rule.tat_hours,
            "deadline_at": (now + timedelta(hours=rule.tat_hours)).isoformat(),
        },
        "departments": [{"id": d.id, "code": d.code, "name": d.name, "kind": d.kind}
                        for d in sorted(departments.values(), key=lambda d: d.name)],
        "candidates": [
            {"id": u.id, "name": u.name, "role": u.role, "authority_level": u.authority_level,
             "department_id": u.department_id}
            for u in candidates
        ],
        "reason_min_length": INTERVENTION_REASON_MIN,
    }


def admin_reassign(
    db: Session,
    admin: User,
    code: str,
    *,
    target_user_id: int,
    reason: str,
    expected_assignee_id: int | None,
    now: datetime | None = None,
) -> Complaint:
    """Reassign a complaint whose escalation chain is exhausted to an authority the
    administrator chooses, with a mandatory reason and a new deadline from the
    configured TAT rules. The original AI output and earlier human decisions are not
    touched; the change is one append-only audit event (who, why, previous and new
    authority, previous and new deadline). The complaint stays open and continues
    through the normal workflow (review/resolution, TAT monitoring)."""
    c = _get_for_intervention(db, admin, code)
    # Lock the row on PostgreSQL so a concurrent reassignment/escalation cannot interleave.
    db.execute(select(Complaint.id).where(Complaint.id == c.id).with_for_update())
    if expected_assignee_id != c.assigned_user_id:
        raise ConflictError("This complaint changed since you opened it. Reload it and try again.")
    reason = (reason or "").strip()
    if len(reason) < INTERVENTION_REASON_MIN:
        raise InvalidRequestError(f"Give a reason of at least {INTERVENTION_REASON_MIN} characters")
    target = db.get(User, target_user_id)
    if (
        target is None
        or not target.is_active
        or target.role not in AUTHORITY_ROLES
        or target.id in (c.complainant_id, c.assigned_user_id)
    ):
        raise InvalidRequestError("Choose a different, active authority (not the complainant or the current assignee)")

    now = now or utcnow()
    stage, status = _intervention_target(c)
    previous = {**_assignment_snapshot(c), **tat_service.deadline_snapshot(c), "breached_at_top": True}
    c.assigned_user_id = target.id
    c.assigned_user = target
    c.handling_department_id = target.department_id
    c.status = status
    c.breached_at_top = False
    _set_deadline(db, c, stage, now)
    audit_service.record(
        db, c, "admin_reassigned", admin,
        previous=previous,
        new={
            **_assignment_snapshot(c),
            **tat_service.deadline_snapshot(c),
            "breached_at_top": False,
            "intervention": {
                "previous_assignee": previous["assigned_user"],
                "new_assignee": _user_ref(target),
                "reason": reason,
            },
        },
        remarks=reason,
    )
    db.commit()
    return _load(db, code)
