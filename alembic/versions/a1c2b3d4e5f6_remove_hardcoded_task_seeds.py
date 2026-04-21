"""remove hardcoded task catalog seed rows

Revision ID: a1c2b3d4e5f6
Revises: e7a9c0d3b1f2
Create Date: 2026-04-21

An earlier revision of ``e8b7c2d1f4a9`` inserted six task rows with numeric
string ids (``'1'``..``'6'``) directly from a migration. Those rows collide
with the demo seeder (``auto_assign.demo.seed``), which owns task-catalog data
and uses stable ``T-*`` ids (e.g. ``T-CLIN``). The unique constraint on
``task_name`` causes the seeder's INSERTs to fail on any DB that has the
legacy rows.

This migration deletes just those six rows by id. There is no FK from
``assignments.catalog_task_id`` to ``tasks.task_id`` (it is a plain string
column), so the delete is always safe. Fresh databases are unaffected.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1c2b3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'e7a9c0d3b1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_LEGACY_TASK_IDS = ('1', '2', '3', '4', '5', '6')


def upgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM tasks WHERE task_id IN ('1','2','3','4','5','6')"
        )
    )


def downgrade() -> None:
    # Restoring the legacy seed rows would just reintroduce the unique-name
    # collision with the demo seeder, so downgrade is a no-op.
    pass
