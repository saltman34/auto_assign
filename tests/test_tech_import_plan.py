'''Tests for technician import planning and ``tech_profile_equals``.'''

import pytest

from auto_assign.db import Base, Technician, session_scope
from auto_assign.db.tech_import_plan import (
    apply_tech_import_plan,
    build_tech_import_plan,
    dedupe_tech_rows_last_wins,
)
from auto_assign.domain.entities import Tech, tech_profile_equals
from auto_assign.domain.enums import DailyPreference


def _tech(
    tid: str,
    name: str,
    *,
    pref: DailyPreference = DailyPreference.CONSISTENCY,
    fav: tuple[str, ...] = (),
    dis: tuple[str, ...] = (),
) -> Tech:
    return Tech(
        tech_id=tid,
        tech_name=name,
        daily_preference=pref,
        favorites=list(fav),
        dislikes=list(dis),
    )


def test_tech_profile_equals_order_insensitive_lists() -> None:
    a = _tech('a', 'pat', fav=('scrolls', 'clinicals'), dis=('grossing',))
    b = _tech('a', 'pat', fav=('clinicals', 'scrolls'), dis=('grossing',))
    assert tech_profile_equals(a, b)


def test_tech_profile_equals_false_on_field() -> None:
    a = _tech('a', 'pat')
    b = _tech('a', 'pat', pref=DailyPreference.VARIATION)
    assert not tech_profile_equals(a, b)


def test_dedupe_tech_rows_last_wins() -> None:
    rows = [_tech('x', 'first'), _tech('y', 'y'), _tech('x', 'second')]
    out = dedupe_tech_rows_last_wins(rows)
    assert [t.tech_id for t in out] == ['y', 'x']
    assert out[1].tech_name == 'Second'


@pytest.fixture
def sqlite_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///:memory:')
    from auto_assign.db.session import get_engine, reset_engine_cache

    reset_engine_cache()
    engine = get_engine()
    Base.metadata.create_all(engine)
    yield engine
    reset_engine_cache()


def test_build_plan_new_unchanged_update_name_blocked(sqlite_engine) -> None:
    incoming_a = _tech('a', 'alice')
    incoming_b = _tech('b', 'bob', fav=('scrolls',))
    with session_scope() as session:
        from auto_assign.db import merge_technician_from_tech

        merge_technician_from_tech(session, incoming_a)
        merge_technician_from_tech(session, incoming_b)

    same_as_a = _tech('a', 'alice')
    with session_scope() as session:
        plans_same = build_tech_import_plan(session, [same_as_a])
    assert len(plans_same) == 1
    assert plans_same[0].status == 'unchanged'

    changed_a = _tech('a', 'alice', pref=DailyPreference.VARIATION)
    steals_b_name = _tech('c', 'bob')
    brand_new = _tech('d', 'dana')

    with session_scope() as session:
        plans2 = build_tech_import_plan(session, [changed_a, steals_b_name, brand_new])
    st = {p.incoming.tech_id: p.status for p in plans2}
    assert st['a'] == 'update_pending'
    assert st['c'] == 'name_blocked'
    assert st['d'] == 'new'


def test_apply_respects_overwrite_and_skip_blocked(sqlite_engine) -> None:
    with session_scope() as session:
        from auto_assign.db import merge_technician_from_tech

        merge_technician_from_tech(session, _tech('a', 'alice'))

    changed = _tech('a', 'alice', pref=DailyPreference.VARIATION)
    blocked = _tech('b', 'alice')

    with session_scope() as session:
        plans = build_tech_import_plan(session, [changed, blocked])

    with session_scope() as session:
        with pytest.raises(ValueError, match='Cannot import'):
            apply_tech_import_plan(session, plans, overwrite_updates=True, skip_name_blocked=False)

    with session_scope() as session:
        w, u, warns = apply_tech_import_plan(
            session,
            plans,
            overwrite_updates=True,
            skip_name_blocked=True,
        )
    assert w == 1
    assert u == 0
    assert any('Skipped `b`' in x for x in warns)

    with session_scope() as session:
        row = session.get(Technician, 'a')
        assert row is not None
        assert row.daily_preference == DailyPreference.VARIATION


def test_apply_skip_update_without_overwrite(sqlite_engine) -> None:
    with session_scope() as session:
        from auto_assign.db import merge_technician_from_tech

        merge_technician_from_tech(session, _tech('a', 'alice', pref=DailyPreference.CONSISTENCY))

    changed = _tech('a', 'alice', pref=DailyPreference.VARIATION)
    with session_scope() as session:
        plans = build_tech_import_plan(session, [changed])

    with session_scope() as session:
        w, u, warns = apply_tech_import_plan(
            session,
            plans,
            overwrite_updates=False,
            skip_name_blocked=True,
        )
    assert w == 0
    assert u == 0
    assert len(warns) == 1

    with session_scope() as session:
        row = session.get(Technician, 'a')
        assert row is not None
        assert row.daily_preference == DailyPreference.CONSISTENCY
