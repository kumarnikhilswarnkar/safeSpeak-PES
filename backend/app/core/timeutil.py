"""Time helpers. The database stores UTC; conversion to local time happens only for display."""
from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def utcnow() -> datetime:
    return datetime.now(UTC)


def to_display_tz(value: datetime, tz: ZoneInfo) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Naive datetimes are not allowed; store and pass UTC-aware values")
    return value.astimezone(tz)
