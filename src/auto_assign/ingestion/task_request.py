from dataclasses import dataclass
from datetime import date
from auto_assign.domain import require_positive_integer, require_date
from auto_assign.domain.validators.primitives import require_non_empty_string, normalize_string
from auto_assign.domain.enums import TimeSlot

@dataclass
class TaskRequest:
    '''
    Requested headcount for one task on a calendar date and shift band (AM/MID/PM).

    ``time_slot`` must match the shift used when filtering available technicians.
    '''
    task_id: str
    task_name: str
    task_count: int
    task_date: date
    time_slot: TimeSlot


    def __post_init__(self):
        '''
        Validate the task request.
        '''
        self.task_id = require_non_empty_string(self.task_id)
        self.task_name = require_non_empty_string(self.task_name)
        self.task_name = normalize_string(self.task_name)
        self.task_count = require_positive_integer(self.task_count)
        self.task_date = require_date(self.task_date)
        if not isinstance(self.time_slot, TimeSlot):
            raise ValueError(f"time_slot must be a TimeSlot enum, got {type(self.time_slot).__name__}")
