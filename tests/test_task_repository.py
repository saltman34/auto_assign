'''Tests for DB-backed task catalog repository (SQLite in-memory).'''

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from auto_assign.db import (
    AssignmentRecord,
    Base,
    Technician,
    create_task,
    delete_task,
    list_tasks,
    set_task_default_count,
)
from auto_assign.domain.enums import AssignmentStatus, DailyPreference, TimeSlot


@pytest.fixture
def engine():
    eng = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(eng)
    return eng


def _tech(tech_id: str = 't1', name: str = 'Pat') -> Technician:
    return Technician(
        tech_id=tech_id,
        tech_name=name,
        daily_preference=DailyPreference.CONSISTENCY,
        favorites=[],
        dislikes=[],
    )


def test_create_and_list_tasks(engine) -> None:
    with Session(engine) as session:
        row = create_task(session, '  clinicals  ', default_count=2)
        session.commit()
        assert row.task_name == 'Clinicals'

    with Session(engine) as session:
        out = list_tasks(session)
    assert len(out) == 1
    assert out[0].task_name == 'Clinicals'
    assert out[0].default_count == 2


def test_update_default_count(engine) -> None:
    with Session(engine) as session:
        row = create_task(session, 'Grossing', default_count=0)
        set_task_default_count(session, row.task_id, 3)
        session.commit()

    with Session(engine) as session:
        out = list_tasks(session)
    assert out[0].default_count == 3


def test_delete_task_blocked_when_used_by_assignments(engine) -> None:
    with Session(engine) as session:
        row = create_task(session, 'Scrolls', default_count=1)
        task_id = row.task_id
        session.add(_tech('a', 'Ann'))
        session.add(
            AssignmentRecord(
                technician_id='a',
                task_id='Scrolls',
                work_date=date(2026, 1, 1),
                time_slot=TimeSlot.AM,
                status=AssignmentStatus.CONFIRMED,
                slot_index=0,
            )
        )
        session.commit()

    with Session(engine) as session:
        with pytest.raises(ValueError, match='assignment row'):
            delete_task(session, task_id)


def test_list_tasks_orders_alphabetically(engine) -> None:
    '''Tasks sort alphabetically by task_name for deterministic display.'''
    with Session(engine) as session:
        create_task(session, 'Recuts', default_count=1)
        create_task(session, 'Clinicals', default_count=2)
        create_task(session, 'Embedding', default_count=2)
        create_task(session, 'Grossing', default_count=1)
        session.commit()

    with Session(engine) as session:
        out = list_tasks(session)
    names = [t.task_name for t in out]
    assert names == ['Clinicals', 'Embedding', 'Grossing', 'Recuts']


def test_delete_task_blocked_when_used_by_tech_preferences(engine) -> None:
    with Session(engine) as session:
        row = create_task(session, 'Embedding', default_count=0)
        task_id = row.task_id
        session.add(
            Technician(
                tech_id='p1',
                tech_name='Pat',
                daily_preference=DailyPreference.CONSISTENCY,
                favorites=['Embedding'],
                dislikes=[],
            )
        )
        session.commit()

    with Session(engine) as session:
        with pytest.raises(ValueError, match='technician profile'):
            delete_task(session, task_id)
