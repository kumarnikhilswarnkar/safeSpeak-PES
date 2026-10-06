"""Complaint ("concern") endpoints. Every route takes the user from the verified
JWT via the auth dependencies; no route accepts a user, reviewer or role from
the request. Fixed paths are declared before /{concern_id}."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import AppSettings, CurrentUser, DbSession, require_permission
from app.core.permissions import Permission
from app.models import User
from app.schemas.complaint import (
    ComplaintCreate,
    ComplaintDetailOut,
    ComplaintOut,
    EscalationOutcomeOut,
    EscalationRunOut,
    PersonOut,
    ReviewRequest,
    complaint_detail_out,
    complaint_out,
)
from app.services import complaint_service
from app.services.triage_service import TriageModel

router = APIRouter(prefix="/concerns", tags=["concerns"])


def get_triage_model(request: Request) -> TriageModel:
    model = request.app.state.triage_model
    if model is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The AI triage model is not available")
    return model


Submitter = Annotated[User, Depends(require_permission(Permission.SUBMIT_COMPLAINT))]
OwnViewer = Annotated[User, Depends(require_permission(Permission.VIEW_OWN_COMPLAINTS))]
Handler = Annotated[User, Depends(require_permission(Permission.VIEW_ASSIGNED_COMPLAINTS))]
Reviewer = Annotated[User, Depends(require_permission(Permission.REVIEW_COMPLAINTS))]
ScopedViewer = Annotated[User, Depends(require_permission(Permission.VIEW_SCOPED_COMPLAINTS))]
SystemOperator = Annotated[User, Depends(require_permission(Permission.MANAGE_RULES_AND_SETTINGS))]


def _detail(db, c, settings) -> ComplaintDetailOut:
    return complaint_detail_out(c, settings, complaint_service.routing_context(db, c))


def _require_demo_mode(settings: AppSettings) -> None:
    if not settings.demo_mode:
        # Hidden entirely unless DEMO_MODE is enabled.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")


@router.post("", response_model=ComplaintDetailOut, status_code=status.HTTP_201_CREATED)
def submit_concern(
    payload: ComplaintCreate,
    user: Submitter,
    db: DbSession,
    settings: AppSettings,
    model: Annotated[TriageModel, Depends(get_triage_model)],
) -> ComplaintDetailOut:
    c = complaint_service.submit(db, settings, model, user, payload.description)
    return _detail(db, c, settings)


@router.get("", response_model=list[ComplaintOut])
def list_in_scope(user: ScopedViewer, db: DbSession, settings: AppSettings) -> list[ComplaintOut]:
    """Read-only list for view-only authorities and admins, limited to their scope."""
    return [complaint_out(c, settings) for c in complaint_service.list_scoped(db, user)]


@router.get("/mine", response_model=list[ComplaintOut])
def my_concerns(user: OwnViewer, db: DbSession, settings: AppSettings) -> list[ComplaintOut]:
    return [complaint_out(c, settings) for c in complaint_service.list_mine(db, user)]


@router.get("/queue", response_model=list[ComplaintOut])
def my_queue(user: Handler, db: DbSession, settings: AppSettings) -> list[ComplaintOut]:
    """Open complaints assigned to the current authority, earliest deadline first."""
    return [complaint_out(c, settings) for c in complaint_service.list_queue(db, user)]


@router.get("/pending-triage", response_model=list[ComplaintOut])
def pending_triage(user: Reviewer, db: DbSession, settings: AppSettings) -> list[ComplaintOut]:
    """Complaints waiting for this authority's human review."""
    return [complaint_out(c, settings) for c in complaint_service.list_pending_review(db, user)]


@router.post("/escalate-overdue", response_model=EscalationRunOut)
def escalate_overdue(user: SystemOperator, request: Request) -> EscalationRunOut:
    """Run the TAT check now. The automatic TAT monitor runs the same check in the
    background every TAT_MONITOR_INTERVAL_SECONDS; both share one lock, so a
    complaint is never escalated twice by overlapping runs."""
    outcomes = request.app.state.tat_monitor.run_once(user, raise_errors=True).outcomes
    return EscalationRunOut(
        processed=len(outcomes),
        outcomes=[
            EscalationOutcomeOut(
                complaint_id=o.complaint_code,
                result=o.result,
                from_level=o.from_level,
                to_level=o.to_level,
                new_assignee=o.new_assignee,
            )
            for o in outcomes
        ],
    )


@router.get("/{concern_id}", response_model=ComplaintDetailOut)
def get_concern(concern_id: str, user: CurrentUser, db: DbSession, settings: AppSettings) -> ComplaintDetailOut:
    return _detail(db, complaint_service.get_visible(db, user, concern_id), settings)


@router.get("/{concern_id}/reroute-targets", response_model=list[PersonOut])
def reroute_targets(concern_id: str, user: Reviewer, db: DbSession) -> list[PersonOut]:
    return [PersonOut.model_validate(u) for u in complaint_service.reroute_targets(db, user, concern_id)]


@router.post("/{concern_id}/review", response_model=ComplaintDetailOut)
def review_concern(
    concern_id: str, payload: ReviewRequest, user: Reviewer, db: DbSession, settings: AppSettings
) -> ComplaintDetailOut:
    c = complaint_service.review(
        db,
        settings,
        user,
        concern_id,
        payload.action,
        category=payload.category,
        priority=payload.priority,
        target_user_id=payload.target_user_id,
        remarks=payload.remarks,
    )
    return _detail(db, c, settings)


@router.post("/{concern_id}/simulate_breach", response_model=ComplaintDetailOut)
def simulate_breach(
    concern_id: str,
    user: SystemOperator,
    db: DbSession,
    settings: AppSettings,
    _demo: Annotated[None, Depends(_require_demo_mode)],
) -> ComplaintDetailOut:
    return _detail(db, complaint_service.simulate_breach(db, user, concern_id), settings)
