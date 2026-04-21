'''
Greedy one-to-one matching: task slots to technicians by descending compatibility.

Orchestrates slot ordering, per-slot candidate selection (with optional lookahead
tie-breaks), optional exact small-pool solve, and optional local swap post-pass.

See also:
- ``compatibility_scoring`` — pure score for one tech–task pair
- ``greedy_exact_match`` — exact DP for small N
- ``greedy_local_swap`` — pairwise swap hill-climb
'''
from __future__ import annotations

import logging
import random
from collections.abc import Mapping, Sequence
from auto_assign.domain import Assignment
from auto_assign.domain.entities import Tech
from auto_assign.ingestion import TaskRequest, ScheduleRow

from .compatibility_scoring import (
    NoEligibleTechnicianError,
    compatibility_score,
    eligible_non_disliker_count,
    is_eligible_for_task,
    task_is_disliked,
)
from .greedy_exact_match import assign_exact_small_pool
from .greedy_local_swap import local_swap_improvement
from .scoring_types import (
    AssignmentScoringContext,
    GreedyOptimizationConfig,
    ScoringWeights,
    TaskSlotRef,
    TechScoringProfile,
    build_pool_scoring_profiles,
)
from .scoring_weights_config import DEFAULT_SCORING_WEIGHTS

_logger = logging.getLogger(__name__)


def _expand_task_slots(task_requests: Sequence[TaskRequest]) -> list[TaskSlotRef]:
    '''
    Turn task requests into one ``TaskSlotRef`` per headcount slot, in request order.
    '''
    slots: list[TaskSlotRef] = []
    for tr in task_requests:
        for _ in range(tr.task_count):
            slots.append(TaskSlotRef(catalog_task_id=tr.task_id, task_name=tr.task_name))
    return slots


def _slot_indices_most_constrained_first(
    task_slots: Sequence[TaskSlotRef],
    pool_profiles: Sequence[TechScoringProfile],
) -> list[int]:
    '''
    Fill slots with fewest **eligible** non-dislikers first (then ascending index).
    '''
    indexed = list(enumerate(task_slots))
    indexed.sort(
        key=lambda pair: (
            eligible_non_disliker_count(pair[1].catalog_task_id, pair[1].task_name, pool_profiles),
            pair[0],
        )
    )
    return [i for i, _ in indexed]


def _strict_candidate_set(
    scored: list[tuple[float, ScheduleRow, TechScoringProfile]],
    task_name: str,
    strict_dislike_avoidance: bool,
) -> list[tuple[float, ScheduleRow, TechScoringProfile]]:
    if not strict_dislike_avoidance:
        return scored
    non_dislikers = [t for t in scored if not task_is_disliked(t[2], task_name)]
    return non_dislikers if non_dislikers else scored


def _lookahead_key_for_candidate(
    chosen_row: ScheduleRow,
    *,
    pool: Sequence[tuple[ScheduleRow, TechScoringProfile]],
    remaining_slot_indices: Sequence[int],
    task_slots: Sequence[TaskSlotRef],
    strict_dislike_avoidance: bool,
) -> tuple[int, int]:
    remaining_profiles = [profile for row, profile in pool if row is not chosen_row]
    if not remaining_profiles:
        return (0, 0)

    option_counts: list[int] = []
    for idx in remaining_slot_indices:
        slot = task_slots[idx]
        n = eligible_non_disliker_count(slot.catalog_task_id, slot.task_name, remaining_profiles)
        if strict_dislike_avoidance and n == 0:
            option_counts.append(len(remaining_profiles))
        else:
            option_counts.append(n)
    return (min(option_counts), sum(option_counts))


def _choose_best_candidate(
    scored: list[tuple[float, ScheduleRow, TechScoringProfile]],
    *,
    slot_index: int,
    slot_position_in_order: int,
    order: Sequence[int],
    task_slots: Sequence[TaskSlotRef],
    pool: Sequence[tuple[ScheduleRow, TechScoringProfile]],
    strict_dislike_avoidance: bool,
    lookahead_tie_breaks: bool,
    rng: random.Random,
) -> tuple[float, ScheduleRow, TechScoringProfile]:
    task_name = task_slots[slot_index].task_name
    candidates = _strict_candidate_set(scored, task_name, strict_dislike_avoidance)
    best_score = max(t[0] for t in candidates)
    tied = [t for t in candidates if t[0] == best_score]
    if len(tied) == 1 or not lookahead_tie_breaks:
        return rng.choice(tied)

    remaining_slot_indices = order[slot_position_in_order + 1 :]
    best_key = None
    best_tied: list[tuple[float, ScheduleRow, TechScoringProfile]] = []
    for entry in tied:
        key = _lookahead_key_for_candidate(
            entry[1],
            pool=pool,
            remaining_slot_indices=remaining_slot_indices,
            task_slots=task_slots,
            strict_dislike_avoidance=strict_dislike_avoidance,
        )
        if best_key is None or key > best_key:
            best_key = key
            best_tied = [entry]
        elif key == best_key:
            best_tied.append(entry)
    return rng.choice(best_tied)


