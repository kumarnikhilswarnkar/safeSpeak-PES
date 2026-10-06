from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import Settings
from app.core.timeutil import utcnow
from app.models import Complaint, ComplaintEvent, User
from app.schemas.user import DepartmentOut
from app.services.tat_service import tat_status

Category = Literal[
    "Hostel",
    "Exam",
    "Academic / Department",
    "Infrastructure and facilities",
    "Safety and welfare",
    "Administrative / Fees",
    "Library / Transport",
    "Other",
]
Priority = Literal["Low", "Medium", "High", "Critical"]


# --- requests (unknown fields such as user_id, role or reviewer_id are rejected) ---

class ComplaintCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=10, max_length=5000)

    @field_validator("description")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 10:
            raise ValueError("Description must be at least 10 characters")
        return value


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["accept", "override", "reroute", "resolve"]
    category: Category | None = None
    priority: Priority | None = None
    target_user_id: int | None = None
    remarks: str | None = Field(default=None, max_length=2000)


# --- responses ------------------------------------------------------------------

class PersonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    role: str
    authority_level: int | None = None
    department: DepartmentOut | None = None


class AIRecommendationOut(BaseModel):
    model: str
    category: str
    category_confidence: float
    priority: str
    priority_confidence: float
    confidence: float
    threshold: float
    threshold_source: str
    flagged_for_review: bool
    flag_reasons: list[str]
    # Contributing words per task and the keyword-baseline labels (model v2+).
    explanation: dict[str, Any] | None = None


class TatOut(BaseModel):
    stage: str
    hours: float
    rule_id: int
    started_at: datetime
    deadline_at: datetime
    state: str
    seconds_remaining: int | None


class ComplaintOut(BaseModel):
    complaint_id: str
    description: str
    status: str
    category: str
    priority: str
    decision_source: str
    needs_review: bool
    review_reasons: list[str]
    ai: AIRecommendationOut
    complainant: PersonOut
    assigned_to: PersonOut | None
    handling_department: DepartmentOut | None
    escalation_level: int
    escalated: bool
    breached_at_top: bool
    tat: TatOut
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    resolution_note: str | None


class EventOut(BaseModel):
    id: int
    action: str
    actor: PersonOut | None
    actor_role: str | None
    previous_value: dict[str, Any] | None
    new_value: dict[str, Any] | None
    remarks: str | None
    created_at: datetime


class EscalationStepOut(BaseModel):
    at: datetime
    result: Literal["escalated", "exhausted"]
    automatic: bool
    from_level: int | None
    to_level: int | None
    from_assignee: dict[str, Any] | None
    to_assignee: dict[str, Any] | None
    previous_deadline_at: str | None
    new_deadline_at: str | None


class EscalationSummaryOut(BaseModel):
    original_deadline_at: str | None
    current_deadline_at: datetime
    overdue_seconds: int | None
    history: list[EscalationStepOut]


class HumanDecisionOut(BaseModel):
    action: str
    reviewer: PersonOut | None
    at: datetime
    remarks: str | None
    previous: dict[str, Any] | None
    new: dict[str, Any] | None


class ComplaintDetailOut(ComplaintOut):
    events: list[EventOut]
    routing: dict[str, Any] | None = None
    escalation: EscalationSummaryOut
    human_decision: HumanDecisionOut | None = None


class EscalationOutcomeOut(BaseModel):
    complaint_id: str
    result: str
    from_level: int
    to_level: int | None
    new_assignee: dict[str, Any] | None


class EscalationRunOut(BaseModel):
    processed: int
    outcomes: list[EscalationOutcomeOut]


# --- builders -------------------------------------------------------------------------

def _person(user: User | None) -> PersonOut | None:
    return PersonOut.model_validate(user) if user else None


def complaint_out(c: Complaint, settings: Settings) -> ComplaintOut:
    p = c.ai_prediction
    status = tat_status(c, utcnow(), settings.due_soon_fraction)
    return ComplaintOut(
        complaint_id=c.complaint_code,
        description=c.description,
        status=c.status,
        category=c.category,
        priority=c.priority,
        decision_source=c.decision_source,
        needs_review=c.needs_review,
        review_reasons=c.review_reasons or [],
        ai=AIRecommendationOut(
            model=f"{p.model_name}:{p.model_version}",
            category=p.category,
            category_confidence=p.category_confidence,
            priority=p.priority,
            priority_confidence=p.priority_confidence,
            confidence=p.confidence,
            threshold=p.threshold,
            threshold_source=p.threshold_source,
            flagged_for_review=p.flagged_for_review,
            flag_reasons=p.flag_reasons or [],
            explanation=p.explanation,
        ),
        complainant=_person(c.complainant),
        assigned_to=_person(c.assigned_user),
        handling_department=DepartmentOut.model_validate(c.handling_department) if c.handling_department else None,
        escalation_level=c.escalation_level,
        escalated=c.escalated,
        breached_at_top=c.breached_at_top,
        tat=TatOut(
            stage=c.tat_stage,
            hours=c.tat_hours,
            rule_id=c.tat_rule_id,
            started_at=c.stage_started_at,
            deadline_at=c.deadline_at,
            state=status.state,
            seconds_remaining=status.seconds_remaining,
        ),
        created_at=c.created_at,
        updated_at=c.updated_at,
        resolved_at=c.resolved_at,
        resolution_note=c.resolution_note,
    )


def event_out(e: ComplaintEvent) -> EventOut:
    return EventOut(
        id=e.id,
        action=e.action,
        actor=_person(e.actor),
        actor_role=e.actor_role,
        previous_value=e.previous_value,
        new_value=e.new_value,
        remarks=e.remarks,
        created_at=e.created_at,
    )


def _escalation_summary(c: Complaint, now: datetime) -> EscalationSummaryOut:
    original = next((e.new_value["deadline_at"] for e in c.events if e.new_value and e.new_value.get("deadline_at")), None)
    history = []
    for e in c.events:
        if e.action not in ("escalation_triggered", "escalation_exhausted"):
            continue
        prev, new = e.previous_value or {}, e.new_value or {}
        exhausted = e.action == "escalation_exhausted"
        history.append(
            EscalationStepOut(
                at=e.created_at,
                result="exhausted" if exhausted else "escalated",
                automatic=e.actor_user_id is None,
                from_level=prev.get("escalation_level"),
                to_level=None if exhausted else new.get("escalation_level"),
                from_assignee=prev.get("assigned_user"),
                to_assignee=None if exhausted else new.get("assigned_user"),
                previous_deadline_at=prev.get("deadline_at"),
                new_deadline_at=None if exhausted else new.get("deadline_at"),
            )
        )
    overdue = int((now - c.deadline_at).total_seconds()) if c.resolved_at is None and c.deadline_at < now else None
    return EscalationSummaryOut(
        original_deadline_at=original, current_deadline_at=c.deadline_at, overdue_seconds=overdue, history=history
    )


def _human_decision(c: Complaint) -> HumanDecisionOut | None:
    e = next((e for e in reversed(c.events) if e.action in ("accepted", "overridden")), None)
    if e is None:
        return None
    return HumanDecisionOut(
        action=e.action, reviewer=_person(e.actor), at=e.created_at, remarks=e.remarks,
        previous=e.previous_value, new=e.new_value,
    )


def complaint_detail_out(c: Complaint, settings: Settings, routing: dict | None = None) -> ComplaintDetailOut:
    return ComplaintDetailOut(
        **complaint_out(c, settings).model_dump(),
        events=[event_out(e) for e in c.events],
        routing=routing,
        escalation=_escalation_summary(c, utcnow()),
        human_decision=_human_decision(c),
    )
