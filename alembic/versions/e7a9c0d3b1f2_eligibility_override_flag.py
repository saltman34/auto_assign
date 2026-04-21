"""eligibility_overridden flag on assignments + assignment_overrides

Revision ID: e7a9c0d3b1f2
Revises: d4e5f6a7b8c9
Create Date: 2026-04-17

Adds a boolean ``eligibility_overridden`` column to both ``assignments`` and
``assignment_overrides`` so a manual pre-assignment that places a tech the
catalog flags as ineligible (e.g. training / shadowing) can be persisted
explicitly and audited. Existing rows backfill to ``False`` via server default.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e7a9c0d3b1f2'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'assignments',
        sa.Column(
            'eligibility_overridden',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        'assignment_overrides',
        sa.Column(
            'eligibility_overridden',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column('assignment_overrides', 'eligibility_overridden')
    op.drop_column('assignments', 'eligibility_overridden')
