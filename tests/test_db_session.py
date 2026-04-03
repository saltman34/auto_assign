'''Tests for DB URL resolution and engine/session factory (SQLite via env).'''

import pytest

from auto_assign.db import Base, Technician
from auto_assign.db.session import (
    get_database_url,
    get_engine,
    get_session_factory,
    reset_engine_cache,
    session_scope,
)
from auto_assign.domain.enums import DailyPreference


@pytest.fixture(autouse=True)
def _clear_engine_cache() -> None:
    reset_engine_cache()
    yield
    reset_engine_cache()


def test_get_database_url_from_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.delenv('POSTGRES_USER', raising=False)
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///:memory:')
    reset_engine_cache()
    assert get_database_url() == 'sqlite:///:memory:'


def test_get_database_url_bare_postgresql_uses_psycopg3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr('auto_assign.db.session.load_dotenv', lambda *_a, **_k: None)
    monkeypatch.delenv('POSTGRES_USER', raising=False)
    monkeypatch.setenv('DATABASE_URL', 'postgresql://u:pw@localhost:5432/db')
    reset_engine_cache()
    assert get_database_url() == 'postgresql+psycopg://u:pw@localhost:5432/db'


def test_get_database_url_from_postgres_parts(monkeypatch: pytest.MonkeyPatch) -> None:
    # Avoid .env DATABASE_URL taking precedence over POSTGRES_* parts in this test.
    monkeypatch.setattr('auto_assign.db.session.load_dotenv', lambda *_a, **_k: None)
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.setenv('POSTGRES_USER', 'u')
    monkeypatch.setenv('POSTGRES_PASSWORD', 'p@ss')
    monkeypatch.setenv('POSTGRES_DB', 'mydb')
    monkeypatch.setenv('POSTGRES_HOST', 'db.example.com')
    monkeypatch.setenv('POSTGRES_PORT', '5433')
    reset_engine_cache()
    url = get_database_url()
    assert url.startswith('postgresql+psycopg://')
    assert 'p%40ss' in url
    assert 'db.example.com:5433' in url
    assert url.endswith('/mydb')


def test_get_database_url_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr('auto_assign.db.session.load_dotenv', lambda *_a, **_k: None)
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.delenv('POSTGRES_USER', raising=False)
    monkeypatch.delenv('POSTGRES_PASSWORD', raising=False)
    monkeypatch.delenv('POSTGRES_DB', raising=False)
    reset_engine_cache()
    with pytest.raises(ValueError, match='DATABASE_URL|POSTGRES'):
        get_database_url()


def test_engine_and_session_factory_sqlite_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///:memory:')
    reset_engine_cache()
    engine = get_engine()
    Base.metadata.create_all(engine)
    factory = get_session_factory()
    with factory() as session:
        session.add(
            Technician(
                tech_id='x',
                tech_name='pat',
                daily_preference=DailyPreference.CONSISTENCY,
                favorites=[],
                dislikes=[],
            )
        )
        session.commit()
    with factory() as session:
        assert session.get(Technician, 'x') is not None


def test_session_scope_commits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///:memory:')
    reset_engine_cache()
    Base.metadata.create_all(get_engine())
    with session_scope() as session:
        session.add(
            Technician(
                tech_id='y',
                tech_name='sam',
                daily_preference=DailyPreference.VARIATION,
                favorites=[],
                dislikes=[],
            )
        )
    factory = get_session_factory()
    with factory() as session:
        assert session.get(Technician, 'y') is not None
