'''Smoke tests for SQLAlchemy assignment rows (SQLite in-memory).'''

from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from auto_assign.db import AssignmentRecord, Base, Technician
from auto_assign.domain.enums import AssignmentStatus, DailyPreference, TimeSlot


def _make_tech(tech_id: str = 't-1') -> Technician:
    return Technician(
        tech_id=tech_id,
        tech_name='alice',
        daily_preference=DailyPreference.CONSISTENCY,
        favorites=[],
        dislikes=[],
    )


def test_assignments_table_fk_and_roundtrip() -> None:
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    d = date(2026, 4, 1)
    with Session(engine) as session:
        session.add(_make_tech())
        session.flush()
        row = AssignmentRecord(
            technician_id='t-1',
            task_id='scrolls',
            work_date=d,
            time_slot=TimeSlot.AM,
            status=AssignmentStatus.CONFIRMED,
            slot_index=0,
        )
        session.add(row)
        session.commit()

    with Session(engine) as session:
        r = session.scalars(select(AssignmentRecord)).one()
        assert r.task_id == 'scrolls'
        assert r.work_date == d
        assert r.time_slot == TimeSlot.AM
        assert r.status == AssignmentStatus.CONFIRMED
        assert r.slot_index == 0
        assert r.technician.tech_name == 'alice'


def test_technician_assignments_relationship() -> None:
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    d = date(2026, 4, 2)
    with Session(engine) as session:
        tech = _make_tech('t-2')
        tech.assignments.append(
            AssignmentRecord(
                technician_id='t-2',
                task_id='recuts',
                work_date=d,
                time_slot=TimeSlot.MID,
                status=AssignmentStatus.DRAFT,
                slot_index=0,
            )
        )
        session.add(tech)
        session.commit()

    with Session(engine) as session:
        t = session.get(Technician, 't-2')
        assert t is not None
        assert len(t.assignments) == 1
        assert t.assignments[0].status == AssignmentStatus.DRAFT
