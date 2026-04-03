'''
SQLAlchemy engine and ``sessionmaker`` from environment variables.

Loads ``.env`` from the project root (next to ``pyproject.toml``) on first use.
Configure either:

- ``DATABASE_URL`` — full SQLAlchemy URL. Prefer ``postgresql+psycopg://`` (psycopg v3). Bare
  ``postgresql://`` / ``postgres://`` is rewritten to ``postgresql+psycopg://`` automatically, or
- ``POSTGRES_USER``, ``POSTGRES_PASSWORD``, ``POSTGRES_DB``, optional ``POSTGRES_HOST`` (default
  ``localhost``), ``POSTGRES_PORT`` (default ``5432``).

Note: shell-style ``${VAR}`` expansion in ``.env`` is **not** applied by python-dotenv; use a
single ``DATABASE_URL`` or the discrete variables above.
'''
from __future__ import annotations

import os
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Iterator
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_dotenv_loaded = False


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _ensure_dotenv() -> None:
    global _dotenv_loaded
    if _dotenv_loaded:
        return
    load_dotenv(_project_root() / '.env')
    _dotenv_loaded = True


def _ensure_psycopg3_driver(url: str) -> str:
    '''
    Bare ``postgresql://`` / ``postgres://`` URLs make SQLAlchemy use the psycopg2 driver.
    This project depends on **psycopg** v3 only; rewrite to ``postgresql+psycopg://``.
    '''
    if url.startswith('postgresql+') or url.startswith('postgres+'):
        return url
    if url.startswith('postgresql://'):
        return 'postgresql+psycopg://' + url.removeprefix('postgresql://')
    if url.startswith('postgres://'):
        return 'postgresql+psycopg://' + url.removeprefix('postgres://')
    return url


def get_database_url() -> str:
    '''
    Resolve the database URL from the environment (after loading ``.env``).

    Raises:
        ValueError: If no usable URL or combination of POSTGRES_* variables is set.
    '''
    _ensure_dotenv()
    url = os.environ.get('DATABASE_URL', '').strip()
    if url:
        return _ensure_psycopg3_driver(url)

    user = os.environ.get('POSTGRES_USER')
    password = os.environ.get('POSTGRES_PASSWORD')
    db = os.environ.get('POSTGRES_DB')
    if user is None or db is None:
        raise ValueError(
            'Set DATABASE_URL or POSTGRES_USER, POSTGRES_PASSWORD (can be empty), and POSTGRES_DB'
        )
    host = os.environ.get('POSTGRES_HOST', 'localhost')
    port = os.environ.get('POSTGRES_PORT', '5432')
    pw = '' if password is None else password
    return (
        f'postgresql+psycopg://{quote_plus(user)}:{quote_plus(pw)}@{host}:{port}/{quote_plus(db)}'
    )


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    '''
    Shared ``Engine`` for the app (cached).

    ``pool_pre_ping`` avoids stale connections after idle timeouts (typical with Postgres).
    '''
    return create_engine(get_database_url(), pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    '''Bound ``sessionmaker``; call it to open a new ``Session`` (``factory()``).'''
    return sessionmaker(
        bind=get_engine(),
        class_=Session,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


@contextmanager
def session_scope() -> Iterator[Session]:
    '''
    Yield a session, commit on success, rollback on exception, always close.

    Example::

        with session_scope() as session:
            session.add(row)
    '''
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def reset_engine_cache() -> None:
    '''
    Clear cached engine and session factory (for tests or process reload).

    Disposes the engine if ``get_engine`` was already called at least once.
    Resets ``.env`` load state so the next call can reload environment (tests only).
    '''
    global _dotenv_loaded
    try:
        get_engine().dispose()
    except Exception:
        pass
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    _dotenv_loaded = False
