"""profile_only_technicians

Revision ID: 7d8e9f10a1b2
Revises: c3f4a1b2d8e0
Create Date: 2026-04-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '7d8e9f10a1b2'
down_revision: Union[str, Sequence[str], None] = 'c3f4a1b2d8e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('technicians', 'staff_status')
    op.drop_column('technicians', 'available_pm')
    op.drop_column('technicians', 'available_mid')
    op.drop_column('technicians', 'available_am')


def downgrade() -> None:
    op.add_column(
        'technicians',
        sa.Column(
            'available_am',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
        ),
    )
    op.add_column(
        'technicians',
        sa.Column(
            'available_mid',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
        ),
    )
    op.add_column(
        'technicians',
        sa.Column(
            'available_pm',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
        ),
    )
    op.add_column(
        'technicians',
        sa.Column(
            'staff_status',
            sa.Enum(
                'scheduled',
                'call_off',
                'overtime',
                name='staffing_status',
                native_enum=False,
                length=32,
            ),
            nullable=False,
            server_default='scheduled',
        ),
    )
