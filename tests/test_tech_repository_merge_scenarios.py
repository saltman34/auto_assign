'''DB merge / uniqueness scenarios for technician profiles (SQLite).'''

import pandas as pd
import pytest
from sqlalchemy.exc import IntegrityError

from auto_assign.core.csv_parsing.parse_tech_profiles import parse_tech_profiles
from auto_assign.db import Base, Technician, merge_technician_from_tech, session_scope
from auto_assign.db.adapters import tech_from_technician
from auto_assign.domain.entities import Tech
from auto_assign.domain.enums import DailyPreference


def _tech(
    tid: str,
    name: str,
    *,
    pref: DailyPreference = DailyPreference.CONSISTENCY,
    favorites: tuple[str, ...] = (),
    dislikes: tuple[str, ...] = (),
) -> Tech:
    return Tech(
        tech_id=tid,
        tech_name=name,
        daily_preference=pref,
        favorites=list(favorites),
        dislikes=list(dislikes),
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


def test_csv_whitespace_and_mixed_case_roundtrip_through_db(sqlite_engine) -> None:
    '''Enums, task lists, and ids/names tolerate extra spacing / casing through parse → DB → ORM.'''
    df = pd.DataFrame(
        [
            {
                'tech_id': '  t-pipeline  ',
                'tech_name': '  pat   doe  ',
                'daily_preference': '  VARIATION ',
                'favorites': ' clinicals  ;   GROSSING ',
                'dislikes': ' exhaust   checks ',
            }
        ]
    )
    techs = parse_tech_profiles(df)
    assert len(techs) == 1
    t0 = techs[0]
    assert t0.tech_id == 't-pipeline'
    assert t0.tech_name == 'Pat   Doe'
    assert t0.daily_preference == DailyPreference.VARIATION
    assert sorted(t0.favorites) == ['Clinicals', 'Grossing']
    assert t0.dislikes == ['Exhaust Checks']

    with session_scope() as session:
        merge_technician_from_tech(session, t0)

    with session_scope() as session:
        row = session.get(Technician, 't-pipeline')
        assert row is not None
        roundtrip = tech_from_technician(row)

    assert roundtrip.tech_id == 't-pipeline'
    assert roundtrip.tech_name == t0.tech_name
    assert roundtrip.daily_preference == DailyPreference.VARIATION
    assert sorted(roundtrip.favorites) == sorted(t0.favorites)
    assert roundtrip.dislikes == t0.dislikes


def test_second_insert_different_id_same_display_name_raises_integrity_error(
    sqlite_engine,
) -> None:
    with session_scope() as session:
        merge_technician_from_tech(session, _tech('a', 'pat'))
    with pytest.raises(IntegrityError):
        with session_scope() as session:
            merge_technician_from_tech(session, _tech('b', 'pat'))


def test_same_tech_id_updates_display_name(sqlite_engine) -> None:
    with session_scope() as session:
        merge_technician_from_tech(session, _tech('t1', 'first name'))
        merge_technician_from_tech(session, _tech('t1', 'second name'))

    with session_scope() as session:
        row = session.get(Technician, 't1')
        assert row is not None
        assert row.tech_name == 'Second Name'


def test_same_id_and_name_different_fields_overwrites(sqlite_engine) -> None:
    with session_scope() as session:
        merge_technician_from_tech(
            session,
            _tech('t1', 'pat', pref=DailyPreference.CONSISTENCY, favorites=('Scrolls',)),
        )
        merge_technician_from_tech(
            session,
            _tech('t1', 'pat', pref=DailyPreference.VARIATION, favorites=('Embedding',), dislikes=('Grossing',)),
        )

    with session_scope() as session:
        row = session.get(Technician, 't1')
        assert row is not None
        assert row.daily_preference == DailyPreference.VARIATION
        assert row.favorites == ['Embedding']
        assert row.dislikes == ['Grossing']


def test_batch_merge_overwrites_multiple_technicians(sqlite_engine) -> None:
    batch1 = [
        _tech('x', 'alex', pref=DailyPreference.CONSISTENCY, favorites=('Clinicals',)),
        _tech('y', 'blake', pref=DailyPreference.CONSISTENCY, dislikes=('Recuts',)),
        _tech('z', 'casey', pref=DailyPreference.CONSISTENCY),
    ]
    batch2 = [
        _tech('x', 'alex', pref=DailyPreference.VARIATION, favorites=('Scrolls',)),
        _tech('y', 'blake', pref=DailyPreference.VARIATION, dislikes=()),
        _tech('z', 'casey', pref=DailyPreference.VARIATION),
    ]

    with session_scope() as session:
        for t in batch1:
            merge_technician_from_tech(session, t)
        for t in batch2:
            merge_technician_from_tech(session, t)

    with session_scope() as session:
        rx = session.get(Technician, 'x')
        ry = session.get(Technician, 'y')
        rz = session.get(Technician, 'z')
        assert rx is not None and ry is not None and rz is not None
        assert rx.daily_preference == DailyPreference.VARIATION and rx.favorites == ['Scrolls']
        assert ry.daily_preference == DailyPreference.VARIATION and ry.dislikes == []
        assert rz.daily_preference == DailyPreference.VARIATION
