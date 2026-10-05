"""Turnaround time: pick the TAT rule for a complaint and compute its deadline.
There is no hidden default: if no rule matches, the action fails with a clear
configuration error."""
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Complaint, TATRule
from app.services.errors import ConfigurationError


def resolve_rule(db: Session, stage: str, category: str, priority: str, level: int) -> TATRule:
    """Most specific active rule wins: category beats priority beats level.
    Two equally specific matches are a configuration error, not a guess."""
    candidates = db.scalars(
        select(TATRule).where(
            TATRule.is_active.is_(True),
            TATRule.stage == stage,
            or_(TATRule.category.is_(None), TATRule.category == category),
            or_(TATRule.priority.is_(None), TATRule.priority == priority),
            or_(TATRule.escalation_level.is_(None), TATRule.escalation_level == level),
        )
    ).all()
    if not candidates:
        raise ConfigurationError(
            f"No TAT rule configured for stage {stage}, category {category}, priority {priority}, level {level}"
        )

    def specificity(rule: TATRule) -> int:
        return (rule.category is not None) * 4 + (rule.priority is not None) * 2 + (rule.escalation_level is not None)

    best = max(specificity(r) for r in candidates)
    winners = [r for r in candidates if specificity(r) == best]
    if len(winners) > 1:
        ids = ", ".join(str(r.id) for r in winners)
        raise ConfigurationError(f"Ambiguous TAT rules ({ids}) for stage {stage}, {category}/{priority}, level {level}")
    return winners[0]


def apply_deadline(complaint: Complaint, rule: TATRule, stage: str, started_at: datetime) -> None:
    complaint.tat_stage = stage
    complaint.tat_rule_id = rule.id
    complaint.tat_hours = rule.tat_hours
    complaint.stage_started_at = started_at
    complaint.deadline_at = started_at + timedelta(hours=rule.tat_hours)


def deadline_snapshot(complaint: Complaint) -> dict:
    return {
        "tat_stage": complaint.tat_stage,
        "tat_rule_id": complaint.tat_rule_id,
        "tat_hours": complaint.tat_hours,
        "deadline_at": complaint.deadline_at.isoformat() if complaint.deadline_at else None,
    }


@dataclass(frozen=True)
class TatStatus:
    state: str  # ON_TRACK | DUE_SOON | OVERDUE | STOPPED
    seconds_remaining: int | None


def tat_status(complaint: Complaint, now: datetime, due_soon_fraction: float) -> TatStatus:
    if complaint.resolved_at is not None:
        return TatStatus("STOPPED", None)
    remaining = (complaint.deadline_at - now).total_seconds()
    if remaining < 0:
        return TatStatus("OVERDUE", int(remaining))
    if remaining <= complaint.tat_hours * 3600 * due_soon_fraction:
        return TatStatus("DUE_SOON", int(remaining))
    return TatStatus("ON_TRACK", int(remaining))
