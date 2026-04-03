'''Tests for transactional assignment slice replace (SQLite in-memory).'''

from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from auto_assign.db import (
    AssignmentRecord,
    Base,
    Technician,
    confirm_slice,
    count_confirmed_for_slice,
    load_draft_assignments_for_slice,
    replace_draft_slice,
    technician_ids_missing_from_db,
)
from auto_assign.domain import Assignment
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


def test_replace_draft_slice_deletes_then_inserts_ordered_slot_index(engine) -> None:
    d = date(2026, 7, 1)
    slot = TimeSlot.AM
    with Session(engine) as session:
        session.add(_tech('a', 'Ann'))
        session.add(_tech('b', 'Ben'))
        session.flush()
        replace_draft_slice(
            session,
            d,
            slot,
            [
                Assignment('Zebra', 'b', d, slot),
                Assignment('Alpha', 'a', d, slot),
            ],
        )
        session.commit()

    with Session(engine) as session:
        rows = session.scalars(select(AssignmentRecord).order_by(AssignmentRecord.slot_index)).all()
        assert len(rows) == 2
        assert rows[0].task_id == 'Alpha'
        assert rows[0].technician_id == 'a'
        assert rows[0].slot_index == 0
        assert rows[1].task_id == 'Zebra'
        assert rows[1].slot_index == 1
        assert all(r.status == AssignmentStatus.DRAFT for r in rows)

    with Session(engine) as session:
        replace_draft_slice(
            session,
            d,
            slot,
            [Assignment('Only', 'a', d, slot)],
        )
        session.commit()

    with Session(engine) as session:
        rows = session.scalars(
            select(AssignmentRecord).where(AssignmentRecord.work_date == d).order_by(AssignmentRecord.id)
        ).all()
        assert len(rows) == 1
        assert rows[0].task_id == 'Only'


def test_confirm_slice_removes_draft_and_confirmed(engine) -> None:
    d = date(2026, 8, 1)
    slot = TimeSlot.PM
    with Session(engine) as session:
        session.add(_tech('x', 'X'))
        session.flush()
        session.add(
            AssignmentRecord(
                technician_id='x',
                task_id='old_draft',
                work_date=d,
                time_slot=slot,
                status=AssignmentStatus.DRAFT,
                slot_index=0,
            )
        )
        session.add(
            AssignmentRecord(
                technician_id='x',
                task_id='old_conf',
                work_date=d,
                time_slot=slot,
                status=AssignmentStatus.CONFIRMED,
                slot_index=0,
            )
        )
        session.commit()

    with Session(engine) as session:
        assert count_confirmed_for_slice(session, d, slot) == 1
        confirm_slice(session, d, slot, [Assignment('Newtask', 'x', d, slot)])
        session.commit()

    with Session(engine) as session:
        rows = session.scalars(select(AssignmentRecord)).all()
        assert len(rows) == 1
        assert rows[0].status == AssignmentStatus.CONFIRMED
        assert rows[0].task_id == 'Newtask'
        assert count_confirmed_for_slice(session, d, slot) == 1


def test_load_draft_assignments_for_slice_returns_domain_ordered(engine) -> None:
    d = date(2026, 9, 1)
    slot = TimeSlot.MID
    with Session(engine) as session:
        session.add(_tech('p', 'Pat'))
        session.flush()
        replace_draft_slice(
            session,
            d,
            slot,
            [
                Assignment('Second', 'p', d, slot),
                Assignment('First', 'p', d, slot),
            ],
        )
        session.commit()

    with Session(engine) as session:
        out = load_draft_assignments_for_slice(session, d, slot)
    assert len(out) == 2
    assert [a.task_name for a in out] == ['First', 'Second']


def test_technician_ids_missing_from_db(engine) -> None:
    with Session(engine) as session:
        session.add(_tech('exists', 'Eve'))
        session.commit()

    with Session(engine) as session:
        miss = technician_ids_missing_from_db(session, ['exists', 'nope', 'exists', 'missing'])
    assert miss == ['nope', 'missing']
