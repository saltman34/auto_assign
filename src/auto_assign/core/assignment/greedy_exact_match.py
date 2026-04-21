'''
Exact one-to-one assignment for small technician pools (bitmask DP).

Used when ``GreedyOptimizationConfig.exact_fallback_max_pool_size`` allows it.
Keeps the heavy DP out of ``greedy_assigner`` so the main loop stays readable.
'''
from __future__ import annotations

import functools
from collections.abc import Sequence

from auto_assign.domain import Assignment
from auto_assign.ingestion import ScheduleRow

from .compatibility_scoring import NoEligibleTechnicianError, compatibility_score, task_is_disliked
from .scoring_types import (
    AssignmentScoringContext,
    ScoringWeights,
    TaskSlotRef,
    TechScoringProfile,
)


def assign_exact_small_pool(
    *,
    ordered_task_slots: Sequence[TaskSlotRef],
    pool: Sequence[tuple[ScheduleRow, TechScoringProfile]],
    scoring_context: AssignmentScoringContext,
    weights: ScoringWeights,
    strict_dislike_avoidance: bool,
) -> list[Assignment]:
    '''
    Max-weight perfect matching via DP over assignment permutations.

    ``pool`` and ``ordered_task_slots`` must have the same length N; runtime is
    O(N * N!) in the bitmask formulation—only suitable for small N (e.g. <= 9).

    Raises:
        NoEligibleTechnicianError: If some slot has no eligible technician in the pool.
    '''
    n_slots = len(ordered_task_slots)
    if n_slots == 0:
        return []
    if len(pool) != n_slots:
        raise ValueError('pool length must match ordered_task_slots length for exact matching')

    scores = [
        [
            compatibility_score(
                profile,
                ordered_task_slots[slot_i].catalog_task_id,
                ordered_task_slots[slot_i].task_name,
                scoring_context,
                weights,
            )
            for _, profile in pool
        ]
        for slot_i in range(n_slots)
    ]
    for slot_i in range(n_slots):
        if max(scores[slot_i]) == float('-inf'):
            slot = ordered_task_slots[slot_i]
            raise NoEligibleTechnicianError(slot.catalog_task_id, slot.task_name)

    disliked = [
        [task_is_disliked(profile, ordered_task_slots[slot_i].task_name) for _, profile in pool]
        for slot_i in range(n_slots)
    ]

    @functools.lru_cache(maxsize=None)
    def _solve(mask: int) -> tuple[int, float, tuple[int, ...]]:
        slot_i = mask.bit_count()
        if slot_i == n_slots:
            return (0, 0.0, ())

        best_non_disliked = -1
        best_score = float('-inf')
        best_tail: tuple[int, ...] = ()

        for tech_i in range(n_slots):
            if mask & (1 << tech_i):
                continue
            sub_non_disliked, sub_score, sub_tail = _solve(mask | (1 << tech_i))
            here_non_disliked = 0 if disliked[slot_i][tech_i] else 1
            total_non_disliked = sub_non_disliked + here_non_disliked
            total_score = sub_score + scores[slot_i][tech_i]

            if strict_dislike_avoidance:
                is_better = total_non_disliked > best_non_disliked or (
                    total_non_disliked == best_non_disliked and total_score > best_score
                )
            else:
                is_better = total_score > best_score

            if is_better:
                best_non_disliked = total_non_disliked
                best_score = total_score
                best_tail = (tech_i, *sub_tail)
        return (best_non_disliked, best_score, best_tail)

    _nondisliked_count, _score, tech_order = _solve(0)
    time_slot = scoring_context.time_slot
    out: list[Assignment] = []
    for slot_i, tech_i in enumerate(tech_order):
        row, profile = pool[tech_i]
        slot = ordered_task_slots[slot_i]
        out.append(
            Assignment(
                task_name=slot.task_name,
                catalog_task_id=slot.catalog_task_id,
                technician_id=profile.tech_id,
                date_assigned=row.work_date,
                time_slot=time_slot,
            )
        )
    return out
