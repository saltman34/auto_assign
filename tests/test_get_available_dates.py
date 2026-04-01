'''Tests for ``get_all_schedule_dates`` — distinct calendar dates in parsed rows.'''

from datetime import date

from auto_assign.core.csv_parsing.get_available_dates import get_all_schedule_dates
from auto_assign.ingestion import ScheduleRow


def test_empty_input_returns_empty_set() -> None:
    assert get_all_schedule_dates([]) == set()


def test_single_row_single_date() -> None:
    d = date(2026, 1, 15)
    rows = [
        ScheduleRow(
            tech_name='A',
            work_date=d,
            available_AM=True,
            available_MID=False,
            available_PM=False,
        )
    ]
    assert get_all_schedule_dates(rows) == {d}


def test_multiple_rows_same_date_returns_one_element() -> None:
    d = date(2026, 6, 1)
    rows = [
        ScheduleRow('A', d, True, True, True),
        ScheduleRow('B', d, False, False, True),
    ]
    assert get_all_schedule_dates(rows) == {d}


def test_multiple_distinct_dates() -> None:
    d_a = date(2025, 12, 31)
    d_b = date(2026, 1, 1)
    d_c = date(2026, 1, 2)
    rows = [
        ScheduleRow('X', d_a, True, True, True),
        ScheduleRow('Y', d_b, True, False, False),
        ScheduleRow('Z', d_c, False, True, False),
        ScheduleRow('X', d_b, True, True, True),
    ]
    assert get_all_schedule_dates(rows) == {d_a, d_b, d_c}


def test_order_of_rows_does_not_matter() -> None:
    d1 = date(2026, 2, 1)
    d2 = date(2026, 2, 2)
    rows_forward = [
        ScheduleRow('A', d1, True, True, True),
        ScheduleRow('B', d2, True, True, True),
    ]
    rows_reverse = list(reversed(rows_forward))
    assert get_all_schedule_dates(rows_forward) == get_all_schedule_dates(rows_reverse) == {d1, d2}


def test_availability_flags_do_not_affect_date_set() -> None:
    '''Dates are collected regardless of AM/MID/PM; slot filtering is elsewhere.'''
    d = date(2026, 4, 1)
    rows_all_off = [ScheduleRow('A', d, False, False, False)]
    rows_mixed = [ScheduleRow('A', d, True, False, True)]
    assert get_all_schedule_dates(rows_all_off) == get_all_schedule_dates(rows_mixed) == {d}
