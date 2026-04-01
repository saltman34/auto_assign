from dataclasses import dataclass
from datetime import date
from auto_assign.domain.validators.primitives import (
    require_non_empty_string,
    require_date,
    normalize_string,
)
from auto_assign.domain.enums import TimeSlot

@dataclass
class Assignment:
    '''
    One technician assigned to one task on a date within a shift band (AM/MID/PM).
    '''
    task_name: str
    technician_id: str
    date_assigned: date
    time_slot: TimeSlot

    def __post_init__(self):
        '''
        Validate the assignment.
        '''
        self.task_name = require_non_empty_string(self.task_name)
        self.technician_id = require_non_empty_string(self.technician_id)
        self.date_assigned = require_date(self.date_assigned)
        self.task_name = normalize_string(self.task_name)
        self.technician_id = normalize_string(self.technician_id)
        if not isinstance(self.time_slot, TimeSlot):
            raise ValueError(f"time_slot must be a TimeSlot enum, got {type(self.time_slot).__name__}")
