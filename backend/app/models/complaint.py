from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    event,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.taxonomy import CATEGORIES, PRIORITIES
from app.core.timeutil import utcnow
from app.db.base import Base, TimestampMixin
from app.db.types import JSONDocument, UTCDateTime
from app.models._sql import sql_in
from app.models.department import Department
from app.models.rules import TatStage
from app.models.user import User


class ComplaintStatus(StrEnum):
    PENDING_REVIEW = "PENDING_REVIEW"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


OPEN_STATUSES = (ComplaintStatus.PENDING_REVIEW, ComplaintStatus.ASSIGNED, ComplaintStatus.IN_PROGRESS)


class DecisionSource(StrEnum):
    """Where the complaint's current category and priority came from."""

    AI_PENDING_REVIEW = "AI_PENDING_REVIEW"  # AI values, waiting for a human
    AI_AUTO = "AI_AUTO"  # AI values used without review (confident, not High/Critical)
    HUMAN_ACCEPTED = "HUMAN_ACCEPTED"  # a reviewer confirmed the AI values
    HUMAN_OVERRIDDEN = "HUMAN_OVERRIDDEN"  # a reviewer changed category and/or priority


_OPEN_NOT_EXHAUSTED = "status IN ('PENDING_REVIEW', 'ASSIGNED', 'IN_PROGRESS') AND breached_at_top = false"


class Complaint(TimestampMixin, Base):
    """A grievance. category/priority hold the CURRENT working values (AI first,
    then the human decision); the original AI output lives in ai_predictions."""

    __tablename__ = "complaints"
    __table_args__ = (
        CheckConstraint(sql_in("category", CATEGORIES), name="category_valid"),
        CheckConstraint(sql_in("priority", PRIORITIES), name="priority_valid"),
        CheckConstraint(sql_in("status", [s.value for s in ComplaintStatus]), name="status_valid"),
        CheckConstraint(sql_in("decision_source", [d.value for d in DecisionSource]), name="decision_source_valid"),
        CheckConstraint(sql_in("tat_stage", [s.value for s in TatStage]), name="tat_stage_valid"),
        CheckConstraint("escalation_level >= 1", name="escalation_level_positive"),
        CheckConstraint("tat_hours > 0", name="tat_hours_positive"),
        CheckConstraint(
            "(status IN ('RESOLVED', 'CLOSED') AND resolved_at IS NOT NULL)"
            " OR (status NOT IN ('RESOLVED', 'CLOSED') AND resolved_at IS NULL)",
            name="resolved_at_matches_status",
        ),
        # Reviewer queues: "open complaints assigned to me".
        Index("ix_complaints_assigned_user_status", "assigned_user_id", "status"),
        # TAT monitor: only open, not-yet-exhausted complaints are scanned by deadline.
        Index(
            "ix_complaints_open_deadline",
            "deadline_at",
            postgresql_where=text(_OPEN_NOT_EXHAUSTED),
            sqlite_where=text(_OPEN_NOT_EXHAUSTED),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    complaint_code: Mapped[str] = mapped_column(String(20), unique=True)
    complainant_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    complainant_role: Mapped[str] = mapped_column(String(32))
    complainant_department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"), index=True
    )
    description: Mapped[str] = mapped_column(Text)

    category: Mapped[str] = mapped_column(String(40))
    priority: Mapped[str] = mapped_column(String(10))
    decision_source: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(20), index=True)
    review_reasons: Mapped[list[str]] = mapped_column(JSONDocument, default=list)

    handling_department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"), index=True
    )
    assigned_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    escalation_level: Mapped[int] = mapped_column(Integer, default=1)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    breached_at_top: Mapped[bool] = mapped_column(Boolean, default=False)

    tat_stage: Mapped[str] = mapped_column(String(12))
    tat_rule_id: Mapped[int] = mapped_column(ForeignKey("tat_rules.id", ondelete="RESTRICT"))
    tat_hours: Mapped[float] = mapped_column(Float)
    stage_started_at: Mapped[datetime] = mapped_column(UTCDateTime)
    deadline_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)

    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    resolution_note: Mapped[str | None] = mapped_column(Text)

    complainant: Mapped[User] = relationship(foreign_keys=[complainant_id])
    assigned_user: Mapped[User | None] = relationship(foreign_keys=[assigned_user_id])
    handling_department: Mapped[Department | None] = relationship(foreign_keys=[handling_department_id])
    ai_prediction: Mapped["AIPrediction"] = relationship(back_populates="complaint", uselist=False)
    events: Mapped[list["ComplaintEvent"]] = relationship(
        back_populates="complaint", order_by="ComplaintEvent.id"
    )

    @property
    def needs_review(self) -> bool:
        return self.status == ComplaintStatus.PENDING_REVIEW


class AIPrediction(Base):
    """The model's original recommendation. Never updated or deleted."""

    __tablename__ = "ai_predictions"
    __table_args__ = (
        CheckConstraint(sql_in("category", CATEGORIES), name="category_valid"),
        CheckConstraint(sql_in("priority", PRIORITIES), name="priority_valid"),
        CheckConstraint("category_confidence BETWEEN 0 AND 1", name="category_confidence_range"),
        CheckConstraint("priority_confidence BETWEEN 0 AND 1", name="priority_confidence_range"),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="confidence_range"),
        CheckConstraint("threshold > 0 AND threshold <= 1", name="threshold_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id", ondelete="RESTRICT"), unique=True)
    model_name: Mapped[str] = mapped_column(String(60))
    model_version: Mapped[str] = mapped_column(String(30))
    category: Mapped[str] = mapped_column(String(40))
    category_confidence: Mapped[float] = mapped_column(Float)
    priority: Mapped[str] = mapped_column(String(10))
    priority_confidence: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)  # min(category, priority)
    threshold: Mapped[float] = mapped_column(Float)
    threshold_source: Mapped[str] = mapped_column(String(40))
    flagged_for_review: Mapped[bool] = mapped_column(Boolean)
    flag_reasons: Mapped[list[str]] = mapped_column(JSONDocument, default=list)
    probabilities: Mapped[dict[str, Any]] = mapped_column(JSONDocument)
    # Contributing words per task and the keyword-baseline labels (model v2+).
    explanation: Mapped[dict[str, Any] | None] = mapped_column(JSONDocument)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    complaint: Mapped[Complaint] = relationship(back_populates="ai_prediction")


class ComplaintEvent(Base):
    """Audit trail entry. Append-only: never updated or deleted."""

    __tablename__ = "complaint_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id", ondelete="RESTRICT"), index=True)
    action: Mapped[str] = mapped_column(String(40))
    # Empty actor means the system (for example, the escalation job).
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    actor_role: Mapped[str | None] = mapped_column(String(32))
    previous_value: Mapped[dict[str, Any] | None] = mapped_column(JSONDocument)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSONDocument)
    remarks: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)

    complaint: Mapped[Complaint] = relationship(back_populates="events")
    actor: Mapped[User | None] = relationship()


class IdCounter(Base):
    """Per-year sequence behind complaint codes (SSP-YYYY-NNNNNN)."""

    __tablename__ = "id_counters"

    year: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    last_value: Mapped[int] = mapped_column(Integer, default=0)


class ImmutableRecordError(RuntimeError):
    pass


def _refuse_change(_mapper, _connection, target) -> None:
    raise ImmutableRecordError(f"{type(target).__name__} records cannot be modified or deleted")


for _model in (AIPrediction, ComplaintEvent):
    event.listen(_model, "before_update", _refuse_change)
    event.listen(_model, "before_delete", _refuse_change)
