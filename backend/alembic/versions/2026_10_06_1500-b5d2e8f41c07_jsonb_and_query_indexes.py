"""JSONB on PostgreSQL and query indexes

Revision ID: b5d2e8f41c07
Revises: a3c91d5e7b20
Create Date: 2026-10-06 15:00:00.000000

Additive only. On PostgreSQL the JSON document columns become JSONB; SQLite
keeps JSON. Indexes support reviewer queues, the TAT monitor scan, scoped
lists, notifications, and one active escalation rule per chain level.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b5d2e8f41c07'
down_revision: Union[str, Sequence[str], None] = 'a3c91d5e7b20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSON_COLUMNS = [
    ('complaints', 'review_reasons', False),
    ('ai_predictions', 'flag_reasons', False),
    ('ai_predictions', 'probabilities', False),
    ('ai_predictions', 'explanation', True),
    ('complaint_events', 'previous_value', True),
    ('complaint_events', 'new_value', True),
]
OPEN_NOT_EXHAUSTED = "status IN ('PENDING_REVIEW', 'ASSIGNED', 'IN_PROGRESS') AND breached_at_top = false"


def upgrade() -> None:
    """Upgrade schema."""
    if op.get_bind().dialect.name == 'postgresql':
        for table, column, nullable in JSON_COLUMNS:
            op.alter_column(
                table, column,
                existing_type=sa.JSON(), type_=postgresql.JSONB(),
                existing_nullable=nullable, postgresql_using=f'{column}::jsonb',
            )

    op.create_index('ix_complaints_complainant_department_id', 'complaints', ['complainant_department_id'])
    op.create_index('ix_complaints_handling_department_id', 'complaints', ['handling_department_id'])
    op.create_index('ix_complaints_assigned_user_status', 'complaints', ['assigned_user_id', 'status'])
    op.create_index(
        'ix_complaints_open_deadline', 'complaints', ['deadline_at'],
        postgresql_where=sa.text(OPEN_NOT_EXHAUSTED), sqlite_where=sa.text(OPEN_NOT_EXHAUSTED),
    )
    op.create_index('ix_complaint_events_created_at', 'complaint_events', ['created_at'])
    op.create_index(
        'uq_escalation_rules_active_chain_level', 'escalation_rules',
        [sa.text("coalesce(category, '')"), 'escalation_level'], unique=True,
        postgresql_where=sa.text('is_active'), sqlite_where=sa.text('is_active'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_escalation_rules_active_chain_level', table_name='escalation_rules')
    op.drop_index('ix_complaint_events_created_at', table_name='complaint_events')
    op.drop_index('ix_complaints_open_deadline', table_name='complaints')
    op.drop_index('ix_complaints_assigned_user_status', table_name='complaints')
    op.drop_index('ix_complaints_handling_department_id', table_name='complaints')
    op.drop_index('ix_complaints_complainant_department_id', table_name='complaints')

    if op.get_bind().dialect.name == 'postgresql':
        for table, column, nullable in JSON_COLUMNS:
            op.alter_column(
                table, column,
                existing_type=postgresql.JSONB(), type_=sa.JSON(),
                existing_nullable=nullable, postgresql_using=f'{column}::json',
            )
