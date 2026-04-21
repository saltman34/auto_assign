"""technician eligibility/proficiency maps; assignments.catalog_task_id

Revision ID: d4e5f6a7b8c9
Revises: f17e3dc9a8b1
Create Date: 2026-04-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'f17e3dc9a8b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'technicians',
        sa.Column(
            'eligible_by_task_id',
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column(
        'technicians',
        sa.Column(
            'proficiency_by_task_id',
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column('assignments', sa.Column('catalog_task_id', sa.String(128), nullable=True))


def downgrade() -> None:
    op.drop_column('assignments', 'catalog_task_id')
    op.drop_column('technicians', 'proficiency_by_task_id')
    op.drop_column('technicians', 'eligible_by_task_id')
