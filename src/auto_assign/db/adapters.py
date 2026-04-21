'''
Thin ORM ↔ domain mappers (no database I/O in this module).

Read path: ``Technician`` / ``AssignmentRecord`` → domain ``Tech`` / ``Assignment`` for
scoring and UI. Write path: ``technician_from_tech`` builds a **new** ORM instance for
inserts (actual ``INSERT``/``UPDATE`` lives in ``tech_repository`` with a ``Session``).

Use ``assignments_from_confirmed_records`` when building ``AssignmentScoringContext`` so
draft rows never enter fairness or same-day history.
'''
from __future__ import annotations

from collections.abc import Iterable

from auto_assign.db.models.assignment_record import AssignmentRecord
from auto_assign.db.models.technician import Technician
from auto_assign.domain.entities import Assignment, Tech
from auto_assign.domain.entities.tech import proficiency_dict_from_storage
from auto_assign.domain.enums import AssignmentStatus


def tech_from_technician(row: Technician) -> Tech:
    '''
    Purpose:
        Takes a persisted ``Technician`` row and converts it back into a domain ``Tech`` so assignment
        and validation code never depends on SQLAlchemy outside the DB layer.

    Inputs:
        ``row``: Loaded ORM ``Technician`` instance (detached or attached); must have JSON list columns
        materialized as Python lists for ``favorites`` / ``dislikes``.

    Returns:
        A new ``Tech``; ``Tech.__post_init__`` runs (normalization). ``favorites`` and
        ``dislikes`` are **copies** so mutating the domain lists does not alter ``row``.
    '''
    # list(...) decouples domain from ORM in-memory state if the session mutates later.
    elig: dict[str, bool] = {}
    for k, v in (row.eligible_by_task_id or {}).items():
        ks = str(k).strip()
        if ks:
            elig[ks] = bool(v)
    prof_raw: dict[str, object] = {}
    for k, v in (row.proficiency_by_task_id or {}).items():
        ks = str(k).strip()
        if ks and v is not None:
            prof_raw[ks] = v
    return Tech(
        tech_id=row.tech_id,
        tech_name=row.tech_name,
        daily_preference=row.daily_preference,
        favorites=list(row.favorites),
        dislikes=list(row.dislikes),
        eligible_by_task_id=elig,
        proficiency_by_task_id=proficiency_dict_from_storage(prof_raw),
    )


def assignment_from_record(row: AssignmentRecord) -> Assignment:
    '''
    Purpose:
        Map one ORM assignment row to domain ``Assignment`` for greedy scoring history
        or display. Does **not** filter by ``status``—use
        ``assignments_from_confirmed_records`` when only published history is allowed.

    Inputs:
        ``row``: Single ``AssignmentRecord`` with ``task_id``, ``technician_id``,
        ``work_date``, ``time_slot``, and ``status``.

    Returns:
        A new ``Assignment``; ``Assignment.__post_init__`` normalizes ``task_name`` and
        ``technician_id``. ``row.task_id`` is passed as ``task_name`` until the product
        stores task ids end-to-end in the domain model.
    '''
    return Assignment(
        task_name=row.task_id,
        technician_id=row.technician_id,
        date_assigned=row.work_date,
        time_slot=row.time_slot,
        catalog_task_id=row.catalog_task_id,
        eligibility_overridden=bool(getattr(row, 'eligibility_overridden', False)),
    )


def technician_from_tech(tech: Tech) -> Technician:
    '''
    Purpose:
        Materialize a **new** SQLAlchemy ``Technician`` instance from an already-validated
        domain ``Tech``. Used only on **insert**; updates should mutate an existing row
        via ``merge_technician_from_tech`` in ``tech_repository``.

    Inputs:
        ``tech``: Domain entity (typically built from CSV/form and validated in ``Tech``).

    Returns:
        A new ``Technician`` object **not** yet added to any ``Session``—no ``INSERT``
        occurs until ``session.add(...)`` and ``commit``.
    '''
    # Fresh lists so ORM JSON columns do not share list identity with the domain object.
    return Technician(
        tech_id=tech.tech_id,
        tech_name=tech.tech_name,
        daily_preference=tech.daily_preference,
        favorites=list(tech.favorites),
        dislikes=list(tech.dislikes),
        eligible_by_task_id=dict(tech.eligible_by_task_id),
        proficiency_by_task_id={k: v.value for k, v in tech.proficiency_by_task_id.items()},
    )


def assignments_from_confirmed_records(records: Iterable[AssignmentRecord]) -> tuple[Assignment, ...]:
    '''
    Purpose:
        Build the tuple of domain assignments that may feed ``AssignmentScoringContext``
        ``confirmed_assignments``: **only** rows whose ``status`` is ``CONFIRMED``, per
        ``docs/assignment_algorithm.md`` (draft must not affect fairness or same-day terms).

    Inputs:
        ``records``: Any iterable of ORM rows (e.g. query result); draft rows are skipped.

    Returns:
        An immutable tuple of ``Assignment`` instances in iteration order, excluding
        non-confirmed rows. Empty tuple if none qualify.
    '''
    return tuple(
        assignment_from_record(r)
        for r in records
        # Draft / scratch assignments must not inflate fairness or repeat-dislike history.
        if r.status == AssignmentStatus.CONFIRMED
    )