def assign_greedy(
    task_requests: list[TaskRequest],
    available_techs: list[ScheduleRow],
    *,
    scoring_context: AssignmentScoringContext,
    tech_profiles_by_name: Mapping[str, Tech] | None = None,
    weights: ScoringWeights | None = None,
    optimization: GreedyOptimizationConfig | None = None,
    rng: random.Random | None = None,
) -> list[Assignment]:
    '''
    Produce exactly one ``Assignment`` per available technician (see module docstring).

    Raises:
        NoEligibleTechnicianError: If a slot has no **eligible** technician in the pool.
    '''
    if rng is None:
        rng = random.Random()
    w = weights if weights is not None else DEFAULT_SCORING_WEIGHTS
    opt = optimization if optimization is not None else GreedyOptimizationConfig()

    pool = list(build_pool_scoring_profiles(available_techs, tech_profiles_by_name))
    all_profiles_by_tech_id = {profile.tech_id: profile for _, profile in pool}
    task_slots = _expand_task_slots(task_requests)
    order = _slot_indices_most_constrained_first(task_slots, [p for _, p in pool])
    ordered_task_slots = [task_slots[i] for i in order]

    if opt.exact_fallback_max_pool_size is not None and len(pool) <= opt.exact_fallback_max_pool_size:
        _logger.debug(
            'Using exact small-pool assignment (pool_size=%s, max=%s)',
            len(pool),
            opt.exact_fallback_max_pool_size,
        )
        exact_assignments = assign_exact_small_pool(
            ordered_task_slots=ordered_task_slots,
            pool=pool,
            scoring_context=scoring_context,
            weights=w,
            strict_dislike_avoidance=opt.strict_dislike_avoidance,
        )
        if opt.local_search_post_pass:
            return local_swap_improvement(
                exact_assignments,
                profiles_by_tech_id=all_profiles_by_tech_id,
                scoring_context=scoring_context,
                weights=w,
                strict_dislike_avoidance=opt.strict_dislike_avoidance,
            )
        return exact_assignments

    assignments: list[Assignment] = []
    time_slot = scoring_context.time_slot

    for slot_position, slot_index in enumerate(order):
        slot = task_slots[slot_index]
        scored: list[tuple[float, ScheduleRow, TechScoringProfile]] = []
        for row, profile in pool:
            if not is_eligible_for_task(profile, slot.catalog_task_id):
                continue
            s = compatibility_score(
                profile,
                slot.catalog_task_id,
                slot.task_name,
                scoring_context,
                w,
            )
            scored.append((s, row, profile))

        if not scored:
            raise NoEligibleTechnicianError(slot.catalog_task_id, slot.task_name)

        _score, chosen_row, chosen_profile = _choose_best_candidate(
            scored,
            slot_index=slot_index,
            slot_position_in_order=slot_position,
            order=order,
            task_slots=task_slots,
            pool=pool,
            strict_dislike_avoidance=opt.strict_dislike_avoidance,
            lookahead_tie_breaks=opt.lookahead_tie_breaks,
            rng=rng,
        )
        pool = [pair for pair in pool if pair[0] is not chosen_row]

        assignments.append(
            Assignment(
                task_name=slot.task_name,
                catalog_task_id=slot.catalog_task_id,
                technician_id=chosen_profile.tech_id,
                date_assigned=chosen_row.work_date,
                time_slot=time_slot,
            )
        )

    if opt.local_search_post_pass:
        return local_swap_improvement(
            assignments,
            profiles_by_tech_id=all_profiles_by_tech_id,
            scoring_context=scoring_context,
            weights=w,
            strict_dislike_avoidance=opt.strict_dislike_avoidance,
        )
    return assignments
