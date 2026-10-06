"""Configurable workflow rules: turnaround times and the escalation chain.

Both are data, not code. The values seeded by seed/prototype_rules.py are SAMPLE
values for the prototype, not the real institutional hierarchy or service levels.
"""
from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.permissions import AUTHORITY_ROLES
from app.core.taxonomy import CATEGORIES, PRIORITIES
from app.db.base import Base, TimestampMixin
from app.models._sql import sql_in


class TatStage(StrEnum):
    REVIEW = "REVIEW"  # time for a reviewer to confirm a flagged complaint
    RESOLUTION = "RESOLUTION"  # time for the assigned authority to resolve it


class TargetScope(StrEnum):
    COMPLAINANT_DEPARTMENT = "COMPLAINANT_DEPARTMENT"  # authority of the complainant's department
    FIXED_DEPARTMENT = "FIXED_DEPARTMENT"  # authority of a named department or office
    INSTITUTION = "INSTITUTION"  # any authority at that level, institution-wide


class TATRule(TimestampMixin, Base):
    """Allowed time for one stage. Empty category/priority/level mean "any";
    when several rules match, the most specific one wins."""

    __tablename__ = "tat_rules"
    __table_args__ = (
        CheckConstraint(sql_in("stage", [s.value for s in TatStage]), name="stage_valid"),
        CheckConstraint(f"category IS NULL OR {sql_in('category', CATEGORIES)}", name="category_valid"),
        CheckConstraint(f"priority IS NULL OR {sql_in('priority', PRIORITIES)}", name="priority_valid"),
        CheckConstraint("escalation_level IS NULL OR escalation_level >= 1", name="level_positive"),
        CheckConstraint("tat_hours > 0", name="hours_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stage: Mapped[str] = mapped_column(String(12))
    category: Mapped[str | None] = mapped_column(String(40))
    priority: Mapped[str | None] = mapped_column(String(10))
    escalation_level: Mapped[int | None] = mapped_column(Integer)
    tat_hours: Mapped[float] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str | None] = mapped_column(String(200))


class EscalationRule(TimestampMixin, Base):
    """One level of the escalation chain. A category-specific chain is used when
    the category has any active rule; otherwise the default chain (category empty)."""

    __tablename__ = "escalation_rules"
    __table_args__ = (
        CheckConstraint(f"category IS NULL OR {sql_in('category', CATEGORIES)}", name="category_valid"),
        CheckConstraint("escalation_level >= 1", name="level_positive"),
        CheckConstraint(sql_in("target_role", sorted(r.value for r in AUTHORITY_ROLES)), name="target_role_valid"),
        CheckConstraint("target_authority_level >= 1", name="authority_level_positive"),
        CheckConstraint(sql_in("target_scope", [s.value for s in TargetScope]), name="target_scope_valid"),
        CheckConstraint(
            "(target_scope = 'FIXED_DEPARTMENT' AND target_department_id IS NOT NULL)"
            " OR (target_scope <> 'FIXED_DEPARTMENT' AND target_department_id IS NULL)",
            name="department_matches_scope",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str | None] = mapped_column(String(40))
    escalation_level: Mapped[int] = mapped_column(Integer)
    target_role: Mapped[str] = mapped_column(String(32))
    target_authority_level: Mapped[int] = mapped_column(Integer)
    target_scope: Mapped[str] = mapped_column(String(32))
    target_department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id", ondelete="RESTRICT"))
    label: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    target_department: Mapped["Department | None"] = relationship()  # noqa: F821
