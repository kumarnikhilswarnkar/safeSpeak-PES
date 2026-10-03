from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, insert, select, text
from sqlalchemy.exc import StatementError

from app.db.session import create_db_engine
from app.db.types import UTCDateTime

IST = timezone(timedelta(hours=5, minutes=30))


@pytest.fixture
def engine(tmp_path):
    engine = create_db_engine(f"sqlite:///{(tmp_path / 'types.db').as_posix()}")
    yield engine
    engine.dispose()


@pytest.fixture
def events(engine):
    table = Table("events", MetaData(), Column("id", Integer, primary_key=True), Column("at", UTCDateTime))
    table.metadata.create_all(engine)
    return table


def test_aware_datetime_round_trips_as_utc(engine, events):
    ist_value = datetime(2026, 10, 5, 10, 30, tzinfo=IST)
    with engine.begin() as conn:
        conn.execute(insert(events).values(id=1, at=ist_value))
        stored = conn.execute(select(events.c.at)).scalar_one()

    assert stored.tzinfo == UTC
    assert stored == ist_value
    assert stored.hour == 5


def test_naive_datetime_is_rejected(engine, events):
    with pytest.raises(StatementError), engine.begin() as conn:
        conn.execute(insert(events).values(id=1, at=datetime(2026, 10, 5, 10, 30)))


def test_sqlite_foreign_keys_are_enforced(engine):
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
