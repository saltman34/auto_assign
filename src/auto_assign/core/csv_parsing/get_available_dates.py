from datetime import date

from auto_assign.ingestion import ScheduleRow


def get_all_schedule_dates(schedule_rows: list[ScheduleRow]) -> set[date]:
    '''
    Distinct calendar dates present in the parsed schedule (any shift flags).

    Does not filter by AM/MID/PM; use ``get_available_techs`` after the user
    picks a date and time slot.
    '''
    return {row.work_date for row in schedule_rows}



