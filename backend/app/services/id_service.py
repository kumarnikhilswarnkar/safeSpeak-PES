"""Complaint codes: SSP-YYYY-NNNNNN, from a per-year counter in the database."""
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import update
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from app.models import IdCounter

PREFIX = "SSP"


def next_complaint_code(db: Session, now: datetime, tz: ZoneInfo) -> str:
    """Reserve the next number for the year (in the display timezone).

    The increment is a single UPDATE ... RETURNING inside the caller's
    transaction, so two submissions can never receive the same number; the
    UNIQUE constraint on complaints.complaint_code is a final safeguard.
    """
    year = now.astimezone(tz).year
    dialect = db.get_bind().dialect.name
    insert = {"sqlite": sqlite.insert, "postgresql": postgresql.insert}.get(dialect)
    if insert is None:
        raise RuntimeError(f"Unsupported database dialect for complaint codes: {dialect}")

    db.execute(insert(IdCounter).values(year=year, last_value=0).on_conflict_do_nothing(index_elements=["year"]))
    number = db.execute(
        update(IdCounter)
        .where(IdCounter.year == year)
        .values(last_value=IdCounter.last_value + 1)
        .returning(IdCounter.last_value)
    ).scalar_one()
    return f"{PREFIX}-{year}-{number:06d}"
