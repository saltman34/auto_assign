from __future__ import annotations

from auto_assign.ingestion import TaskRequest



def validate_task_requests(task_requests: list[TaskRequest], available_tech_count: int) -> None:
    '''
    Ensure total requested task slots equals the number of available technicians.

    ``available_tech_count`` is the length of the already date/slot-filtered tech list.
    The sum of all ``task_count`` values must match exactly so each tech gets one slot.
    '''
    total_requested_tasks = sum(task_request.task_count for task_request in task_requests)

    if total_requested_tasks != available_tech_count:
        raise ValueError(f"The number of task requests ({total_requested_tasks}) is not equal to the number of available techs ({available_tech_count})")
    




