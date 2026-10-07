"""Dashboards, notifications, model evaluation and automation status.

All numbers come from the live database or from the evaluation reports written by
ml/scripts/run_experiments.py (ml/reports/v3); nothing here is hard-coded."""
import json
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import AppSettings, CurrentUser, DbSession, require_permission
from app.core.permissions import Permission, has_permission
from app.models import EscalationRule, TATRule, User
from app.services import analytics_service
from app.services.tat_monitor import MonitorRun
from app.services.triage_service import effective_priority_threshold, effective_threshold

router = APIRouter(tags=["insights"])

SystemOperator = Annotated[User, Depends(require_permission(Permission.MANAGE_RULES_AND_SETTINGS))]


REPORT_FILES = ("model_comparison", "selection", "calibration", "thresholds", "holdout_results",
                "dataset_info", "reproducibility")


def _model_info(request: Request, settings) -> tuple[float | None, str | None, str | None]:
    model = request.app.state.triage_model
    if model is None:
        return None, None, None
    threshold, source = effective_threshold(settings, model)
    return threshold, source, f"{model.name}:{model.version}"


def _research_payload(reports: dict[str, Any]) -> dict[str, Any]:
    """The parts of the v3 reports the research page shows (the full files stay in ml/reports/v3)."""
    tasks = {}
    for task, rows in reports["model_comparison"]["tasks"].items():
        selected = reports["selection"][task]["selected"]
        holdout = reports["holdout_results"][task]
        th = reports["thresholds"][task]
        tasks[task] = {
            "comparison": rows,
            "selection": reports["selection"][task],
            "calibration": reports["calibration"][task]["models"][selected],
            "holdout_calibration": holdout["selected_model_details"]["calibration"],
            "thresholds": {k: th[k] for k in ("threshold", "rule", "met", "at_threshold", "report_table",
                                              "holdout_table", "calibration_method", "curve")},
            "selected_holdout": holdout["models"][selected],
            "keyword_holdout": holdout["models"].get("keyword_baseline"),
        }
    return {
        "version": "v3",
        "dataset": reports["dataset_info"],
        "setfit_pilot": reports["model_comparison"].get("setfit_pilot"),
        "protocol": {
            "cv": "5 folds x 5 repeats, StratifiedGroupKFold (paraphrase groups never split)",
            "holdout": "40 whole groups (120 records), used once after all decisions",
            "selection_rule": reports["selection"]["category"]["rule"],
        },
        "reproducibility": {k: reports["reproducibility"].get(k) for k in ("command", "packages", "seeds", "checksums")},
        "tasks": tasks,
    }


@router.get("/analytics/overview")
def analytics_overview(request: Request, user: CurrentUser, db: DbSession, settings: AppSettings) -> dict[str, Any]:
    threshold, _source, model = _model_info(request, settings)
    return analytics_service.overview(db, user, threshold, model)


@router.get("/notifications")
def my_notifications(user: CurrentUser, db: DbSession) -> list[dict[str, Any]]:
    return analytics_service.notifications(db, user)


@router.get("/research/evaluation")
def research_evaluation(request: Request, _user: CurrentUser, settings: AppSettings) -> dict[str, Any]:
    """The offline v3 evaluation (synthetic dataset) plus the model and thresholds
    the API is using right now."""
    try:
        reports = {name: json.loads((settings.reports_dir / f"{name}.json").read_text(encoding="utf-8"))
                   for name in REPORT_FILES}
        payload = _research_payload(reports)
    except (OSError, ValueError, KeyError):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evaluation reports not found; run ml/scripts/run_experiments.py") from None
    threshold, source, model = _model_info(request, settings)
    live_model = request.app.state.triage_model
    priority_threshold, priority_source = (
        effective_priority_threshold(settings, live_model) if live_model is not None else (None, None))
    return {
        **payload,
        "live": {
            "model": model,
            "threshold": threshold,
            "threshold_source": source,
            "priority_threshold": priority_threshold,
            "priority_threshold_source": priority_source,
            "review_high_severity": settings.review_high_severity,
        },
    }


class MonitorRunOut(BaseModel):
    started_at: datetime
    finished_at: datetime
    trigger: str
    processed: int
    escalated: list[str]
    exhausted: list[str]
    error: str | None


class AutomationOut(BaseModel):
    enabled: bool
    running: bool
    interval_seconds: int
    started_at: datetime | None
    last_run_at: datetime | None
    last_automatic_run_at: datetime | None
    next_run_at: datetime | None
    total_runs: int
    total_escalated: int
    total_exhausted: int
    recent_runs: list[MonitorRunOut]


def _run_out(run: MonitorRun, show_codes: bool) -> MonitorRunOut:
    return MonitorRunOut(
        started_at=run.started_at,
        finished_at=run.finished_at,
        trigger=run.trigger,
        processed=run.processed,
        escalated=run.escalated if show_codes else [],
        exhausted=run.exhausted if show_codes else [],
        error=run.error if show_codes else None,
    )


def _automation(request: Request, user: User) -> AutomationOut:
    m = request.app.state.tat_monitor
    # Complaint codes in run results are only shown to administrators.
    show_codes = has_permission(user.role, Permission.MANAGE_RULES_AND_SETTINGS)
    return AutomationOut(
        enabled=m.enabled,
        running=m.running,
        interval_seconds=m.interval_seconds,
        started_at=m.started_at,
        last_run_at=m.last_run.finished_at if m.last_run else None,
        last_automatic_run_at=m.last_automatic_run.finished_at if m.last_automatic_run else None,
        next_run_at=m.next_run_at if m.running else None,
        total_runs=m.total_runs,
        total_escalated=m.total_escalated,
        total_exhausted=m.total_exhausted,
        recent_runs=[_run_out(r, show_codes) for r in m.runs],
    )


@router.get("/system/automation", response_model=AutomationOut)
def automation_status(request: Request, user: CurrentUser) -> AutomationOut:
    return _automation(request, user)


@router.post("/system/automation/run", response_model=AutomationOut)
def automation_run_now(request: Request, user: SystemOperator) -> AutomationOut:
    """Run the same check the automatic monitor runs, immediately."""
    request.app.state.tat_monitor.run_once(user, raise_errors=True)
    return _automation(request, user)


@router.get("/system/rules")
def workflow_rules(_user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """The configured TAT rules and escalation chains (read-only). They are
    database rows, so changing them needs no code change."""
    tat = db.scalars(select(TATRule).where(TATRule.is_active.is_(True)).order_by(TATRule.stage, TATRule.id)).all()
    chains = db.scalars(
        select(EscalationRule)
        .where(EscalationRule.is_active.is_(True))
        .options(selectinload(EscalationRule.target_department))
        .order_by(EscalationRule.category, EscalationRule.escalation_level)
    ).all()
    return {
        "tat_rules": [
            {
                "id": r.id, "stage": r.stage, "category": r.category, "priority": r.priority,
                "escalation_level": r.escalation_level, "tat_hours": r.tat_hours, "note": r.note,
            }
            for r in tat
        ],
        "escalation_rules": [
            {
                "id": r.id, "category": r.category, "level": r.escalation_level, "label": r.label,
                "target_role": r.target_role, "target_authority_level": r.target_authority_level,
                "target_scope": r.target_scope,
                "target_department": r.target_department.code if r.target_department else None,
            }
            for r in chains
        ],
    }
