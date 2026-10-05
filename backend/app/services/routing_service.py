"""Routing: find the authority responsible for a complaint at a given level of
the configured escalation chain."""
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Complaint, EscalationRule, TargetScope, User


@dataclass(frozen=True)
class RoutingResult:
    level: int
    rule: EscalationRule
    assignee: User
    # Levels passed over because no active authority was available there.
    skipped_levels: list[int] = field(default_factory=list)


def chain_for(db: Session, category: str) -> list[EscalationRule]:
    """The category's own chain if it has active rules, otherwise the default chain."""
    specific = db.scalars(
        select(EscalationRule)
        .where(EscalationRule.is_active.is_(True), EscalationRule.category == category)
        .order_by(EscalationRule.escalation_level)
    ).all()
    if specific:
        return list(specific)
    return list(
        db.scalars(
            select(EscalationRule)
            .where(EscalationRule.is_active.is_(True), EscalationRule.category.is_(None))
            .order_by(EscalationRule.escalation_level)
        ).all()
    )


def find_assignee(db: Session, rule: EscalationRule, complaint: Complaint) -> User | None:
    query = select(User).where(
        User.is_active.is_(True),
        User.role == rule.target_role,
        User.authority_level == rule.target_authority_level,
        # Nobody handles their own complaint.
        User.id != complaint.complainant_id,
    )
    if rule.target_scope == TargetScope.COMPLAINANT_DEPARTMENT:
        if complaint.complainant_department_id is None:
            return None
        query = query.where(User.department_id == complaint.complainant_department_id)
    elif rule.target_scope == TargetScope.FIXED_DEPARTMENT:
        query = query.where(User.department_id == rule.target_department_id)
    return db.scalars(query.order_by(User.id).limit(1)).first()


def route_from_level(db: Session, complaint: Complaint, start_level: int) -> tuple[RoutingResult | None, list[int]]:
    """First level >= start_level that has an available authority.
    Returns (result, skipped levels); result is None when the chain is exhausted."""
    skipped: list[int] = []
    for rule in chain_for(db, complaint.category):
        if rule.escalation_level < start_level:
            continue
        assignee = find_assignee(db, rule, complaint)
        if assignee is not None:
            return RoutingResult(rule.escalation_level, rule, assignee, skipped), skipped
        skipped.append(rule.escalation_level)
    return None, skipped


def department_for(rule: EscalationRule, complaint: Complaint, assignee: User) -> int | None:
    if rule.target_scope == TargetScope.COMPLAINANT_DEPARTMENT:
        return complaint.complainant_department_id
    if rule.target_scope == TargetScope.FIXED_DEPARTMENT:
        return rule.target_department_id
    return assignee.department_id
