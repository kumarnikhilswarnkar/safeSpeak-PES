"""FastAPI application factory.

Run locally from the backend folder:
    uvicorn app.main:app --reload
"""
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.db.session import create_db_engine, create_session_factory
from app.services.errors import WorkflowError
from app.services.tat_monitor import TatMonitor
from app.services.triage_service import TriageModelError, load_triage_model

logger = logging.getLogger("safespeak")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine = create_db_engine(settings.database_url)

    if not settings.email_domains:
        logger.warning("ALLOWED_EMAIL_DOMAINS is empty: every sign-in attempt will be refused (503).")
    if settings.demo_mode:
        logger.warning("DEMO_MODE is on: demo-only endpoints (TAT breach simulation) are enabled.")

    try:
        triage_model = load_triage_model(settings)
    except TriageModelError as exc:
        # The API still starts (sign-in, reading complaints), but submissions are refused with 503.
        logger.error("AI triage model not loaded: %s", exc)
        triage_model = None

    session_factory = create_session_factory(engine)
    tat_monitor = TatMonitor(
        session_factory=session_factory,
        interval_seconds=settings.tat_monitor_interval_seconds,
        enabled=settings.tat_monitor_enabled,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        tat_monitor.start()
        yield
        await tat_monitor.stop()
        engine.dispose()

    app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.triage_model = triage_model
    app.state.tat_monitor = tat_monitor

    @app.exception_handler(WorkflowError)
    async def workflow_error_handler(_request: Request, exc: WorkflowError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
