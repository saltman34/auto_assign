"""add tasks catalog table

Revision ID: e8b7c2d1f4a9
Revises: 7d8e9f10a1b2
Create Date: 2026-04-09

Creates the ``tasks`` catalog table. Task rows are managed by the demo seeder
(``auto_assign.demo.seed``) or real operator input — not by migrations — so this
migration intentionally inserts no rows. A follow-up migration
(``a1c2b3d4e5f6``) cleans up legacy seed rows left behind by earlier revisions
of this file.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e8b7c2d1f4a9'
down_revision: Union[str, Sequence[str], None] = '7d8e9f10a1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tasks',
        sa.Column('task_id', sa.String(length=128), nullable=False),
        sa.Column('task_name', sa.String(length=256), nullable=False),
        sa.Column('default_count', sa.Integer(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('task_id'),
        sa.UniqueConstraint('task_name', name='uq_tasks_task_name'),
    )


def downgrade() -> None:
    op.drop_table('tasks')
