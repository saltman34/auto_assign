from __future__ import annotations

from datetime import date
from typing import List

from auto_assign.domain.enums import Staffing_Status, TimeSlot
from auto_assign.ingestion import ScheduleRow


def row_is_available_for_time_slot(row: ScheduleRow, time_slot: TimeSlot) -> bool:
    '''
    Whether this row marks the technician **available** (flag is ``True``) for ``time_slot``.

    This reads the parsed boolean for that shift only: ``TimeSlot.AM`` →
    ``row.available_AM``, ``MID`` → ``available_MID``, ``PM`` → ``available_PM``.
    ``False`` means not assignable for that shift on ``row.work_date``.
    '''
    if row.staffing_status == Staffing_Status.CALL_OFF:
        return False
    if time_slot == TimeSlot.AM:
        return row.available_AM is True
    if time_slot == TimeSlot.MID:
        return row.available_MID is True
    if time_slot == TimeSlot.PM:
        return row.available_PM is True
    raise ValueError(f"Invalid time slot: {time_slot!r}")


def filter_schedule_rows_available_for_date_and_time_slot(
    schedule_rows: List[ScheduleRow],
    selected_date: date,
    time_slot: TimeSlot,
) -> List[ScheduleRow]:
    '''
    Schedule rows for ``selected_date`` where the technician is available for ``time_slot``.

    Keeps a row only if ``work_date == selected_date`` **and** the availability
    column for that shift is ``True`` (see ``row_is_available_for_time_slot``).

    Use this list as the technician pool passed to ``assign_tasks`` for that date and shift.
    '''
    return [
        row
        for row in schedule_rows
        if row.work_date == selected_date and row_is_available_for_time_slot(row, time_slot)
    ]


def get_available_techs(
    schedule_rows: List[ScheduleRow],
    selected_date: date,
    time_slot: TimeSlot,
) -> List[str]:
    '''
    Names of technicians available on ``selected_date`` for ``time_slot``.

    Same filtering as ``filter_schedule_rows_available_for_date_and_time_slot``;
    returns ``tech_name`` for each matching row.
    '''
    return [
        row.tech_name
        for row in filter_schedule_rows_available_for_date_and_time_slot(
            schedule_rows, selected_date, time_slot
        )
    ]
