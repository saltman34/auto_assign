from __future__ import annotations

import random
from datetime import date

from auto_assign.domain import Assignment
from auto_assign.domain.enums import TimeSlot
from auto_assign.ingestion import TaskRequest, ScheduleRow
from auto_assign.core.task_management import validate_task_requests


def assign_tasks(
    task_requests: list[TaskRequest],
    available_techs: list[ScheduleRow],
    random_seed: int | None = None,
) -> list[Assignment]:
    '''
    Build one assignment per available technician for the same date/slot context.

    ``available_techs`` must already be filtered to the target ``work_date`` and
    shift (AM/MID/PM) so each row is eligible for assignment. Task request counts
    must sum to exactly ``len(available_techs)``. Assignments are produced by
    shuffling technicians and zipping them with expanded task slots (task name,
    date, and time slot copied from each ``TaskRequest``).
    '''
    validate_task_requests(task_requests, len(available_techs))

    rng = random.Random(random_seed)
    shuffled_techs = list(available_techs)
    rng.shuffle(shuffled_techs)

    task_slots: list[tuple[str, date, TimeSlot]] = []
    for tr in task_requests:
        for _ in range(tr.task_count):
            task_slots.append((tr.task_name, tr.task_date, tr.time_slot))

    assignments: list[Assignment] = []
    for tech, (task_name, task_date, time_slot) in zip(shuffled_techs, task_slots, strict=True):
        assignments.append(
            Assignment(
                task_name=task_name,
                technician_id=tech.tech_name,
                date_assigned=tech.work_date,
                time_slot=time_slot,
            )
        )
    return assignments