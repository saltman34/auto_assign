'''
Session-scoped loaders for greedy assignment and scoring.

**Technician profiles** — ``load_tech_profiles_by_name`` returns ``dict[str, Tech]`` keyed by
``normalize_string(tech.tech_name)`` for schedule **name** lookup. Domain
``Assignment.technician_id`` and ``AssignmentRecord.technician_id`` are **``tech_id``**
end-to-end; ``compatibility_scoring._tech_matches_assignment`` compares ids to
``TechScoringProfile.tech_id``.

**Tasks table (forward compatibility):** ``AssignmentRecord.task_id`` is currently treated as
the string fed into domain ``Assignment.task_name`` for scoring (see ``assignment_from_record``).
When a persisted ``tasks`` catalog and real FK exist, resolve catalog id → normalized task name
in the adapter or denormalize ``task_name`` on assignment rows so favorites/dislikes (name-based)
stay correct. This module may later join ``Task`` when loading confirmed history.

**Confirmed history** — ``load_confirmed_assignments_for_scoring`` applies the same date window
as ``_assignment_in_lookback`` in ``compatibility_scoring`` (confirmed rows only; draft excluded).
'''
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from auto_assign.db.adapters import assignment_from_record, tech_from_technician
from auto_assign.db.models.assignment_record import AssignmentRecord
from auto_assign.db.models.technician import Technician
from auto_assign.domain.entities import Assignment, Tech
from auto_assign.domain.enums import AssignmentStatus
from auto_assign.domain.validators.primitives import normalize_string


def load_tech_profiles_by_name(
    session: Session,
    *,
    tech_ids: frozenset[str] | None = None,
) -> dict[str, Tech]:
    '''
    Load all technicians (or an allowlist by ``tech_id``) as domain ``Tech``, keyed by
    normalized ``tech_name`` for ``tech_profiles_by_name`` in ``assign_tasks``.

    Raises:
        ValueError: If two rows normalize to the same dict key (should not happen if
        ``uq_technicians_tech_name`` is enforced).
    '''
    stmt = select(Technician)
    if tech_ids is not None:
        if not tech_ids:
            return {}
        stmt = stmt.where(Technician.tech_id.in_(tech_ids))

    rows = session.scalars(stmt).all()
    out: dict[str, Tech] = {}
    for row in rows:
        tech = tech_from_technician(row)
        key = normalize_string(tech.tech_name)
        if key in out:
            raise ValueError(
                f'Duplicate technician map key after normalization: {key!r} '
                f'(tech_id={row.tech_id!r} collides with tech_id={out[key].tech_id!r})'
            )
        out[key] = tech
    return out


def load_confirmed_assignments_for_scoring(
    session: Session,
    work_date: date,
    lookback_days: int | None,
) -> tuple[Assignment, ...]:
    '''
    Confirmed assignment history for ``AssignmentScoringContext``, with the same inclusive
    date window as ``_assignment_in_lookback`` (no lower bound when ``lookback_days`` is ``None``).
    '''
    stmt = select(AssignmentRecord).where(AssignmentRecord.status == AssignmentStatus.CONFIRMED)
    if lookback_days is not None:
        cutoff = work_date - timedelta(days=lookback_days)
        stmt = stmt.where(
            AssignmentRecord.work_date >= cutoff,
            AssignmentRecord.work_date <= work_date,
        )
    stmt = stmt.order_by(AssignmentRecord.work_date, AssignmentRecord.id)

    records = session.scalars(stmt).all()
    return tuple(assignment_from_record(r) for r in records)
