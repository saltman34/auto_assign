'''
Task catalog persistence helpers.
'''
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from auto_assign.db.models.assignment_record import AssignmentRecord
from auto_assign.db.models.task_catalog import TaskCatalog
from auto_assign.db.models.technician import Technician
from auto_assign.domain.entities import Task
from auto_assign.domain.validators.primitives import normalize_string


def _slugify_task_id(task_name: str) -> str:
    s = normalize_string(task_name).lower()
    s = re.sub(r'[^a-z0-9]+', '_', s).strip('_')
    if not s:
        raise ValueError('task_name must contain at least one letter or number')
    return s


def _next_available_task_id(session: Session, base_id: str) -> str:
    candidate = base_id
    n = 2
    while session.get(TaskCatalog, candidate) is not None:
        candidate = f'{base_id}_{n}'
        n += 1
    return candidate


def list_tasks(session: Session) -> list[Task]:
    '''All catalog tasks as domain ``Task`` objects, ordered by ``task_name``.'''
    rows = session.scalars(select(TaskCatalog).order_by(TaskCatalog.task_name)).all()
    return [
        Task(task_id=row.task_id, task_name=row.task_name, default_count=int(row.default_count))
        for row in rows
    ]


def create_task(session: Session, task_name: str, *, default_count: int = 0) -> TaskCatalog:
    '''
    Insert a new task row with a generated ``task_id`` based on the task name.

    ``task_name`` is normalized with the same title-case convention used in domain entities.
    '''
    name = normalize_string(task_name)
    if default_count < 0:
        raise ValueError('default_count must be >= 0')
    existing_name = session.scalars(select(TaskCatalog).where(TaskCatalog.task_name == name)).first()
    if existing_name is not None:
        raise ValueError(f'Task name already exists: {name!r}')
    task_id = _next_available_task_id(session, _slugify_task_id(name))
    row = TaskCatalog(task_id=task_id, task_name=name, default_count=int(default_count))
    session.add(row)
    session.flush()
    return row


def set_task_default_count(session: Session, task_id: str, default_count: int) -> TaskCatalog:
    '''Update ``default_count`` for one task.'''
    if default_count < 0:
        raise ValueError('default_count must be >= 0')
    row = session.get(TaskCatalog, task_id)
    if row is None:
        raise ValueError(f'Unknown task_id: {task_id}')
    row.default_count = int(default_count)
    return row


def delete_task(session: Session, task_id: str) -> int:
    '''
    Delete one task when it is not referenced by assignment history or technician preferences.

    Returns:
        ``1`` if deleted, ``0`` if no such task exists.
    '''
    row = session.get(TaskCatalog, task_id)
    if row is None:
        return 0

    used_in_assignments = int(
        session.query(AssignmentRecord).filter(AssignmentRecord.task_id == row.task_name).count()
    )
    if used_in_assignments > 0:
        raise ValueError(
            f'Cannot delete task {row.task_name!r}: it is used by {used_in_assignments} assignment row(s).'
        )

    tech_rows = session.scalars(select(Technician)).all()
    used_in_profiles = sum(
        1
        for t in tech_rows
        if row.task_name in (t.favorites or []) or row.task_name in (t.dislikes or [])
    )
    if used_in_profiles > 0:
        raise ValueError(
            f'Cannot delete task {row.task_name!r}: it is referenced in {used_in_profiles} technician profile(s).'
        )

    session.delete(row)
    session.flush()
    return 1
