from __future__ import annotations

from auto_assign.domain.entities import Task



def create_tasks(tasks_config: list[dict]) -> list[Task]:
    '''
    Create task objects from task config
    '''
    tasks = []
    for task in tasks_config:
        tasks.append(Task(task_id=task['task_id'], task_name=task['task_name'], default_count=task['default_count']))
    return tasks
