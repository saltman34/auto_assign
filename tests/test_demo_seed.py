'''Tests for the demo-data seeder (SQLite in-memory).

The seeder runs the real greedy scorer against an in-memory database, so this
test also serves as a smoke test that the scoring → persistence round-trip
holds for the full fixture dataset.
'''
from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from auto_assign.db import (
    AssignmentRecord,
    Base,
    TaskCatalog,
    Technician,
    list_tasks,
)
from auto_assign.demo import (
    DEMO_TASKS,
    DEMO_TECHS,
    reset_demo_data,
    seed_demo_data,
)
from auto_assign.demo.csv_export import write_sample_csvs
from auto_assign.domain.enums import AssignmentStatus


@pytest.fixture
def session() -> Session:
    eng = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        yield s


_FIXED_TODAY = date(2026, 10, 1)


def test_seed_demo_data_populates_expected_tasks_and_techs(session: Session) -> None:
    result = seed_demo_data(session, today=_FIXED_TODAY)
    session.commit()

    assert result.tasks_created == len(DEMO_TASKS)
    assert result.technicians_upserted == len(DEMO_TECHS)

    tasks = list_tasks(session)
    assert {t.task_id for t in tasks} == {spec.task_id for spec in DEMO_TASKS}

    techs = session.execute(select(Technician)).scalars().all()
    assert {t.tech_id for t in techs} == {spec.tech_id for spec in DEMO_TECHS}


def test_seed_demo_data_populates_confirmed_history_in_lookback_window(
    session: Session,
) -> None:
    seed_demo_data(session, today=_FIXED_TODAY)
    session.commit()

    rows = session.execute(
        select(AssignmentRecord).where(AssignmentRecord.status == AssignmentStatus.CONFIRMED)
    ).scalars().all()

    assert len(rows) > 0, 'seeder should have written confirmed history'

    oldest = _FIXED_TODAY - timedelta(days=14)
    for rec in rows:
        assert oldest <= rec.work_date < _FIXED_TODAY, (
            f'confirmed row on {rec.work_date} falls outside the expected window '
            f'[{oldest}, {_FIXED_TODAY})'
        )


def test_seed_demo_data_returns_future_schedule_rows(session: Session) -> None:
    result = seed_demo_data(session, today=_FIXED_TODAY)

    assert len(result.future_schedule_rows) > 0
    future_dates = {r.work_date for r in result.future_schedule_rows}
    assert all(d >= _FIXED_TODAY for d in future_dates)
    # Each tech appears on each of the 7 future days.
    assert len(future_dates) == 7
    assert len(result.future_schedule_rows) == 7 * len(DEMO_TECHS)


def test_seed_demo_data_is_deterministic(session: Session) -> None:
    '''Two seeds with identical inputs should write identical confirmed rows.'''
    eng1 = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(eng1)
    eng2 = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(eng2)

    with Session(eng1) as s1:
        seed_demo_data(s1, today=_FIXED_TODAY, seed=42)
        s1.commit()
        rows1 = sorted(
            (r.work_date, r.time_slot.value, r.task_id, r.technician_id)
            for r in s1.execute(select(AssignmentRecord)).scalars().all()
        )
    with Session(eng2) as s2:
        seed_demo_data(s2, today=_FIXED_TODAY, seed=42)
        s2.commit()
        rows2 = sorted(
            (r.work_date, r.time_slot.value, r.task_id, r.technician_id)
            for r in s2.execute(select(AssignmentRecord)).scalars().all()
        )

    assert rows1 == rows2


def test_reset_demo_data_clears_all_seeded_rows(session: Session) -> None:
    seed_demo_data(session, today=_FIXED_TODAY)
    session.commit()
    assert session.execute(select(Technician)).scalars().first() is not None

    reset_demo_data(session)
    session.commit()

    assert session.execute(select(Technician)).scalars().first() is None
    assert session.execute(select(TaskCatalog)).scalars().first() is None
    assert session.execute(select(AssignmentRecord)).scalars().first() is None


def test_write_sample_csvs_produces_parseable_files(tmp_path) -> None:
    import pandas as pd

    from auto_assign.core.csv_parsing.parse_schedule import parse_schedule

    schedule_path, profiles_path = write_sample_csvs(tmp_path)
    assert schedule_path.exists()
    assert profiles_path.exists()

    schedule_df = pd.read_csv(schedule_path)
    rows = parse_schedule(schedule_df)
    assert len(rows) > 0

    profiles_df = pd.read_csv(profiles_path)
    assert set(profiles_df.columns) >= {
        'tech_id',
        'tech_name',
        'daily_preference',
        'favorites',
        'dislikes',
    }
    assert len(profiles_df) == len(DEMO_TECHS)
