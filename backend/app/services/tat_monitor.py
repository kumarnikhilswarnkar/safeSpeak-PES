"""Automatic TAT monitoring.

A background asyncio task inside the API process wakes up every
TAT_MONITOR_INTERVAL_SECONDS, finds open complaints whose deadline has passed,
and escalates them through complaint_service.escalate_overdue (system actor, so
the audit trail shows "System (automatic TAT monitor)").

Design notes:
- No Redis/Celery: one lightweight loop is enough for one API process. Run the
  API with a single worker so only one monitor exists.
- A lock serialises the automatic run and the administrator's "run check now",
  so the same overdue complaint can never be escalated twice by overlapping runs.
  escalate_overdue itself is idempotent: an escalated complaint gets a new future
  deadline, and an exhausted one is marked breached_at_top and never picked again.
- The database work runs in a worker thread (asyncio.to_thread) so the event loop
  keeps serving requests.
"""
import asyncio
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from app.core.timeutil import utcnow
from app.models import User
from app.services import complaint_service

logger = logging.getLogger("safespeak.tat_monitor")

RECENT_RUNS = 20


@dataclass
class MonitorRun:
    started_at: datetime
    finished_at: datetime
    trigger: str  # "automatic" | "manual"
    processed: int
    escalated: list[str]
    exhausted: list[str]
    error: str | None = None
    outcomes: list = field(default_factory=list)


@dataclass
class TatMonitor:
    session_factory: sessionmaker[Session]
    interval_seconds: int
    enabled: bool
    started_at: datetime | None = None
    next_run_at: datetime | None = None
    runs: list[MonitorRun] = field(default_factory=list)
    total_runs: int = 0
    total_escalated: int = 0
    total_exhausted: int = 0

    def __post_init__(self) -> None:
        self._lock = threading.Lock()
        self._task: asyncio.Task | None = None

    # --- one check ------------------------------------------------------------------

    def run_once(
        self, triggered_by: User | None = None, now: datetime | None = None, *, raise_errors: bool = False
    ) -> MonitorRun:
        """Check and escalate now. triggered_by=None means the automatic monitor;
        raise_errors=True for a manual run, so the administrator sees the failure."""
        with self._lock:
            started = utcnow()
            run = MonitorRun(started, started, "manual" if triggered_by else "automatic", 0, [], [])
            try:
                with self.session_factory() as db:
                    actor = db.get(User, triggered_by.id) if triggered_by else None
                    outcomes = complaint_service.escalate_overdue(db, actor, now)
                run.outcomes = outcomes
                run.processed = len(outcomes)
                run.escalated = [o.complaint_code for o in outcomes if o.result == "escalated"]
                run.exhausted = [o.complaint_code for o in outcomes if o.result == "exhausted"]
                if outcomes:
                    logger.info("TAT check (%s): %d escalated, %d exhausted", run.trigger, len(run.escalated), len(run.exhausted))
            except Exception as exc:  # keep the monitor alive; surface the error on the status page
                logger.exception("TAT check failed")
                run.error = f"{type(exc).__name__}: {exc}"
                if raise_errors:
                    raise
            finally:
                run.finished_at = utcnow()
                self._record(run)
            return run

    def _record(self, run: MonitorRun) -> None:
        self.total_runs += 1
        self.total_escalated += len(run.escalated)
        self.total_exhausted += len(run.exhausted)
        self.runs = [run, *self.runs][:RECENT_RUNS]

    # --- background loop -------------------------------------------------------------

    async def _loop(self) -> None:
        while True:
            self.next_run_at = utcnow() + timedelta(seconds=self.interval_seconds)
            await asyncio.sleep(self.interval_seconds)
            await asyncio.to_thread(self.run_once)

    def start(self) -> None:
        if not self.enabled or self._task is not None:
            return
        self.started_at = utcnow()
        self._task = asyncio.get_running_loop().create_task(self._loop(), name="tat-monitor")
        logger.info("Automatic TAT monitor started (every %ss)", self.interval_seconds)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        self.next_run_at = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def last_run(self) -> MonitorRun | None:
        return self.runs[0] if self.runs else None

    @property
    def last_automatic_run(self) -> MonitorRun | None:
        return next((r for r in self.runs if r.trigger == "automatic"), None)
