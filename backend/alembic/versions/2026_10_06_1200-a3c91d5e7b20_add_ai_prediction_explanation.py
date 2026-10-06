"""add ai_predictions.explanation

Revision ID: a3c91d5e7b20
Revises: f0ec376ae4d3
Create Date: 2026-10-06 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3c91d5e7b20'
down_revision: Union[str, Sequence[str], None] = 'f0ec376ae4d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: nullable, so existing predictions are unchanged."""
    with op.batch_alter_table('ai_predictions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('explanation', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('ai_predictions', schema=None) as batch_op:
        batch_op.drop_column('explanation')
