'''Unit tests for ``distribute_defaults_across_pool``.'''

from __future__ import annotations

from auto_assign.core.assignment.headcount_distribution import (
    distribute_defaults_across_pool,
)


def test_defaults_fit_pool_returns_raw_defaults() -> None:
    '''When sum(defaults) <= pool_size the raw defaults are preserved.'''
    result = distribute_defaults_across_pool(
        [('A', 2), ('B', 2), ('C', 2)],
        pool_size=8,
    )
    assert result == {'A': 2, 'B': 2, 'C': 2}


def test_defaults_overshoot_pool_scales_down_and_sums_to_pool() -> None:
    '''When sum(defaults) > pool_size the total matches pool exactly.'''
    result = distribute_defaults_across_pool(
        [('A', 4), ('B', 4), ('C', 4)],
        pool_size=8,
    )
    assert sum(result.values()) == 8
    assert set(result) == {'A', 'B', 'C'}


def test_no_positive_task_is_starved_when_capacity_allows_it() -> None:
    '''Every task with a positive default gets >= 1 slot while capacity remains.'''
    result = distribute_defaults_across_pool(
        [('A', 5), ('B', 5), ('C', 5)],
        pool_size=8,
    )
    assert sum(result.values()) == 8
    for count in result.values():
        assert count >= 1


def test_tasks_with_zero_default_receive_zero() -> None:
    '''Zero-default tasks are skipped entirely even when sum exceeds pool.'''
    result = distribute_defaults_across_pool(
        [('A', 3), ('B', 0), ('C', 3)],
        pool_size=4,
    )
    assert result['B'] == 0
    assert result['A'] + result['C'] == 4


def test_higher_defaults_top_up_first() -> None:
    '''The task with higher default_count tops up first when capacity is tight.'''
    result = distribute_defaults_across_pool(
        [('A', 2), ('B', 5)],
        pool_size=5,
    )
    assert sum(result.values()) == 5
    assert result['B'] >= result['A']


def test_pool_size_zero_returns_all_zero() -> None:
    '''No capacity -> every task gets zero regardless of defaults.'''
    result = distribute_defaults_across_pool(
        [('A', 3), ('B', 3)],
        pool_size=0,
    )
    assert result == {'A': 0, 'B': 0}


def test_negative_pool_size_returns_all_zero() -> None:
    '''Negative pool size is defensive-cast to zero (seeders should not pass negatives).'''
    result = distribute_defaults_across_pool(
        [('A', 3), ('B', 3)],
        pool_size=-2,
    )
    assert result == {'A': 0, 'B': 0}


def test_pool_smaller_than_task_count_gives_slots_to_highest_defaults() -> None:
    '''With 3 tasks and a pool of 2, the two highest-default tasks each get 1.'''
    result = distribute_defaults_across_pool(
        [('A', 1), ('B', 4), ('C', 3)],
        pool_size=2,
    )
    assert sum(result.values()) == 2
    assert result['B'] == 1
    assert result['C'] == 1
    assert result['A'] == 0


def test_ties_broken_by_input_order() -> None:
    '''When two tasks share default_count and capacity is tight, input order breaks the tie.'''
    result = distribute_defaults_across_pool(
        [('first', 3), ('second', 3)],
        pool_size=5,
    )
    assert sum(result.values()) == 5
    assert result['first'] >= result['second']


def test_empty_defaults_returns_empty_dict() -> None:
    assert distribute_defaults_across_pool([], pool_size=10) == {}


def test_negative_default_is_clamped_to_zero() -> None:
    '''Negative defaults (shouldn't happen in practice) degrade safely to zero.'''
    result = distribute_defaults_across_pool(
        [('A', -3), ('B', 4)],
        pool_size=5,
    )
    assert result['A'] == 0
    assert result['B'] == 4


def test_result_is_deterministic_for_same_inputs() -> None:
    '''Same inputs produce identical outputs (no reliance on set/dict iteration).'''
    inputs = [('A', 4), ('B', 4), ('C', 4), ('D', 2)]
    first = distribute_defaults_across_pool(inputs, pool_size=9)
    second = distribute_defaults_across_pool(inputs, pool_size=9)
    assert first == second
    assert sum(first.values()) == 9
