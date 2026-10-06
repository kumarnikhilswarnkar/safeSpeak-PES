"""Append-only audit trail enforced by the database

Revision ID: c7e4a9d2b310
Revises: b5d2e8f41c07
Create Date: 2026-10-06 15:10:00.000000

The application already refuses to update or delete ai_predictions and
complaint_events rows (ORM hooks). These triggers make the database itself
refuse it too, so a script, a console session or a bug that bypasses the ORM
cannot silently rewrite the audit trail or the original AI recommendation.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c7e4a9d2b310'
down_revision: Union[str, Sequence[str], None] = 'b5d2e8f41c07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ('ai_predictions', 'complaint_events')


def upgrade() -> None:
    """Upgrade schema."""
    if op.get_bind().dialect.name == 'postgresql':
        op.execute(
            """
            CREATE OR REPLACE FUNCTION safespeak_refuse_change() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION '% rows are append-only and cannot be modified or deleted', TG_TABLE_NAME
                    USING ERRCODE = 'insufficient_privilege';
            END
            $$;
            """
        )
        for table in TABLES:
            op.execute(
                f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON {table} "
                f"FOR EACH ROW EXECUTE FUNCTION safespeak_refuse_change()"
            )
            op.execute(
                f"CREATE TRIGGER trg_{table}_no_truncate BEFORE TRUNCATE ON {table} "
                f"FOR EACH STATEMENT EXECUTE FUNCTION safespeak_refuse_change()"
            )
    else:  # SQLite (development and tests)
        for table in TABLES:
            for event in ('UPDATE', 'DELETE'):
                op.execute(
                    f"CREATE TRIGGER trg_{table}_no_{event.lower()} BEFORE {event} ON {table} "
                    f"BEGIN SELECT RAISE(ABORT, '{table} rows are append-only and cannot be modified or deleted'); END"
                )


def downgrade() -> None:
    """Downgrade schema."""
    if op.get_bind().dialect.name == 'postgresql':
        for table in TABLES:
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_no_truncate ON {table}")
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_append_only ON {table}")
        op.execute("DROP FUNCTION IF EXISTS safespeak_refuse_change()")
    else:
        for table in TABLES:
            for event in ('update', 'delete'):
                op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_no_{event}")
