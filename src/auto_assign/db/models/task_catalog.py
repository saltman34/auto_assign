'''
ORM model for the task catalog used by assignment headcounts and preference validation.
'''
from __future__ import annotations

from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from auto_assign.db.base import Base


class TaskCatalog(Base):
    __tablename__ = 'tasks'
    __table_args__ = (UniqueConstraint('task_name', name='uq_tasks_task_name'),)

    task_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    task_name: Mapped[str] = mapped_column(String(256), nullable=False)
    default_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
