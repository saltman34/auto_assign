from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from datetime import date

from auto_assign.domain import Assignment
from auto_assign.domain.entities import Tech
from auto_assign.domain.enums import TimeSlot
from auto_assign.domain.validators.primitives import normalize_string, normalize_tech_id
from auto_assign.ingestion import TaskRequest, ScheduleRow
from auto_assign.core.task_management import validate_task_requests

from .greedy_assigner import assign_greedy
from .scoring_types import AssignmentScoringContext, ScoringWeights


def _technician_id_for_schedule_row(
    row: ScheduleRow,
    tech_profiles_by_name: Mapping[str, Tech] | None,
) -> str:
    if tech_profiles_by_name is not None:
        tech = tech_profiles_by_name.get(normalize_string(row.tech_name))
        if tech is not None:
            return tech.tech_id
    return normalize_tech_id(row.tech_name)


def assign_tasks(
    task_requests: list[TaskRequest],
    available_techs: list[ScheduleRow],
    random_seed: int | None = None,
    *,
    use_greedy_assignment: bool = False,
    tech_profiles_by_name: Mapping[str, Tech] | None = None,
    confirmed_assignments: Sequence[Assignment] = (),
    scoring_weights: ScoringWeights | None = None,
    fairness_lookback_days: int | None = 30,
) -> list[Assignment]:
    '''
    Build one assignment per available technician for the same date/slot context.

    ``available_techs`` must already be filtered to the target ``work_date`` and
    shift. Task request counts must sum to ``len(available_techs)``.

    **Legacy path** (``use_greedy_assignment=False``): shuffle technicians and
    zip with expanded task slots—useful for a quick baseline.

    **Greedy path** (``use_greedy_assignment=True``): score each tech–task pair,
    fill **most-constrained** slots first, break ties with ``random_seed``.
    Optional ``tech_profiles_by_name`` supplies favorites/dislikes/preferences;
    missing names get neutral scoring. ``confirmed_assignments`` should be
    **published** history only (see ``docs/assignment_algorithm.md``).
    '''
    validate_task_requests(task_requests, len(available_techs))

    if use_greedy_assignment:
        if not task_requests:
            raise ValueError('task_requests must be non-empty for greedy assignment')
        anchor = task_requests[0]
        ctx = AssignmentScoringContext(
            work_date=anchor.task_date,
            time_slot=anchor.time_slot,
            confirmed_assignments=tuple(confirmed_assignments),
            lookback_days=fairness_lookback_days,
        )
        rng = random.Random(random_seed)
        return assign_greedy(
            task_requests,
            available_techs,
            scoring_context=ctx,
            tech_profiles_by_name=tech_profiles_by_name,
            weights=scoring_weights,
            rng=rng,
        )

    rng = random.Random(random_seed)
    shuffled_techs = list(available_techs)
    rng.shuffle(shuffled_techs)

    task_slots: list[tuple[str, date, TimeSlot]] = []
    for tr in task_requests:
        for _ in range(tr.task_count):
            task_slots.append((tr.task_name, tr.task_date, tr.time_slot))

    assignments: list[Assignment] = []
    for tech_row, (task_name, task_date, time_slot) in zip(shuffled_techs, task_slots, strict=True):
        assignments.append(
            Assignment(
                task_name=task_name,
                technician_id=_technician_id_for_schedule_row(tech_row, tech_profiles_by_name),
                date_assigned=tech_row.work_date,
                time_slot=time_slot,
            )
        )
    return assignments
