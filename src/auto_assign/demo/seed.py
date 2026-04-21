'''Seed and reset the database with the demo dataset.

The seeder is idempotent in the sense that it overwrites any pre-existing demo
rows (same ``tech_id`` / ``task_id``) via upsert, but it does **not** delete
unrelated data. If you want a guaranteed-clean slate, call
:func:`reset_demo_data` first.

Past confirmed history is produced by running the real greedy scorer once per
``(date, time_slot)`` for the 14 days preceding ``today``. That means the
lookback window used by the UI is populated with output that is internally
consistent with the same algorithm a hiring manager is about to invoke — and,
as a side benefit, the seeder dogfoods the production persistence path.
'''
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from auto_assign.core.assignment.assignment_service import assign_tasks
from auto_assign.core.csv_parsing.get_available_techs import (
    filter_schedule_rows_available_for_date_and_time_slot,
)
from auto_assign.db import (
    AssignmentOverride,
    AssignmentRecord,
    TaskCatalog,
    confirm_slice,
    delete_all_technicians,
    list_tasks,
    load_confirmed_assignments_for_scoring,
    load_tech_profiles_by_name,
    set_task_default_count,
    upsert_technicians,
)
from auto_assign.demo.fixtures import (
    DEMO_TASKS,
    DEMO_TECHS,
    build_demo_schedule_rows,
)
from auto_assign.domain.entities.tech import Tech
from auto_assign.domain.enums import TimeSlot
from auto_assign.ingestion.csv_schema import ScheduleRow
from auto_assign.ingestion.task_request import TaskRequest

_LOOKBACK_DAYS = 14
_FUTURE_DAYS = 7
_PAST_DAYS = 14


@dataclass(frozen=True)
class SeedResult:
    '''Summary returned by :func:`seed_demo_data`.

    ``future_schedule_rows`` are the rows that should be offered to the operator
    as a downloadable / uploadable CSV for the live scheduling demo. They cover
    ``today`` through ``today + 6`` inclusive. Past days are **not** returned;
    they are already persisted as confirmed history in the DB.
    '''

    tasks_created: int
    technicians_upserted: int
    past_days_confirmed: int
    confirmed_assignments_written: int
    future_schedule_rows: list[ScheduleRow]


def seed_demo_data(
    session: Session,
    *,
    today: date | None = None,
    seed: int = 20260617,
) -> SeedResult:
    '''Populate ``session``'s database with the demo dataset.

    Args:
        session: Open SQLAlchemy session; caller is responsible for the
            surrounding commit (use ``session_scope()``).
        today: Calendar day to anchor the past/future split. Defaults to
            ``date.today()``.
        seed: RNG seed for the schedule generator (same seed → same output).

    Returns:
        :class:`SeedResult` describing what was written plus the 7-day future
        schedule the operator should upload.
    '''
    if today is None:
        today = date.today()

    tasks_created = _upsert_tasks(session)
    techs_upserted = _upsert_technicians(session)
    session.flush()

    start_date = today - timedelta(days=_PAST_DAYS)
    total_days = _PAST_DAYS + _FUTURE_DAYS
    all_rows = build_demo_schedule_rows(
        start_date=start_date,
        num_days=total_days,
        seed=seed,
    )

    past_days, confirmed_count = _seed_past_confirmed_history(
        session,
        schedule_rows=all_rows,
        past_start=start_date,
        today=today,
    )

    future_rows = [r for r in all_rows if r.work_date >= today]

    return SeedResult(
        tasks_created=tasks_created,
        technicians_upserted=techs_upserted,
        past_days_confirmed=past_days,
        confirmed_assignments_written=confirmed_count,
        future_schedule_rows=future_rows,
    )


def reset_demo_data(session: Session) -> None:
    '''Truncate all assignment rows, override rows, technicians, and tasks.

    This is destructive and not scoped to "demo rows only" — the schema has no
    way to distinguish demo-seeded data from real data once it lives in the DB.
    Intended for local-dev / portfolio-demo use. Do not wire to a production
    environment.
    '''
    session.execute(delete(AssignmentOverride))
    session.execute(delete(AssignmentRecord))
    session.flush()
    delete_all_technicians(session)
    session.execute(delete(TaskCatalog))
    session.flush()


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _upsert_tasks(session: Session) -> int:
    '''Create or update every demo task; returns count written.'''
    existing_by_id = {t.task_id: t for t in list_tasks(session)}
    written = 0
    for spec in DEMO_TASKS:
        if spec.task_id in existing_by_id:
            set_task_default_count(session, spec.task_id, spec.default_count)
        else:
            # create_task generates a task_id unless we already have one; we
            # inline the INSERT here to pin a stable demo id for deterministic
            # eligibility/proficiency keys.
            session.add(
                TaskCatalog(
                    task_id=spec.task_id,
                    task_name=spec.task_name,
                    default_count=spec.default_count,
                )
            )
        written += 1
    return written


