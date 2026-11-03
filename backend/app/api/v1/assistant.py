"""SafeSpeak Assistant endpoint: deterministic, database-backed answers about the
complaints the signed-in user is allowed to see (see services/assistant_service.py).
No external AI service; messages are not stored."""
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import AppSettings, CurrentUser, DbSession
from app.services import assistant_service

router = APIRouter(prefix="/assistant", tags=["assistant"])


class ListContext(BaseModel):
    """The list shown in the previous answer, for "show more" and "the second one".
    Only a position hint: the list is re-queried with the user's permissions."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["mine", "queue", "overdue", "scoped"]
    offset: int = Field(default=0, ge=0, le=100_000)
    limit: int = Field(default=8, ge=1, le=100)
    total: int = Field(default=0, ge=0, le=100_000)


class AssistantMessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # identity and role come only from the token

    message: str = Field(min_length=1, max_length=500)
    # The complaint discussed in the previous turn (for follow-ups such as "and the
    # deadline?"). Only a hint: access is checked again on every message.
    context_complaint_id: str | None = Field(default=None, max_length=24)
    list_context: ListContext | None = None


class AssistantMessageOut(BaseModel):
    reply: str
    intent: str
    complaint_id: str | None
    cards: list[dict[str, Any]]
    suggestions: list[str]
    list_context: dict[str, Any] | None = None


@router.post("/messages", response_model=AssistantMessageOut)
def ask(payload: AssistantMessageIn, user: CurrentUser, db: DbSession, settings: AppSettings) -> AssistantMessageOut:
    r = assistant_service.respond(
        db, settings, user, payload.message, payload.context_complaint_id,
        payload.list_context.model_dump() if payload.list_context else None,
    )
    return AssistantMessageOut(reply=r.reply, intent=r.intent, complaint_id=r.complaint_id,
                               cards=r.cards, suggestions=r.suggestions, list_context=r.list_context)
