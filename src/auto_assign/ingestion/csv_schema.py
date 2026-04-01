from dataclasses import dataclass
from datetime import date
from auto_assign.domain.validators.primitives import require_non_empty_string, require_date, require_boolean



@dataclass
class ScheduleRow:
    '''
    One schedule record: a technician on a calendar day with AM / MID / PM availability flags.

    Each flag is True if that technician may be assigned during that shift band on work_date.
    '''
    tech_name: str
    work_date: date
    available_AM: bool
    available_MID: bool
    available_PM: bool

    def __post_init__(self):
        '''
        Validate the schedule row.
        '''
        self.tech_name = require_non_empty_string(self.tech_name)
        self.work_date = require_date(self.work_date)
        self.available_AM = require_boolean(self.available_AM)
        self.available_MID = require_boolean(self.available_MID)
        self.available_PM = require_boolean(self.available_PM)


