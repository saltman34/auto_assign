'''Tests for slot availability helpers — filter techs by date and shift band.'''

from datetime import date
from enum import Enum

import pytest

from auto_assign.core.csv_parsing.get_available_techs import (
    filter_schedule_rows_available_for_date_and_time_slot,
    get_available_techs,
    row_is_available_for_time_slot,
)
from auto_assign.domain.enums import TimeSlot
from auto_assign.ingestion import ScheduleRow


class _ForeignTimeSlot(Enum):
    '''Not a ``TimeSlot``; used to exercise the invalid-branch guard.'''

    OTHER = 'other'


@pytest.fixture
def sample_rows() -> list[ScheduleRow]:
    d = date(2026, 3, 30)
    return [
        ScheduleRow('Alex', d, True, False, False),
        ScheduleRow('Blake', d, True, True, False),
        ScheduleRow('Casey', d, False, False, True),
        ScheduleRow('Drew', date(2026, 3, 31), True, True, True),
    ]


def test_row_is_available_for_time_slot_reads_boolean_columns(sample_rows: list[ScheduleRow]) -> None:
    alex = sample_rows[0]
    assert row_is_available_for_time_slot(alex, TimeSlot.AM) is True
    assert row_is_available_for_time_slot(alex, TimeSlot.MID) is False
    assert row_is_available_for_time_slot(alex, TimeSlot.PM) is False

    casey = sample_rows[2]
    assert row_is_available_for_time_slot(casey, TimeSlot.AM) is False
    assert row_is_available_for_time_slot(casey, TimeSlot.MID) is False
    assert row_is_available_for_time_slot(casey, TimeSlot.PM) is True


def test_row_is_available_for_time_slot_invalid_enum_member_raises() -> None:
    row = ScheduleRow('X', date(2026, 1, 1), True, True, True)
    with pytest.raises(ValueError, match='Invalid time slot'):
        row_is_available_for_time_slot(row, _ForeignTimeSlot.OTHER)


def test_row_is_not_available_when_call_off_even_if_shift_flag_true() -> None:
    row = ScheduleRow('X', date(2026, 1, 1), True, True, True, staffing_status='call_off')
    assert row_is_available_for_time_slot(row, TimeSlot.AM) is False


def test_filter_schedule_rows_requires_true_for_shift_not_just_matching_date(
    sample_rows: list[ScheduleRow],
) -> None:
    d = date(2026, 3, 30)
    am_rows = filter_schedule_rows_available_for_date_and_time_slot(sample_rows, d, TimeSlot.AM)
    assert {r.tech_name for r in am_rows} == {'Alex', 'Blake'}
    for r in am_rows:
        assert r.available_AM is True


def test_get_available_techs_matches_filter_names(sample_rows: list[ScheduleRow]) -> None:
    d = date(2026, 3, 30)
    am_names = get_available_techs(sample_rows, d, TimeSlot.AM)
    assert am_names == [r.tech_name for r in sample_rows if r.work_date == d and r.available_AM]

    mid_names = get_available_techs(sample_rows, d, TimeSlot.MID)
    assert mid_names == ['Blake']

    pm_names = get_available_techs(sample_rows, d, TimeSlot.PM)
    assert pm_names == ['Casey']


def test_get_available_techs_no_rows_for_wrong_date(sample_rows: list[ScheduleRow]) -> None:
    assert get_available_techs(sample_rows, date(2020, 1, 1), TimeSlot.AM) == []


def test_get_available_techs_all_unavailable_for_slot_returns_empty() -> None:
    '''Every row has the requested slot false — pool is empty (not confused with wrong date).'''
    d = date(2026, 8, 15)
    rows = [
        ScheduleRow('A', d, False, True, True),
        ScheduleRow('B', d, False, False, True),
    ]
    assert get_available_techs(rows, d, TimeSlot.AM) == []
    assert filter_schedule_rows_available_for_date_and_time_slot(rows, d, TimeSlot.AM) == []


def test_filter_schedule_rows_preserves_row_objects_and_order(sample_rows: list[ScheduleRow]) -> None:
    d = date(2026, 3, 30)
    rows = filter_schedule_rows_available_for_date_and_time_slot(sample_rows, d, TimeSlot.AM)
    assert rows == [sample_rows[0], sample_rows[1]]
    assert all(r.work_date == d and r.available_AM for r in rows)


def test_filter_schedule_rows_duplicate_tech_same_day_two_rows() -> None:
    '''Duplicate schedule lines — both returned if AM is True on each.'''
    d = date(2026, 5, 1)
    r1 = ScheduleRow('Sam', d, True, False, False)
    r2 = ScheduleRow('Sam', d, True, False, False)
    pool = [r1, r2]
    out = filter_schedule_rows_available_for_date_and_time_slot(pool, d, TimeSlot.AM)
    assert len(out) == 2 and out[0] is r1 and out[1] is r2
