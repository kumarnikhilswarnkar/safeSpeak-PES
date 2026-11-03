"""add users.phone and users.photo_filename (self-service profile)

Revision ID: d4e8b1f27a90
Revises: c7e4a9d2b310
Create Date: 2026-10-12 12:00:00.000000

Both columns are nullable and have no default, so existing accounts are unchanged.
The photo itself is stored on disk (MEDIA_DIR), never in the database; the column
holds only the server-generated file name.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e8b1f27a90'
down_revision: Union[str, Sequence[str], None] = 'c7e4a9d2b310'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('phone', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('photo_filename', sa.String(length=80), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('photo_filename')
        batch_op.drop_column('phone')
