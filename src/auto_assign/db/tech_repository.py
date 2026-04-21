'''
Persist domain ``Tech`` rows (upsert by ``tech_id``).
'''
from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import Executable

from auto_assign.db.adapters import technician_from_tech, tech_from_technician
from auto_assign.db.models.assignment_record import AssignmentRecord
from auto_assign.db.models.technician import Technician
from auto_assign.domain.entities import Tech


def _delete_rowcount(session: Session, stmt: Executable) -> int:
    '''Best-effort deleted row count (SQLAlchemy ``Result.rowcount`` is driver-dependent).'''
    result = session.execute(stmt)
    rc = getattr(result, 'rowcount', None)
    if isinstance(rc, int) and rc >= 0:
        return rc
    return 0


def list_technicians(session: Session) -> list[Tech]:
    '''All technicians as domain ``Tech``, ordered by ``tech_id``.'''
    rows = session.scalars(select(Technician).order_by(Technician.tech_id)).all()
    return [tech_from_technician(r) for r in rows]


def count_assignments_for_technician(session: Session, tech_id: str) -> int:
    stmt = select(func.count()).select_from(AssignmentRecord).where(
        AssignmentRecord.technician_id == tech_id,
    )
    return int(session.scalar(stmt) or 0)


def delete_technician(session: Session, tech_id: str) -> tuple[int, int]:
    '''
    Remove ``tech_id`` and every ``assignments`` row that references them (FK is RESTRICT).

    Returns:
        ``(assignments_removed, technicians_removed)`` — second value is ``0`` or ``1``.
    '''
    n_assign = _delete_rowcount(
        session,
        delete(AssignmentRecord).where(AssignmentRecord.technician_id == tech_id),
    )
    row = session.get(Technician, tech_id)
    n_tech = 0
    if row is not None:
        session.delete(row)
        n_tech = 1
    return n_assign, n_tech


def delete_all_technicians(session: Session) -> tuple[int, int]:
    '''
    Delete all assignment rows, then all technicians.

    Returns:
        ``(assignments_removed, technicians_removed)``.
    '''
    n_a = _delete_rowcount(session, delete(AssignmentRecord))
    n_t = _delete_rowcount(session, delete(Technician))
    return n_a, n_t


def merge_technician_from_tech(session: Session, tech: Tech) -> Technician:
    '''
    Insert or update a ``Technician`` row keyed by ``tech.tech_id``.
    '''
    existing = session.get(Technician, tech.tech_id)
    if existing is None:
        row = technician_from_tech(tech)
        session.add(row)
        session.flush()
        return row

    existing.tech_name = tech.tech_name
    existing.daily_preference = tech.daily_preference
    existing.favorites = list(tech.favorites)
    existing.dislikes = list(tech.dislikes)
    existing.eligible_by_task_id = dict(tech.eligible_by_task_id)
    existing.proficiency_by_task_id = {k: v.value for k, v in tech.proficiency_by_task_id.items()}
    return existing


def upsert_technicians(session: Session, techs: Iterable[Tech]) -> int:
    '''
    Upsert each ``Tech`` entity into the database; returns number processed.
    '''
    n = 0
    for t in techs:
        merge_technician_from_tech(session, t)
        n += 1
    return n


def load_tech_by_tech_id(session: Session, tech_id: str) -> Tech | None:
    '''Return the saved profile for ``tech_id``, or ``None`` if missing.'''
    row = session.get(Technician, tech_id)
    return tech_from_technician(row) if row is not None else None


def find_tech_id_for_normalized_tech_name(session: Session, normalized_name: str) -> str | None:
    '''
    Return ``tech_id`` for a row whose stored ``tech_name`` equals ``normalized_name`` (exact match).

    Callers should pass ``normalize_string(...)`` so comparison matches how profiles are stored.
    '''
    row = session.scalars(
        select(Technician).where(Technician.tech_name == normalized_name).limit(1)
    ).first()
    return row.tech_id if row is not None else None
