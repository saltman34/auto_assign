'''Tests for domain ``Tech`` → ORM upsert.'''

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from auto_assign.db import Base
from auto_assign.db.models.technician import Technician
from auto_assign.db.tech_repository import (
    find_tech_id_for_normalized_tech_name,
    load_tech_by_tech_id,
    merge_technician_from_tech,
    upsert_technicians,
)
from auto_assign.domain.entities import Tech
from auto_assign.domain.enums import DailyPreference


def _tech(tech_id: str = 'id-1', name: str = 'Sam') -> Tech:
    return Tech(
        tech_id=tech_id,
        tech_name=name,
        daily_preference=DailyPreference.CONSISTENCY,
        favorites=['A'],
        dislikes=[],
    )


def test_merge_inserts_then_updates() -> None:
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        merge_technician_from_tech(session, _tech())
        session.commit()
    with Session(engine) as session:
        row = session.get(Technician, 'id-1')
        assert row is not None
        assert row.tech_name == 'Sam'
        assert row.favorites == ['A']

    updated = _tech(name='Samuel')
    updated.favorites = ['B', 'C']
    updated.daily_preference = DailyPreference.VARIATION
    with Session(engine) as session:
        merge_technician_from_tech(session, updated)
        session.commit()
    with Session(engine) as session:
        row = session.get(Technician, 'id-1')
        assert row.tech_name == 'Samuel'
        assert row.favorites == ['B', 'C']
        assert row.daily_preference == DailyPreference.VARIATION


def test_upsert_technicians_count() -> None:
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        n = upsert_technicians(session, [_tech('a', 'A'), _tech('b', 'B')])
        session.commit()
        assert n == 2
        assert session.get(Technician, 'b') is not None


def test_load_tech_by_tech_id() -> None:
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        merge_technician_from_tech(session, _tech('x-1', 'Pat'))
        session.commit()
    with Session(engine) as session:
        assert load_tech_by_tech_id(session, 'missing') is None
        t = load_tech_by_tech_id(session, 'x-1')
        assert t is not None
        assert t.tech_id == 'x-1'
        assert t.tech_name == 'Pat'


def test_find_tech_id_for_normalized_tech_name() -> None:
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        merge_technician_from_tech(session, _tech('y-1', 'Jordan Lee'))
        session.commit()
    with Session(engine) as session:
        assert find_tech_id_for_normalized_tech_name(session, 'nobody') is None
        assert find_tech_id_for_normalized_tech_name(session, 'Jordan Lee') == 'y-1'
