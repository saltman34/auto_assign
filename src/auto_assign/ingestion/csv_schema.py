from dataclasses import dataclass
from datetime import date
from auto_assign.domain.validators.primitives import require_non_empty_string, require_date, require_boolean
from auto_assign.domain.enums import Staffing_Status



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
    staffing_status: Staffing_Status = Staffing_Status.SCHEDULED

    def __post_init__(self):
        '''
        Validate the schedule row.
        '''
        self.tech_name = require_non_empty_string(self.tech_name)
        self.work_date = require_date(self.work_date)
        self.available_AM = require_boolean(self.available_AM)
        self.available_MID = require_boolean(self.available_MID)
        self.available_PM = require_boolean(self.available_PM)
        if isinstance(self.staffing_status, Staffing_Status):
            return
        s = str(self.staffing_status).strip().lower().replace(' ', '_').replace('-', '_')
        for e in Staffing_Status:
            if s == e.value or s == e.name.lower():
                self.staffing_status = e
                return
        allowed = ', '.join(f'{e.name} ({e.value})' for e in Staffing_Status)
        raise ValueError(f'Invalid staffing_status {self.staffing_status!r}. Use one of: {allowed}')


