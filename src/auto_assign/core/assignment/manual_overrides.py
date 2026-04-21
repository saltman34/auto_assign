'''Pure helpers for availability and manual pre-assignment overrides.'''

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from auto_assign.domain import Assignment
from auto_assign.domain.entities import Tech
from auto_assign.domain.enums import Staffing_Status
from auto_assign.domain.validators.primitives import normalize_string, normalize_tech_id
from auto_assign.ingestion import ScheduleRow, TaskRequest


def is_tech_eligible_for_catalog_task(tech: Tech, catalog_task_id: str | None) -> bool:
    '''
    True unless the technician has an **explicit** ineligibility entry for this catalog task.

    Absent keys are treated as eligible (matches scoring-layer contract: missing =
    allowed). Passing ``catalog_task_id=None`` also returns True because catalog-keyed
    eligibility cannot be evaluated without a catalog id.
    '''
    if catalog_task_id is None:
        return True
    key = catalog_task_id.strip()
    if not key:
        return True
    return tech.eligible_by_task_id.get(key, True) is not False


@dataclass(frozen=True)
class IneligibleOverrideInfo:
    '''Identifies a manual assignment whose tech is explicitly ineligible for the task.'''

    task_name: str
    catalog_task_id: str | None
    technician_id: str


def classify_ineligible_manual_assignments(
    manual_assignments: Sequence[Assignment],
    tech_profiles_by_name: Mapping[str, Tech] | None,
) -> tuple[IneligibleOverrideInfo, ...]:
    '''
    Return info for manual assignments that place a tech the catalog says is ineligible.

    ``tech_profiles_by_name`` is keyed by **normalized tech name**; the manual
    ``Assignment.technician_id`` is a ``tech_id``, so we build a tech_id→Tech index
    once. Unknown tech_ids (no matching profile) are skipped — separate validation
    (``technician_ids_missing_from_db``) already surfaces those.
    '''
    if not manual_assignments or not tech_profiles_by_name:
        return ()
    tech_by_id: dict[str, Tech] = {t.tech_id: t for t in tech_profiles_by_name.values()}
    out: list[IneligibleOverrideInfo] = []
    for a in manual_assignments:
        tech = tech_by_id.get(a.technician_id)
        if tech is None:
            continue
        if not is_tech_eligible_for_catalog_task(tech, a.catalog_task_id):
            out.append(
                IneligibleOverrideInfo(
                    task_name=a.task_name,
                    catalog_task_id=a.catalog_task_id,
                    technician_id=a.technician_id,
                )
            )
    return tuple(out)


def _tech_id_for_schedule_row(
    row: ScheduleRow,
    tech_profiles_by_name: Mapping[str, Tech] | None,
) -> str:
    if tech_profiles_by_name is not None:
        tech = tech_profiles_by_name.get(normalize_string(row.tech_name))
        if tech is not None:
            return tech.tech_id
    return normalize_tech_id(row.tech_name)


def apply_day_availability_overrides(
    *,
    base_pool: Sequence[ScheduleRow],
    selected_date: date,
    tech_profiles_by_name: Mapping[str, Tech] | None,
    call_off_tech_ids: Sequence[str],
    overtime_techs: Sequence[Tech],
) -> list[ScheduleRow]:
    '''
    Build the effective pool for one date/slot after day-scope call-off and overtime edits.
    '''
    call_off = set(call_off_tech_ids)
    out_by_tid: dict[str, ScheduleRow] = {}
    for row in base_pool:
        tid = _tech_id_for_schedule_row(row, tech_profiles_by_name)
        if tid in call_off:
            continue
        if tid not in out_by_tid:
            out_by_tid[tid] = row

    for tech in overtime_techs:
        if tech.tech_id in call_off:
            continue
        if tech.tech_id in out_by_tid:
            continue
        out_by_tid[tech.tech_id] = ScheduleRow(
            tech_name=tech.tech_name,
            work_date=selected_date,
            available_AM=True,
            available_MID=True,
            available_PM=True,
            staffing_status=Staffing_Status.OVERTIME,
        )

    return list(out_by_tid.values())


@dataclass(frozen=True)
class ResidualPlan:
    residual_requests: list[TaskRequest]
    residual_pool: list[ScheduleRow]
    errors: list[str]
    ineligible_overrides: tuple[IneligibleOverrideInfo, ...] = ()


def build_residual_plan_after_manual_assignments(
    *,
    task_requests: Sequence[TaskRequest],
    effective_pool: Sequence[ScheduleRow],
    manual_assignments: Sequence[Assignment],
    tech_profiles_by_name: Mapping[str, Tech] | None,
) -> ResidualPlan:
    '''
    Compute greedy residual workload/pool after fixed manual assignments.

    Manual assignments that carry ``eligibility_overridden=True`` (or that the catalog
    still flags as ineligible) are **allowed** by design — they represent an explicit
    operator decision (e.g. training / shadowing). They are reported via
    ``ResidualPlan.ineligible_overrides`` for UI banners but never added to ``errors``.
    '''
    errors: list[str] = []
    manual_by_tid: dict[str, Assignment] = {}
    for a in manual_assignments:
        if a.technician_id in manual_by_tid:
            errors.append(f'Duplicate manual assignment for tech_id `{a.technician_id}`.')
        else:
            manual_by_tid[a.technician_id] = a

    pool_by_tid: dict[str, ScheduleRow] = {}
    for row in effective_pool:
        tid = _tech_id_for_schedule_row(row, tech_profiles_by_name)
        if tid in pool_by_tid:
            continue
        pool_by_tid[tid] = row

    unknown_manual = [tid for tid in manual_by_tid if tid not in pool_by_tid]
    if unknown_manual:
        errors.append(
            'Manual assignment includes tech(s) not in effective pool: '
            + ', '.join(f'`{x}`' for x in sorted(unknown_manual))
        )

    request_by_task = Counter({tr.task_name: tr.task_count for tr in task_requests})
    manual_by_task = Counter(a.task_name for a in manual_assignments)

    residual_requests: list[TaskRequest] = []
    for tr in task_requests:
        rem = request_by_task[tr.task_name] - manual_by_task[tr.task_name]
        if rem < 0:
            errors.append(
                f'Manual assignments for task `{tr.task_name}` exceed requested count ({request_by_task[tr.task_name]}).'
            )
            rem = 0
        residual_requests.append(
            TaskRequest(
                task_id=tr.task_id,
                task_name=tr.task_name,
                task_count=int(rem),
                task_date=tr.task_date,
                time_slot=tr.time_slot,
            )
        )

    residual_pool = [row for tid, row in pool_by_tid.items() if tid not in manual_by_tid]
    residual_total = sum(r.task_count for r in residual_requests)
    if residual_total != len(residual_pool):
        errors.append(
            f'Residual mismatch: remaining task slots={residual_total}, remaining technicians={len(residual_pool)}.'
        )

    return ResidualPlan(
        residual_requests=residual_requests,
        residual_pool=residual_pool,
        errors=errors,
        ineligible_overrides=classify_ineligible_manual_assignments(
            manual_assignments, tech_profiles_by_name
        ),
    )
