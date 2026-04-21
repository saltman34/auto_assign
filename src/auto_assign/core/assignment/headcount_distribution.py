'''Pure helpers for turning catalog ``default_count`` into Step 5 headcounts.

Step 5 of the schedule workflow asks the operator to split the available pool
across tasks. The catalog's ``default_count`` seeds that split, but catalog
defaults are aspirational — they can easily sum to more than the actual pool on
a small day (e.g. catalog defaults = 9 with only 8 techs available). The old
cascade clamp zeroed out whichever task happened to come first in catalog
order, which was both unfair and surprising.

``distribute_defaults_across_pool`` replaces that with a proportional split:

1. Each task with a positive ``default_count`` gets at least 1 slot, taken in
   ``(-default_count, input_index)`` order, while capacity remains.
2. Each task is topped up toward its ``default_count`` in the same order.
3. If ``sum(default_count) <= pool_size`` the raw defaults are returned
   unchanged — the operator keeps the remaining slots to assign by hand.

The helper is pure and deterministic so it can also be reused from the demo
seeder and from tests.
'''

from __future__ import annotations

from collections.abc import Sequence


def distribute_defaults_across_pool(
    defaults: Sequence[tuple[str, int]],
    pool_size: int,
) -> dict[str, int]:
    '''Split ``pool_size`` across ``defaults`` fairly.

    Args:
        defaults: ``(task_id, default_count)`` pairs in catalog (display) order.
            ``default_count`` is treated as non-negative; negatives are clamped
            to ``0``.
        pool_size: Number of technicians available for this slice. Non-positive
            values produce an all-zero result.

    Returns:
        A ``{task_id: count}`` mapping whose values are non-negative integers.

        * If ``sum(default_count) <= pool_size``: each task receives its full
          default; the caller retains ``pool_size - sum(defaults)`` headroom to
          allocate manually.
        * Otherwise: counts are scaled down so they sum to exactly ``pool_size``,
          and no task with a positive default ends at ``0`` until capacity is
          exhausted. Higher ``default_count`` receives its "seat" and top-up
          first; catalog order breaks ties.
    '''
    clean: list[tuple[int, str, int]] = [
        (idx, tid, max(int(default_count), 0))
        for idx, (tid, default_count) in enumerate(defaults)
    ]
    result: dict[str, int] = {tid: 0 for _, tid, _ in clean}

    if pool_size <= 0 or not clean:
        return result

    total_default = sum(d for _, _, d in clean)
    if total_default <= pool_size:
        for _, tid, d in clean:
            result[tid] = d
        return result

    fill_order = sorted(clean, key=lambda item: (-item[2], item[0]))
    remaining = pool_size

    for _, tid, d in fill_order:
        if remaining <= 0:
            break
        if d <= 0:
            continue
        result[tid] = 1
        remaining -= 1

    for _, tid, d in fill_order:
        if remaining <= 0:
            break
        headroom = d - result[tid]
        if headroom <= 0:
            continue
        add = min(headroom, remaining)
        result[tid] += add
        remaining -= add

    return result
