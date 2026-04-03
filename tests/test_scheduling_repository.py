'''Tests for ``scheduling_repository`` loaders (SQLite in-memory).'''

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from auto_assign.db import Base
from auto_assign.db.models.assignment_record import AssignmentRecord
from auto_assign.db.models.technician import Technician
from auto_assign.db.scheduling_repository import (
    load_confirmed_assignments_for_scoring,
    load_tech_profiles_by_name,
)
from auto_assign.domain.enums import AssignmentStatus, DailyPreference, TimeSlot


def _tech_row(
    tech_id: str,
    tech_name: str,
) -> Technician:
    return Technician(
        tech_id=tech_id,
        tech_name=tech_name,
        daily_preference=DailyPreference.CONSISTENCY,
        favorites=[],
        dislikes=[],
    )


@pytest.fixture
def engine():
    eng = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(eng)
    return eng


def test_load_tech_profiles_by_name_keys_normalized(engine) -> None:
    with Session(engine) as session:
        session.add(_tech_row('id-a', 'alice'))
        session.add(_tech_row('id-b', 'Bob Smith'))
        session.commit()

    with Session(engine) as session:
        m = load_tech_profiles_by_name(session)
    assert set(m.keys()) == {'Alice', 'Bob Smith'}
    assert m['Alice'].tech_id == 'id-a'
    assert m['Bob Smith'].tech_id == 'id-b'


def test_load_tech_profiles_by_name_allowlist(engine) -> None:
    with Session(engine) as session:
        session.add(_tech_row('x', 'Ann'))
        session.add(_tech_row('y', 'Ben'))
        session.commit()

    with Session(engine) as session:
        m = load_tech_profiles_by_name(session, tech_ids=frozenset({'y'}))
    assert list(m.keys()) == ['Ben']


def test_load_tech_profiles_by_name_empty_allowlist(engine) -> None:
    with Session(engine) as session:
        session.add(_tech_row('x', 'Ann'))
        session.commit()
    with Session(engine) as session:
        assert load_tech_profiles_by_name(session, tech_ids=frozenset()) == {}


def test_load_tech_profiles_by_name_duplicate_normalized_key_raises(engine) -> None:
    with Session(engine) as session:
        session.add(_tech_row('t1', 'alice'))
        session.add(_tech_row('t2', 'Alice'))
        session.commit()

    with Session(engine) as session:
        with pytest.raises(ValueError, match='Duplicate technician map key'):
            load_tech_profiles_by_name(session)


def test_load_confirmed_assignments_for_scoring_filters_status_and_window(engine) -> None:
    d0 = date(2026, 6, 1)
    d10 = date(2026, 6, 10)
    d15 = date(2026, 6, 15)
    d20 = date(2026, 6, 20)

    with Session(engine) as session:
        session.add(_tech_row('tech1', 'Pat'))
        session.flush()
        session.add_all(
            [
                AssignmentRecord(
                    technician_id='tech1',
                    task_id='t1',
                    work_date=d10,
                    time_slot=TimeSlot.AM,
                    status=AssignmentStatus.CONFIRMED,
                    slot_index=0,
                ),
                AssignmentRecord(
                    technician_id='tech1',
                    task_id='t2',
                    work_date=d15,
                    time_slot=TimeSlot.AM,
                    status=AssignmentStatus.DRAFT,
                    slot_index=0,
                ),
                AssignmentRecord(
                    technician_id='tech1',
                    task_id='t3',
                    work_date=d0,
                    time_slot=TimeSlot.AM,
                    status=AssignmentStatus.CONFIRMED,
                    slot_index=0,
                ),
                AssignmentRecord(
                    technician_id='tech1',
                    task_id='t4',
                    work_date=d20,
                    time_slot=TimeSlot.AM,
                    status=AssignmentStatus.CONFIRMED,
                    slot_index=0,
                ),
            ]
        )
        session.commit()

    with Session(engine) as session:
        out = load_confirmed_assignments_for_scoring(session, d15, lookback_days=5)

    assert len(out) == 1
    assert out[0].task_name == 'T1'
    assert out[0].date_assigned == d10


def test_load_confirmed_assignments_lookback_none_returns_all_confirmed(engine) -> None:
    d1 = date(2026, 1, 1)
    d2 = date(2026, 2, 1)
    anchor = date(2026, 6, 1)

    with Session(engine) as session:
        session.add(_tech_row('t', 'X'))
        session.flush()
        session.add_all(
            [
                AssignmentRecord(
                    technician_id='t',
                    task_id='a',
                    work_date=d1,
                    time_slot=TimeSlot.PM,
                    status=AssignmentStatus.CONFIRMED,
                    slot_index=0,
                ),
                AssignmentRecord(
                    technician_id='t',
                    task_id='b',
                    work_date=d2,
                    time_slot=TimeSlot.PM,
                    status=AssignmentStatus.CONFIRMED,
                    slot_index=0,
                ),
            ]
        )
        session.commit()

    with Session(engine) as session:
        out = load_confirmed_assignments_for_scoring(session, anchor, lookback_days=None)

    assert len(out) == 2
    assert {a.task_name for a in out} == {'A', 'B'}
