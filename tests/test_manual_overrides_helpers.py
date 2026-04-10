'''Tests for pure manual override helper logic.'''

from datetime import date

from auto_assign.core.assignment.manual_overrides import (
    apply_day_availability_overrides,
    build_residual_plan_after_manual_assignments,
)
from auto_assign.domain import Assignment
from auto_assign.domain.entities import Tech
from auto_assign.domain.enums import DailyPreference, TimeSlot
from auto_assign.ingestion import ScheduleRow, TaskRequest


def _row(name: str, d: date) -> ScheduleRow:
    return ScheduleRow(
        tech_name=name,
        work_date=d,
        available_AM=True,
        available_MID=True,
        available_PM=True,
        staffing_status='scheduled',
    )


def _tech(tech_id: str, name: str) -> Tech:
    return Tech(
        tech_id=tech_id,
        tech_name=name,
        daily_preference=DailyPreference.CONSISTENCY,
        favorites=[],
        dislikes=[],
    )


def test_apply_day_availability_overrides_calloff_and_overtime() -> None:
    d = date(2026, 10, 1)
    profiles = {'Ann': _tech('a', 'Ann'), 'Ben': _tech('b', 'Ben'), 'Cam': _tech('c', 'Cam')}
    out = apply_day_availability_overrides(
        base_pool=[_row('Ann', d), _row('Ben', d)],
        selected_date=d,
        tech_profiles_by_name=profiles,
        call_off_tech_ids=['a'],
        overtime_techs=[profiles['Cam']],
    )
    names = sorted(r.tech_name for r in out)
    assert names == ['Ben', 'Cam']


def test_build_residual_plan_after_manual_assignments() -> None:
    d = date(2026, 10, 2)
    slot = TimeSlot.AM
    profiles = {'Ann': _tech('a', 'Ann'), 'Ben': _tech('b', 'Ben')}
    task_requests = [
        TaskRequest('t1', 'Clinicals', 1, d, slot),
        TaskRequest('t2', 'Recuts', 1, d, slot),
    ]
    plan = build_residual_plan_after_manual_assignments(
        task_requests=task_requests,
        effective_pool=[_row('Ann', d), _row('Ben', d)],
        manual_assignments=[Assignment('Clinicals', 'a', d, slot)],
        tech_profiles_by_name=profiles,
    )
    assert not plan.errors
    assert len(plan.residual_pool) == 1
    assert sum(r.task_count for r in plan.residual_requests) == 1
    assert [r.task_name for r in plan.residual_requests if r.task_count > 0] == ['Recuts']


def test_build_residual_plan_flags_overage() -> None:
    d = date(2026, 10, 3)
    slot = TimeSlot.PM
    profiles = {'Ann': _tech('a', 'Ann')}
    task_requests = [TaskRequest('t1', 'Clinicals', 1, d, slot)]
    plan = build_residual_plan_after_manual_assignments(
        task_requests=task_requests,
        effective_pool=[_row('Ann', d)],
        manual_assignments=[
            Assignment('Clinicals', 'a', d, slot),
            Assignment('Clinicals', 'a', d, slot),
        ],
        tech_profiles_by_name=profiles,
    )
    assert plan.errors
