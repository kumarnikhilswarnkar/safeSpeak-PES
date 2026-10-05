"""SQLAlchemy models.

Every model module must be imported here so that Alembic autogenerate sees
its table. Models are added phase by phase, each with its own migration.
"""
from app.models.complaint import (
    OPEN_STATUSES,
    AIPrediction,
    Complaint,
    ComplaintEvent,
    ComplaintStatus,
    DecisionSource,
    IdCounter,
    ImmutableRecordError,
)
from app.models.department import Department, DepartmentKind
from app.models.rules import EscalationRule, TargetScope, TatStage, TATRule
from app.models.user import User

__all__ = [
    "OPEN_STATUSES",
    "AIPrediction",
    "Complaint",
    "ComplaintEvent",
    "ComplaintStatus",
    "DecisionSource",
    "Department",
    "DepartmentKind",
    "EscalationRule",
    "IdCounter",
    "ImmutableRecordError",
    "TATRule",
    "TargetScope",
    "TatStage",
    "User",
]
