'''Smoke tests for SQLAlchemy technician model (SQLite in-memory).'''

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from auto_assign.db import Base, Technician
from auto_assign.domain.enums import DailyPreference


def test_technicians_table_create_and_roundtrip() -> None:
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        t = Technician(
            tech_id='t-1',
            tech_name='alice',
            daily_preference=DailyPreference.CONSISTENCY,
            favorites=['scrolls'],
            dislikes=['grunge'],
        )
        session.add(t)
        session.commit()

    with Session(engine) as session:
        row = session.get(Technician, 't-1')
        assert row is not None
        assert row.tech_name == 'alice'
        assert row.favorites == ['scrolls']
        assert row.dislikes == ['grunge']
        assert row.daily_preference == DailyPreference.CONSISTENCY
