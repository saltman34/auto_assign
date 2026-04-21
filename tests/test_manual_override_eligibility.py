'''Tests for eligibility-override classification and residual plan reporting.'''

from datetime import date

from auto_assign.core.assignment.manual_overrides import (
    build_residual_plan_after_manual_assignments,
    classify_ineligible_manual_assignments,
    is_tech_eligible_for_catalog_task,
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


def _tech(tech_id: str, name: str, eligible: dict[str, bool] | None = None) -> Tech:
    return Tech(
        tech_id=tech_id,
        tech_name=name,
        daily_preference=DailyPreference.CONSISTENCY,
        favorites=[],
        dislikes=[],
        eligible_by_task_id=dict(eligible or {}),
    )


def test_is_tech_eligible_defaults_true_when_key_missing() -> None:
    tech = _tech('a', 'Ann')
    assert is_tech_eligible_for_catalog_task(tech, 't1') is True


def test_is_tech_eligible_false_when_explicit_false() -> None:
    tech = _tech('a', 'Ann', eligible={'t1': False})
    assert is_tech_eligible_for_catalog_task(tech, 't1') is False
    assert is_tech_eligible_for_catalog_task(tech, 't2') is True


def test_is_tech_eligible_without_catalog_id_returns_true() -> None:
    tech = _tech('a', 'Ann', eligible={'t1': False})
    # No catalog id → cannot evaluate catalog-keyed eligibility; treat as eligible.
    assert is_tech_eligible_for_catalog_task(tech, None) is True
    assert is_tech_eligible_for_catalog_task(tech, '  ') is True


def test_classify_ineligible_manual_assignments_reports_only_explicit_false() -> None:
    d = date(2026, 10, 5)
    slot = TimeSlot.AM
    profiles = {
        'Ann': _tech('a', 'Ann', eligible={'t1': False}),
        'Ben': _tech('b', 'Ben'),
    }
    manuals = [
        Assignment(task_name='Clinicals', technician_id='a', date_assigned=d, time_slot=slot, catalog_task_id='t1'),
        Assignment(task_name='Recuts', technician_id='b', date_assigned=d, time_slot=slot, catalog_task_id='t2'),
    ]
    infos = classify_ineligible_manual_assignments(manuals, profiles)
    assert len(infos) == 1
    assert infos[0].technician_id == 'a'
    assert infos[0].catalog_task_id == 't1'


def test_build_residual_plan_reports_ineligible_without_failing() -> None:
    d = date(2026, 10, 6)
    slot = TimeSlot.AM
    profiles = {
        'Ann': _tech('a', 'Ann', eligible={'t1': False}),
        'Ben': _tech('b', 'Ben'),
    }
    task_requests = [
        TaskRequest('t1', 'Clinicals', 1, d, slot),
        TaskRequest('t2', 'Recuts', 1, d, slot),
    ]
    manual = Assignment(
        task_name='Clinicals',
        technician_id='a',
        date_assigned=d,
        time_slot=slot,
        catalog_task_id='t1',
        eligibility_overridden=True,
    )
    plan = build_residual_plan_after_manual_assignments(
        task_requests=task_requests,
        effective_pool=[_row('Ann', d), _row('Ben', d)],
        manual_assignments=[manual],
        tech_profiles_by_name=profiles,
    )
    assert plan.errors == []
    assert len(plan.ineligible_overrides) == 1
    assert plan.ineligible_overrides[0].technician_id == 'a'
    assert [r.task_name for r in plan.residual_requests if r.task_count > 0] == ['Recuts']


def test_assignment_flag_default_false_and_round_trip() -> None:
    a = Assignment('Clinicals', 'a', date(2026, 10, 7), TimeSlot.AM)
    assert a.eligibility_overridden is False
    b = Assignment(
        'Clinicals',
        'a',
        date(2026, 10, 7),
        TimeSlot.AM,
        catalog_task_id='t1',
        eligibility_overridden=True,
    )
    assert b.eligibility_overridden is True
