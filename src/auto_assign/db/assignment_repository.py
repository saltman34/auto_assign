'''Transactional replace of assignment rows for one (work_date, time_slot) slice.'''

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from auto_assign.db.adapters import assignment_from_record
from auto_assign.db.models.assignment_record import AssignmentRecord
from auto_assign.db.models.technician import Technician
from auto_assign.domain import Assignment
from auto_assign.domain.enums import AssignmentStatus, TimeSlot


def _sorted_assignments(assignments: Sequence[Assignment]) -> list[Assignment]:
    return sorted(assignments, key=lambda a: (a.task_name, a.technician_id))


def _records_for_slice(
    assignments: Sequence[Assignment],
    *,
    status: AssignmentStatus,
) -> list[AssignmentRecord]:
    rows: list[AssignmentRecord] = []
    for slot_index, a in enumerate(_sorted_assignments(assignments)):
        rows.append(
            AssignmentRecord(
                technician_id=a.technician_id,
                task_id=a.task_name,
                work_date=a.date_assigned,
                time_slot=a.time_slot,
                status=status,
                slot_index=slot_index,
            )
        )
    return rows


def replace_draft_slice(
    session: Session,
    work_date: date,
    time_slot: TimeSlot,
    assignments: Sequence[Assignment],
) -> None:
    '''
    Delete all **draft** rows for ``(work_date, time_slot)``, then insert ``assignments`` as draft.
    '''
    session.execute(
        delete(AssignmentRecord).where(
            AssignmentRecord.work_date == work_date,
            AssignmentRecord.time_slot == time_slot,
            AssignmentRecord.status == AssignmentStatus.DRAFT,
        )
    )
    for rec in _records_for_slice(assignments, status=AssignmentStatus.DRAFT):
        session.add(rec)


def confirm_slice(
    session: Session,
    work_date: date,
    time_slot: TimeSlot,
    assignments: Sequence[Assignment],
) -> None:
    '''
    Atomically replace the published slice: delete **draft and confirmed** for
    ``(work_date, time_slot)``, then insert ``assignments`` as **confirmed**.
    '''
    session.execute(
        delete(AssignmentRecord).where(
            AssignmentRecord.work_date == work_date,
            AssignmentRecord.time_slot == time_slot,
            AssignmentRecord.status.in_((AssignmentStatus.DRAFT, AssignmentStatus.CONFIRMED)),
        )
    )
    for rec in _records_for_slice(assignments, status=AssignmentStatus.CONFIRMED):
        session.add(rec)


def count_confirmed_for_slice(
    session: Session,
    work_date: date,
    time_slot: TimeSlot,
) -> int:
    '''Number of **confirmed** rows for the slice (for pre-confirm overwrite warning).'''
    stmt = select(func.count()).select_from(AssignmentRecord).where(
        AssignmentRecord.work_date == work_date,
        AssignmentRecord.time_slot == time_slot,
        AssignmentRecord.status == AssignmentStatus.CONFIRMED,
    )
    return int(session.scalar(stmt) or 0)


def load_draft_assignments_for_slice(
    session: Session,
    work_date: date,
    time_slot: TimeSlot,
) -> tuple[Assignment, ...]:
    '''
    Load **draft** rows for ``(work_date, time_slot)`` as domain ``Assignment`` tuples,
    ordered by ``slot_index`` then ``id`` (stable display / confirm order).
    '''
    stmt = (
        select(AssignmentRecord)
        .where(
            AssignmentRecord.work_date == work_date,
            AssignmentRecord.time_slot == time_slot,
            AssignmentRecord.status == AssignmentStatus.DRAFT,
        )
        .order_by(AssignmentRecord.slot_index, AssignmentRecord.id)
    )
    records = session.scalars(stmt).all()
    return tuple(assignment_from_record(r) for r in records)


def technician_ids_missing_from_db(
    session: Session,
    technician_ids: Iterable[str],
) -> list[str]:
    '''
    Return ``tech_id`` values that do not exist in ``technicians`` (preserves first-seen order,
    deduplicated). Empty list means every id is safe for FK inserts on ``assignments``.
    '''
    unique: list[str] = []
    seen: set[str] = set()
    for tid in technician_ids:
        if tid in seen:
            continue
        seen.add(tid)
        unique.append(tid)
    if not unique:
        return []
    stmt = select(Technician.tech_id).where(Technician.tech_id.in_(unique))
    found = set(session.scalars(stmt).all())
    return [tid for tid in unique if tid not in found]
