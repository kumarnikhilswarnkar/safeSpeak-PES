"""Seed SAMPLE TAT rules and a SAMPLE escalation chain.

These are prototype values chosen for demonstration, NOT the real PES
University hierarchy or service levels. They are ordinary database rows and
can be changed without touching application code.

Usage, from the backend folder, after `alembic upgrade head`:

    python -m seed.prototype_rules
"""
import sys

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.permissions import Role
from app.db.session import create_db_engine, create_session_factory
from app.models import EscalationRule, TargetScope, TatStage, TATRule

# Default chain for every category without its own chain.
# escalation_level = position in the chain; target_authority_level = the
# authority level an account must hold to receive complaints at that position.
SAMPLE_DEFAULT_CHAIN = [
    (1, Role.DEPARTMENT_AUTHORITY, 1, TargetScope.COMPLAINANT_DEPARTMENT, "L1 Department Authority (sample)"),
    (2, Role.HIGHER_AUTHORITY, 3, TargetScope.INSTITUTION, "L3 Dean (sample)"),
    (3, Role.HIGHER_AUTHORITY, 4, TargetScope.INSTITUTION, "L4 Director (sample)"),
]

# Category-specific chain example: safety concerns skip straight to the Director.
SAMPLE_CATEGORY_CHAINS = {
    "Safety and welfare": [
        (1, Role.DEPARTMENT_AUTHORITY, 1, TargetScope.COMPLAINANT_DEPARTMENT, "L1 Department Authority (sample)"),
        (2, Role.HIGHER_AUTHORITY, 4, TargetScope.INSTITUTION, "L4 Director (sample, safety fast-track)"),
    ],
}

# Category-specific chain that targets a named office instead of the
# complainant's department. Added by seed_demo_routing() only when the office
# exists (the demo seed creates it), so the core sample rules stay unchanged.
SAMPLE_OFFICE_CHAINS = {
    "Infrastructure and facilities": (
        "FACILITIES",
        [
            (1, Role.DEPARTMENT_AUTHORITY, 1, TargetScope.FIXED_DEPARTMENT, "L1 Facilities Office (sample)"),
            (2, Role.HIGHER_AUTHORITY, 3, TargetScope.INSTITUTION, "L3 Dean (sample)"),
            (3, Role.HIGHER_AUTHORITY, 4, TargetScope.INSTITUTION, "L4 Director (sample)"),
        ],
    ),
}

# Hours for a reviewer to confirm a flagged complaint (any category, any level).
SAMPLE_REVIEW_HOURS = {"Critical": 1, "High": 4, "Medium": 12, "Low": 24}

# Hours to resolve, by escalation level (any category).
SAMPLE_RESOLUTION_HOURS = {
    1: {"Critical": 4, "High": 24, "Medium": 72, "Low": 168},
    2: {"Critical": 2, "High": 12, "Medium": 48, "Low": 96},
    3: {"Critical": 1, "High": 6, "Medium": 24, "Low": 48},
}

# Category + priority overrides (any level); more specific, so they win.
SAMPLE_CATEGORY_RESOLUTION_HOURS = [
    ("Infrastructure and facilities", "Medium", 48),
    ("Safety and welfare", "High", 12),
    ("Safety and welfare", "Critical", 2),
]


def seed_prototype_rules(db: Session) -> tuple[int, int]:
    """Insert the sample rules if no rules exist yet. Returns (tat_rules, escalation_rules) added."""
    has_tat = db.scalar(select(func.count()).select_from(TATRule)) > 0
    has_chain = db.scalar(select(func.count()).select_from(EscalationRule)) > 0
    tat_added = chain_added = 0

    if not has_chain:
        chains = [(None, SAMPLE_DEFAULT_CHAIN), *SAMPLE_CATEGORY_CHAINS.items()]
        for category, chain in chains:
            for level, role, authority_level, scope, label in chain:
                db.add(
                    EscalationRule(
                        category=category,
                        escalation_level=level,
                        target_role=role.value,
                        target_authority_level=authority_level,
                        target_scope=scope.value,
                        label=label,
                    )
                )
                chain_added += 1

    if not has_tat:
        for priority, hours in SAMPLE_REVIEW_HOURS.items():
            db.add(TATRule(stage=TatStage.REVIEW.value, priority=priority, tat_hours=hours, note="sample review TAT"))
            tat_added += 1
        for level, by_priority in SAMPLE_RESOLUTION_HOURS.items():
            for priority, hours in by_priority.items():
                db.add(
                    TATRule(
                        stage=TatStage.RESOLUTION.value,
                        priority=priority,
                        escalation_level=level,
                        tat_hours=hours,
                        note="sample resolution TAT",
                    )
                )
                tat_added += 1
        for category, priority, hours in SAMPLE_CATEGORY_RESOLUTION_HOURS:
            db.add(
                TATRule(
                    stage=TatStage.RESOLUTION.value,
                    category=category,
                    priority=priority,
                    tat_hours=hours,
                    note="sample category-specific resolution TAT",
                )
            )
            tat_added += 1

    db.flush()
    return tat_added, chain_added


def seed_demo_routing(db: Session, departments: dict) -> int:
    """Add SAMPLE_OFFICE_CHAINS for categories that have no rules yet, when the
    target office exists. Idempotent. Returns the number of rules added."""
    added = 0
    for category, (office_code, chain) in SAMPLE_OFFICE_CHAINS.items():
        office = departments.get(office_code)
        exists = db.scalar(select(func.count()).select_from(EscalationRule).where(EscalationRule.category == category))
        if office is None or exists:
            continue
        for level, role, authority_level, scope, label in chain:
            db.add(
                EscalationRule(
                    category=category,
                    escalation_level=level,
                    target_role=role.value,
                    target_authority_level=authority_level,
                    target_scope=scope.value,
                    target_department_id=office.id if scope == TargetScope.FIXED_DEPARTMENT else None,
                    label=label,
                )
            )
            added += 1
    db.flush()
    return added


def main() -> int:
    settings = get_settings()
    engine = create_db_engine(settings.database_url)
    if not inspect(engine).has_table("tat_rules"):
        print("Database tables are missing. Run `alembic upgrade head` first.", file=sys.stderr)
        return 1
    with create_session_factory(engine)() as db:
        tat_added, chain_added = seed_prototype_rules(db)
        db.commit()
    engine.dispose()
    if tat_added == chain_added == 0:
        print("Rules already exist; nothing changed.")
    else:
        print(f"Added {tat_added} sample TAT rule(s) and {chain_added} sample escalation rule(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