def _upsert_technicians(session: Session) -> int:
    '''Upsert every demo technician with eligibility + proficiency populated.'''
    techs: list[Tech] = [
        Tech(
            tech_id=spec.tech_id,
            tech_name=spec.tech_name,
            daily_preference=spec.daily_preference,
            favorites=list(spec.favorites),
            dislikes=list(spec.dislikes),
            eligible_by_task_id=dict(spec.eligible_by_task_id),
            proficiency_by_task_id=dict(spec.proficiency_by_task_id),
        )
        for spec in DEMO_TECHS
    ]
    return upsert_technicians(session, techs)


def _seed_past_confirmed_history(
    session: Session,
    *,
    schedule_rows: list[ScheduleRow],
    past_start: date,
    today: date,
) -> tuple[int, int]:
    '''Run the greedy scorer once per (past_date, slot) and confirm results.

    Returns ``(days_confirmed, total_assignments_written)``. Each slice is
    flushed so subsequent slices can read prior confirmed history for fairness.
    '''
    tasks = list_tasks(session)
    task_by_id = {t.task_id: t for t in tasks}

    days_done = 0
    total_written = 0
    day = past_start
    while day < today:
        for slot in TimeSlot:
            pool = filter_schedule_rows_available_for_date_and_time_slot(
                schedule_rows, day, slot
            )
            if not pool:
                continue
            tech_profiles_by_name = load_tech_profiles_by_name(session)
            confirmed_history = load_confirmed_assignments_for_scoring(
                session, day, lookback_days=_LOOKBACK_DAYS
            )
            requests = _task_requests_for_slice(
                task_by_id=task_by_id,
                pool_size=len(pool),
                work_date=day,
                time_slot=slot,
            )
            if not requests:
                continue
            assignments = assign_tasks(
                requests,
                pool,
                random_seed=20260617,
                use_greedy_assignment=True,
                tech_profiles_by_name=tech_profiles_by_name,
                confirmed_assignments=tuple(confirmed_history),
                fairness_lookback_days=_LOOKBACK_DAYS,
            )
            confirm_slice(session, day, slot, assignments)
            total_written += len(assignments)
            session.flush()
        days_done += 1
        day = day + timedelta(days=1)
    return days_done, total_written


def _task_requests_for_slice(
    *,
    task_by_id: dict[str, object],
    pool_size: int,
    work_date: date,
    time_slot: TimeSlot,
) -> list[TaskRequest]:
    '''Build TaskRequest list whose headcounts sum **exactly** to ``pool_size``.

    The assigner enforces ``sum(task_count) == len(available_techs)`` — any
    mismatch raises. We therefore distribute the pool across tasks in three
    passes, prioritizing high-``default_count`` tasks:

    1. Give each task at least 1 slot (in default-count-desc order) while pool
       remains. Tasks that do not fit drop to 0 and are omitted.
    2. Top up each task toward its ``default_count`` in the same order.
    3. Distribute any remaining surplus round-robin to the highest-default
       tasks (handles pools larger than the sum of defaults).
    '''
    if pool_size <= 0:
        return []
    specs = [s for s in DEMO_TASKS if s.task_id in task_by_id]
    if not specs:
        return []

    ordered = sorted(specs, key=lambda s: (-s.default_count, s.task_id))
    counts: dict[str, int] = {s.task_id: 0 for s in specs}
    remaining = pool_size

    for spec in ordered:
        if remaining <= 0:
            break
        counts[spec.task_id] = 1
        remaining -= 1

    for spec in ordered:
        if remaining <= 0:
            break
        headroom = spec.default_count - counts[spec.task_id]
        if headroom <= 0:
            continue
        add = min(headroom, remaining)
        counts[spec.task_id] += add
        remaining -= add

    while remaining > 0:
        for spec in ordered:
            if remaining <= 0:
                break
            counts[spec.task_id] += 1
            remaining -= 1

    return [
        TaskRequest(
            task_id=task_by_id[s.task_id].task_id,
            task_name=task_by_id[s.task_id].task_name,
            task_count=counts[s.task_id],
            task_date=work_date,
            time_slot=time_slot,
        )
        for s in specs
        if counts[s.task_id] > 0
    ]
