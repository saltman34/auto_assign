'''Tests for ORM → domain adapters.'''

from datetime import date

from auto_assign.db.adapters import (
    assignment_from_record,
    assignments_from_confirmed_records,
    tech_from_technician,
)
from auto_assign.db.models.assignment_record import AssignmentRecord
from auto_assign.db.models.technician import Technician
from auto_assign.domain.enums import AssignmentStatus, DailyPreference, TimeSlot


def test_tech_from_technician_roundtrip_fields() -> None:
    row = Technician(
        tech_id='t-99',
        tech_name='Jordan',
        daily_preference=DailyPreference.VARIATION,
        favorites=['scrolls'],
        dislikes=['grunge'],
    )
    tech = tech_from_technician(row)
    assert tech.tech_id == 't-99'
    assert tech.tech_name == 'Jordan'
    assert tech.daily_preference == DailyPreference.VARIATION
    assert tech.favorites == ['Scrolls']
    assert tech.dislikes == ['Grunge']
    tech.favorites.append('x')
    assert 'x' not in row.favorites


def test_assignment_from_record_maps_task_id_to_task_name() -> None:
    d = date(2026, 5, 1)
    row = AssignmentRecord(
        technician_id='t-1',
        task_id='clinicals',
        work_date=d,
        time_slot=TimeSlot.PM,
        status=AssignmentStatus.DRAFT,
        slot_index=0,
    )
    a = assignment_from_record(row)
    assert a.task_name == 'Clinicals'
    assert a.technician_id == 't-1'
    assert a.date_assigned == d
    assert a.time_slot == TimeSlot.PM


def test_assignments_from_confirmed_records_skips_draft() -> None:
    d = date(2026, 5, 2)
    rows = [
        AssignmentRecord(
            technician_id='a',
            task_id='t1',
            work_date=d,
            time_slot=TimeSlot.AM,
            status=AssignmentStatus.CONFIRMED,
            slot_index=0,
        ),
        AssignmentRecord(
            technician_id='b',
            task_id='t2',
            work_date=d,
            time_slot=TimeSlot.AM,
            status=AssignmentStatus.DRAFT,
            slot_index=0,
        ),
        AssignmentRecord(
            technician_id='c',
            task_id='t3',
            work_date=d,
            time_slot=TimeSlot.MID,
            status=AssignmentStatus.CONFIRMED,
            slot_index=0,
        ),
    ]
    out = assignments_from_confirmed_records(rows)
    assert len(out) == 2
    assert {x.technician_id for x in out} == {'a', 'c'}
