from dataclasses import dataclass
from auto_assign.domain.validators.primitives import normalize_string, require_date
from auto_assign.domain.enums import TimeSlot
from datetime import date


@dataclass
class DailyStaff:
    '''
    Snapshot of who is available on a calendar date for one shift band (AM/MID/PM).
    '''
    techs_available: list[str]
    selected_date: date
    time_slot: TimeSlot

    def __post_init__(self):
        '''
        Validate the daily staff of selected date and time slot.
        '''
        self.selected_date = require_date(self.selected_date)
        if not isinstance(self.time_slot, TimeSlot):
            raise ValueError(f"time_slot must be a TimeSlot enum, got {type(self.time_slot).__name__}")
        self.techs_available = [normalize_string(tech) for tech in self.techs_available]