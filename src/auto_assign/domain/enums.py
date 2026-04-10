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


class AssignmentStatus(Enum):
    '''
    Persisted assignment row lifecycle: scratch ``draft`` vs published ``confirmed``.

    Scoring history must use **confirmed** rows only (see ``docs/assignment_algorithm.md``).
    '''
    DRAFT = 'draft'
    CONFIRMED = 'confirmed'


class OverrideScope(Enum):
    '''Scope of a manual override record.'''

    DAY = 'day'
    SLICE = 'slice'


class OverrideKind(Enum):
    '''Manual override type for availability or pre-assignment.'''

    CALL_OFF = 'call_off'
    OVERTIME = 'overtime'
    MANUAL_ASSIGNMENT = 'manual_assignment'

