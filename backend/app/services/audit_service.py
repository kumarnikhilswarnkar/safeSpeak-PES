"""Append-only audit trail for complaints. The actor is always a server-side
User object (or None for the system), never a value supplied by the client."""
from typing import Any

from sqlalchemy.orm import Session

from app.models import Complaint, ComplaintEvent, User


def record(
    db: Session,
    complaint: Complaint,
    action: str,
    actor: User | None,
    *,
    previous: dict[str, Any] | None = None,
    new: dict[str, Any] | None = None,
    remarks: str | None = None,
) -> ComplaintEvent:
    event = ComplaintEvent(
        complaint_id=complaint.id,
        action=action,
        actor_user_id=actor.id if actor else None,
        actor_role=actor.role if actor else None,
        previous_value=previous,
        new_value=new,
        remarks=remarks,
    )
    db.add(event)
    return event
