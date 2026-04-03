"""slot_index not null on assignments

Revision ID: c3f4a1b2d8e0
Revises: b76286bc7620
Create Date: 2026-03-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c3f4a1b2d8e0'
down_revision: Union[str, Sequence[str], None] = 'b76286bc7620'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text('UPDATE assignments SET slot_index = 0 WHERE slot_index IS NULL'))
    op.alter_column(
        'assignments',
        'slot_index',
        existing_type=sa.Integer(),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        'assignments',
        'slot_index',
        existing_type=sa.Integer(),
        nullable=True,
    )
