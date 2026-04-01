from enum import Enum

class DailyPreference(Enum):
    '''
    Represents the daily preference of a technician.
    '''
    CONSISTENCY = "consistency"
    VARIATION = "variation"

class TimeSlot(Enum):
    '''
    Shift band for scheduling (morning / mid / afternoon).

    Used together with a calendar date to choose which ``ScheduleRow`` availability
    flags apply (``available_AM``, ``available_MID``, ``available_PM``).
    '''
    AM = "AM"
    MID = "MID"
    PM = "PM"

class Staffing_Status(Enum):
    '''
    Represents the staffing status of a technician.
    '''
    SCHEDULED = "scheduled"
    CALL_OFF = "call_off"
    OVERTIME = "overtime"

