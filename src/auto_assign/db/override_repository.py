'''Persistence helpers for manual override draft/audit rows.'''

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, datetime
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from auto_assign.db.models.assignment_override import AssignmentOverride
from auto_assign.domain import Assignment
from auto_assign.domain.enums import AssignmentStatus, OverrideKind, OverrideScope, TimeSlot


def _stable_unique(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for v in values:
        if v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


def replace_draft_day_availability_overrides(
    session: Session,
    work_date: date,
    *,
    call_off_tech_ids: Iterable[str],
    overtime_tech_ids_by_slot: dict[TimeSlot, Iterable[str]],
) -> None:
    '''
    Replace draft day-scope availability overrides (call-off/overtime) for ``work_date``.
    '''
    session.execute(
        delete(AssignmentOverride).where(
            AssignmentOverride.work_date == work_date,
            AssignmentOverride.scope == OverrideScope.DAY,
            AssignmentOverride.kind.in_((OverrideKind.CALL_OFF, OverrideKind.OVERTIME)),
            AssignmentOverride.status == AssignmentStatus.DRAFT,
        )
    )
    call_off = _stable_unique(call_off_tech_ids)
    overtime_by_slot = {
        slot: _stable_unique(ids)
        for slot, ids in overtime_tech_ids_by_slot.items()
    }
    overtime_any = {tid for ids in overtime_by_slot.values() for tid in ids}
    overlap = set(call_off) & overtime_any
    if overlap:
        raise ValueError(f'Tech cannot be both call-off and overtime on same day: {sorted(overlap)!r}')
    for tid in call_off:
        session.add(
            AssignmentOverride(
                work_date=work_date,
                time_slot=None,
                scope=OverrideScope.DAY,
                kind=OverrideKind.CALL_OFF,
                technician_id=tid,
                task_name=None,
                status=AssignmentStatus.DRAFT,
            )
        )
    for slot, tids in overtime_by_slot.items():
        for tid in tids:
            session.add(
                AssignmentOverride(
                    work_date=work_date,
                    time_slot=slot,
                    scope=OverrideScope.DAY,
                    kind=OverrideKind.OVERTIME,
                    technician_id=tid,
                    task_name=None,
                    status=AssignmentStatus.DRAFT,
                )
            )


def replace_draft_manual_assignments_for_slice(
    session: Session,
    work_date: date,
    time_slot: TimeSlot,
    assignments: Sequence[Assignment],
) -> None:
    '''
    Replace draft slice-scope manual pre-assignments for one ``(work_date, time_slot)``.
    '''
    session.execute(
        delete(AssignmentOverride).where(
            AssignmentOverride.work_date == work_date,
            AssignmentOverride.time_slot == time_slot,
            AssignmentOverride.scope == OverrideScope.SLICE,
            AssignmentOverride.kind == OverrideKind.MANUAL_ASSIGNMENT,
            AssignmentOverride.status == AssignmentStatus.DRAFT,
        )
    )
    seen_tech: set[str] = set()
    for a in assignments:
        if a.technician_id in seen_tech:
            raise ValueError(f'Duplicate technician in manual assignments: {a.technician_id!r}')
        seen_tech.add(a.technician_id)
        session.add(
            AssignmentOverride(
                work_date=work_date,
                time_slot=time_slot,
                scope=OverrideScope.SLICE,
                kind=OverrideKind.MANUAL_ASSIGNMENT,
                technician_id=a.technician_id,
                task_name=a.task_name,
                status=AssignmentStatus.DRAFT,
                eligibility_overridden=bool(a.eligibility_overridden),
            )
        )


def load_draft_overrides_for_slice(
    session: Session,
    work_date: date,
    time_slot: TimeSlot,
) -> dict[str, Any]:
    '''
    Draft overrides for one slice, including day-scope availability edits.
    '''
    stmt = (
        select(AssignmentOverride)
        .where(
            AssignmentOverride.work_date == work_date,
            AssignmentOverride.status == AssignmentStatus.DRAFT,
            (
                (AssignmentOverride.scope == OverrideScope.DAY)
                | (
                    (AssignmentOverride.scope == OverrideScope.SLICE)
                    & (AssignmentOverride.time_slot == time_slot)
                )
            ),
        )
        .order_by(AssignmentOverride.created_at, AssignmentOverride.id)
    )
    rows = session.scalars(stmt).all()
    call_off_ids: list[str] = []
    overtime_ids: list[str] = []
    overtime_by_slot: dict[TimeSlot, list[str]] = {s: [] for s in TimeSlot}
    manual: list[Assignment] = []
    for row in rows:
        if row.scope == OverrideScope.DAY and row.kind == OverrideKind.CALL_OFF:
            call_off_ids.append(row.technician_id)
        elif row.scope == OverrideScope.DAY and row.kind == OverrideKind.OVERTIME:
            if row.time_slot is None:
                overtime_ids.append(row.technician_id)
                for s in TimeSlot:
                    overtime_by_slot[s].append(row.technician_id)
            else:
                overtime_by_slot[row.time_slot].append(row.technician_id)
                if row.time_slot == time_slot:
                    overtime_ids.append(row.technician_id)
        elif row.scope == OverrideScope.SLICE and row.kind == OverrideKind.MANUAL_ASSIGNMENT:
            if row.task_name is None:
                continue
            manual.append(
                Assignment(
                    task_name=row.task_name,
                    technician_id=row.technician_id,
                    date_assigned=work_date,
                    time_slot=time_slot,
                    eligibility_overridden=bool(row.eligibility_overridden),
                )
            )
    return {
        'call_off_tech_ids': _stable_unique(call_off_ids),
        'overtime_tech_ids': _stable_unique(overtime_ids),
        'overtime_tech_ids_by_slot': {
            s.name: _stable_unique(ids) for s, ids in overtime_by_slot.items()
        },
        'manual_assignments': tuple(manual),
    }


def clear_draft_overrides_for_slice(
    session: Session,
    work_date: date,
    time_slot: TimeSlot,
) -> int:
    '''
    Remove draft overrides that apply to ``work_date`` (day scope) and ``(work_date, time_slot)`` (slice scope).
    '''
    result = session.execute(
        delete(AssignmentOverride).where(
            AssignmentOverride.work_date == work_date,
            AssignmentOverride.status == AssignmentStatus.DRAFT,
            (
                (AssignmentOverride.scope == OverrideScope.DAY)
                | (
                    (AssignmentOverride.scope == OverrideScope.SLICE)
                    & (AssignmentOverride.time_slot == time_slot)
                )
            ),
        )
    )
    return int(result.rowcount or 0)


def confirm_draft_overrides_for_slice(
    session: Session,
    work_date: date,
    time_slot: TimeSlot,
) -> int:
    '''
    Promote draft slice manual-assignment overrides to confirmed for audit retention.

    Day-wide availability overrides stay in draft so they remain available across shift publishes
    for the same selected date until the user clears or changes them.
    '''
    result = session.execute(
        update(AssignmentOverride)
        .where(
            AssignmentOverride.work_date == work_date,
            AssignmentOverride.status == AssignmentStatus.DRAFT,
            AssignmentOverride.scope == OverrideScope.SLICE,
            AssignmentOverride.kind == OverrideKind.MANUAL_ASSIGNMENT,
            AssignmentOverride.time_slot == time_slot,
        )
        .values(status=AssignmentStatus.CONFIRMED, confirmed_at=datetime.utcnow())
    )
    return int(result.rowcount or 0)


def load_confirmed_override_rows_for_slice(
    session: Session,
    work_date: date,
    time_slot: TimeSlot,
) -> list[dict[str, Any]]:
    '''
    Confirmed override audit rows for one slice (includes day-scope rows for that date).
    '''
    stmt = (
        select(AssignmentOverride)
        .where(
            AssignmentOverride.work_date == work_date,
            AssignmentOverride.status == AssignmentStatus.CONFIRMED,
            (
                (AssignmentOverride.scope == OverrideScope.DAY)
                | (
                    (AssignmentOverride.scope == OverrideScope.SLICE)
                    & (AssignmentOverride.time_slot == time_slot)
                )
            ),
        )
        .order_by(AssignmentOverride.confirmed_at, AssignmentOverride.created_at, AssignmentOverride.id)
    )
    out: list[dict[str, Any]] = []
    for row in session.scalars(stmt).all():
        out.append(
            {
                'work_date': row.work_date,
                'time_slot': row.time_slot.value if row.time_slot else '',
                'scope': row.scope.value,
                'kind': row.kind.value,
                'tech_id': row.technician_id,
                'task': row.task_name or '',
                'confirmed_at': row.confirmed_at.isoformat() if row.confirmed_at else '',
                'eligibility_overridden': bool(row.eligibility_overridden),
            }
        )
    return out
