"""add assignment overrides table

Revision ID: f17e3dc9a8b1
Revises: e8b7c2d1f4a9
Create Date: 2026-04-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f17e3dc9a8b1'
down_revision: Union[str, Sequence[str], None] = 'e8b7c2d1f4a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'assignment_overrides',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('work_date', sa.Date(), nullable=False),
        sa.Column(
            'time_slot',
            sa.Enum('AM', 'MID', 'PM', name='timeslot', native_enum=False, length=8),
            nullable=True,
        ),
        sa.Column(
            'scope',
            sa.Enum('day', 'slice', name='overridescope', native_enum=False, length=16),
            nullable=False,
        ),
        sa.Column(
            'kind',
            sa.Enum(
                'call_off',
                'overtime',
                'manual_assignment',
                name='overridekind',
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column('technician_id', sa.String(length=128), nullable=False),
        sa.Column('task_name', sa.String(length=256), nullable=True),
        sa.Column(
            'status',
            sa.Enum('draft', 'confirmed', name='assignmentstatus', native_enum=False, length=16),
            nullable=False,
        ),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['technician_id'], ['technicians.tech_id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_assignment_overrides_status_work_date',
        'assignment_overrides',
        ['status', 'work_date'],
        unique=False,
    )
    op.create_index(
        'ix_assignment_overrides_slice_lookup',
        'assignment_overrides',
        ['work_date', 'time_slot', 'status'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_assignment_overrides_slice_lookup', table_name='assignment_overrides')
    op.drop_index('ix_assignment_overrides_status_work_date', table_name='assignment_overrides')
    op.drop_table('assignment_overrides')
