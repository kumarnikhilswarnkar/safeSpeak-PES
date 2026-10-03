"""Liveness and database connectivity check."""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import __version__
from app.core.timeutil import utcnow
from app.db.session import get_db

router = APIRouter(tags=["system"])


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]
    environment: str
    version: str
    server_time_utc: datetime


@router.get("/health", response_model=HealthOut)
def health(request: Request, response: Response, db: Session = Depends(get_db)) -> HealthOut:
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except SQLAlchemyError:
        database = "unavailable"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthOut(
        status="ok" if database == "ok" else "degraded",
        database=database,
        environment=request.app.state.settings.environment,
        version=__version__,
        server_time_utc=utcnow(),
    )
