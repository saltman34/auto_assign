'''Tests for assignment override persistence helpers (SQLite in-memory).'''

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from auto_assign.db import (
    Base,
    Technician,
    clear_draft_overrides_for_slice,
    confirm_draft_overrides_for_slice,
    load_confirmed_override_rows_for_slice,
    load_draft_overrides_for_slice,
    replace_draft_day_availability_overrides,
    replace_draft_manual_assignments_for_slice,
)
from auto_assign.domain import Assignment
from auto_assign.domain.enums import DailyPreference, TimeSlot


@pytest.fixture
def engine():
    eng = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(eng)
    return eng


def _tech(tech_id: str, name: str) -> Technician:
    return Technician(
        tech_id=tech_id,
        tech_name=name,
        daily_preference=DailyPreference.CONSISTENCY,
        favorites=[],
        dislikes=[],
    )


def test_override_draft_load_confirm_lifecycle(engine) -> None:
    d = date(2026, 9, 1)
    slot = TimeSlot.AM
    with Session(engine) as session:
        session.add_all([_tech('a', 'Ann'), _tech('b', 'Ben'), _tech('c', 'Cam')])
        replace_draft_day_availability_overrides(
            session,
            d,
            call_off_tech_ids=['a'],
            overtime_tech_ids_by_slot={TimeSlot.AM: ['c']},
        )
        replace_draft_manual_assignments_for_slice(
            session,
            d,
            slot,
            [Assignment('Clinicals', 'b', d, slot)],
        )
        session.commit()

    with Session(engine) as session:
        draft = load_draft_overrides_for_slice(session, d, slot)
    assert draft['call_off_tech_ids'] == ['a']
    assert draft['overtime_tech_ids'] == ['c']
    assert draft['overtime_tech_ids_by_slot']['AM'] == ['c']
    assert len(draft['manual_assignments']) == 1
    assert draft['manual_assignments'][0].technician_id == 'b'

    with Session(engine) as session:
        n = confirm_draft_overrides_for_slice(session, d, slot)
        session.commit()
    assert n == 1

    with Session(engine) as session:
        rows = load_confirmed_override_rows_for_slice(session, d, slot)
    assert len(rows) == 1
    assert {r['kind'] for r in rows} == {'manual_assignment'}

    with Session(engine) as session:
        draft = load_draft_overrides_for_slice(session, d, slot)
    assert draft['call_off_tech_ids'] == ['a']
    assert draft['overtime_tech_ids'] == ['c']


def test_manual_assignment_eligibility_override_round_trip(engine) -> None:
    '''
    Draft write → load → confirm → audit must preserve ``eligibility_overridden``
    across the full ``AssignmentOverride`` lifecycle so the audit trail is intact.
    '''
    d = date(2026, 9, 3)
    slot = TimeSlot.AM
    with Session(engine) as session:
        session.add_all([_tech('a', 'Ann'), _tech('b', 'Ben')])
        replace_draft_manual_assignments_for_slice(
            session,
            d,
            slot,
            [
                Assignment(
                    task_name='Clinicals',
                    technician_id='a',
                    date_assigned=d,
                    time_slot=slot,
                    catalog_task_id='t1',
                    eligibility_overridden=True,
                ),
                Assignment(
                    task_name='Recuts',
                    technician_id='b',
                    date_assigned=d,
                    time_slot=slot,
                    catalog_task_id='t2',
                ),
            ],
        )
        session.commit()

    with Session(engine) as session:
        draft = load_draft_overrides_for_slice(session, d, slot)
    manual = {a.technician_id: a for a in draft['manual_assignments']}
    assert manual['a'].eligibility_overridden is True
    assert manual['b'].eligibility_overridden is False

    with Session(engine) as session:
        confirm_draft_overrides_for_slice(session, d, slot)
        session.commit()

    with Session(engine) as session:
        audit = load_confirmed_override_rows_for_slice(session, d, slot)
    by_tech = {row['tech_id']: row for row in audit}
    assert by_tech['a']['eligibility_overridden'] is True
    assert by_tech['b']['eligibility_overridden'] is False


def test_clear_draft_overrides_for_slice(engine) -> None:
    d = date(2026, 9, 2)
    slot = TimeSlot.PM
    with Session(engine) as session:
        session.add_all([_tech('a', 'Ann'), _tech('b', 'Ben')])
        replace_draft_day_availability_overrides(
            session,
            d,
            call_off_tech_ids=['a'],
            overtime_tech_ids_by_slot={TimeSlot.AM: [], TimeSlot.MID: [], TimeSlot.PM: []},
        )
        replace_draft_manual_assignments_for_slice(
            session,
            d,
            slot,
            [Assignment('Recuts', 'b', d, slot)],
        )
        session.commit()

    with Session(engine) as session:
        deleted = clear_draft_overrides_for_slice(session, d, slot)
        session.commit()
    assert deleted == 2
