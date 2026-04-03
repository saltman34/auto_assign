'''Tests for technician delete helpers (cascade assignments).'''

import pytest

from auto_assign.db import (
    AssignmentRecord,
    Base,
    Technician,
    delete_all_technicians,
    delete_technician,
    list_technicians,
    merge_technician_from_tech,
    session_scope,
)
from auto_assign.domain.entities import Tech
from auto_assign.domain.enums import AssignmentStatus, DailyPreference, TimeSlot


def _sample_tech(tid: str, name: str) -> Tech:
    return Tech(
        tech_id=tid,
        tech_name=name,
        daily_preference=DailyPreference.CONSISTENCY,
        favorites=[],
        dislikes=[],
    )


@pytest.fixture
def sqlite_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///:memory:')
    from auto_assign.db.session import get_engine, reset_engine_cache

    reset_engine_cache()
    engine = get_engine()
    Base.metadata.create_all(engine)
    yield engine
    reset_engine_cache()


def test_delete_technician_removes_assignments(sqlite_engine) -> None:
    from datetime import date

    with session_scope() as session:
        merge_technician_from_tech(session, _sample_tech('t1', 'pat'))
        session.add(
            AssignmentRecord(
                technician_id='t1',
                task_id='clinicals',
                work_date=date(2026, 1, 1),
                time_slot=TimeSlot.AM,
                status=AssignmentStatus.DRAFT,
                slot_index=0,
            )
        )

    with session_scope() as session:
        n_a, n_t = delete_technician(session, 't1')

    assert n_t == 1
    assert n_a >= 1

    with session_scope() as session:
        assert session.get(Technician, 't1') is None
        assert list_technicians(session) == []


def test_delete_all_technicians(sqlite_engine) -> None:
    with session_scope() as session:
        merge_technician_from_tech(session, _sample_tech('a', 'alice'))
        merge_technician_from_tech(session, _sample_tech('b', 'bob'))

    with session_scope() as session:
        n_a, n_t = delete_all_technicians(session)

    assert n_t == 2
    with session_scope() as session:
        assert list_technicians(session) == []
