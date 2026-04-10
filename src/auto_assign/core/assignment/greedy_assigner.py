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

from .compatibility_scoring import compatibility_score, non_disliker_count, task_is_disliked
from .greedy_exact_match import assign_exact_small_pool
from .greedy_local_swap import local_swap_improvement
from .scoring_types import (
    AssignmentScoringContext,
    GreedyOptimizationConfig,
    ScoringWeights,
    TechScoringProfile,
    build_pool_scoring_profiles,
)
from .scoring_weights_config import DEFAULT_SCORING_WEIGHTS

_logger = logging.getLogger(__name__)


def _expand_task_slots(task_requests: Sequence[TaskRequest]) -> list[str]:
    '''
    Purpose:
        Turn task requests (each with a count) into a flat list with one task
        name per headcount slot, in request order.

    Inputs:
        ``task_requests``: Non-empty sequence; each ``TaskRequest`` carries
        ``task_name``, ``task_count``, and shared date/slot metadata. Names are
        already normalized by ``TaskRequest`` validation.

    Returns:
        A list of length ``sum(tr.task_count)``; index ``i`` is the task name for
        slot ``i`` before any reordering by ``_slot_indices_most_constrained_first``.
    '''
    slots: list[str] = []
    for tr in task_requests:
        # One list entry per person needed for that task type (e.g. count 3 ⇒ three slots).
        for _ in range(tr.task_count):
            slots.append(tr.task_name)
    return slots


def _slot_indices_most_constrained_first(
    task_slots: Sequence[str],
    pool_profiles: Sequence[TechScoringProfile],
) -> list[int]:
    '''
    Purpose:
        Choose an order in which to fill task slots so hard slots (fewest techs
        willing to do the task) are decided before easy ones, reducing the chance
        of leaving an impossible slot at the end.

    Inputs:
        ``task_slots``: Flat slot list from ``_expand_task_slots`` (task name per index).
        ``pool_profiles``: One ``TechScoringProfile`` per candidate tech, same order
        as the greedy pool (used only to count who does **not** dislike each task).

    Returns:
        A permutation of ``range(len(task_slots))``: slot indices to process, hardest
        first. Ties on difficulty break by **ascending index** (stable, deterministic
        except where ``assign_greedy`` later uses ``rng`` for score ties).
    '''
    indexed = list(enumerate(task_slots))
    # Sort by (non_disliker_count, slot_index): lower count ⇒ harder ⇒ earlier; tie ⇒ lower index first.
    indexed.sort(key=lambda pair: (non_disliker_count(pair[1], pool_profiles), pair[0]))
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
    task_slots: Sequence[str],
    strict_dislike_avoidance: bool,
) -> tuple[int, int]:
    remaining_profiles = [profile for row, profile in pool if row is not chosen_row]
    if not remaining_profiles:
        return (0, 0)

    option_counts: list[int] = []
    for idx in remaining_slot_indices:
        task_name = task_slots[idx]
        non_dislikers = non_disliker_count(task_name, remaining_profiles)
        if strict_dislike_avoidance and non_dislikers == 0:
            option_counts.append(len(remaining_profiles))
        else:
            option_counts.append(non_dislikers)
    return (min(option_counts), sum(option_counts))


def _choose_best_candidate(
    scored: list[tuple[float, ScheduleRow, TechScoringProfile]],
    *,
    slot_index: int,
    slot_position_in_order: int,
    order: Sequence[int],
    task_slots: Sequence[str],
    pool: Sequence[tuple[ScheduleRow, TechScoringProfile]],
    strict_dislike_avoidance: bool,
    lookahead_tie_breaks: bool,
    rng: random.Random,
) -> tuple[float, ScheduleRow, TechScoringProfile]:
    task_name = task_slots[slot_index]
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
    Purpose:
        Produce exactly one ``Assignment`` per available technician by repeatedly
        picking a task slot (hardest first), assigning the remaining tech with
        highest compatibility score, and removing that tech from the pool.

    Inputs:
        ``task_requests``: Defines task names and counts; caller must ensure
        ``sum(task_count) == len(available_techs)`` (e.g. ``validate_task_requests``).
        ``available_techs``: Candidate techs for this date/shift only; order preserved
        when pairing with profiles (see ``build_pool_scoring_profiles``).
        ``scoring_context``: Current ``work_date``, ``time_slot``, confirmed history,
        and lookback for ``compatibility_score``.
        ``tech_profiles_by_name``: Optional ``tech_name`` → ``Tech``; missing names
        get neutral profiles inside ``build_pool_scoring_profiles``.
        ``weights``: Score coefficients; default ``DEFAULT_SCORING_WEIGHTS`` when ``None``.
        ``optimization``: Greedy extras (exact fallback, lookahead, swap pass); default
        ``GreedyOptimizationConfig()`` when ``None``.
        ``rng``: Random source for breaking **score** ties; new ``Random()`` if ``None``.

    Returns:
        A list of ``Assignment`` rows, **one per input tech**, in **slot processing
        order** (most constrained slot first), not alphabetical by technician.
        Each row uses ``chosen_row.work_date``, ``scoring_context.time_slot``, and
        ``technician_id`` = ``tech_id`` from the scoring profile (resolved from schedule name).

    Debugging:
        Set logging on ``auto_assign.core.assignment.greedy_assigner`` to DEBUG to log
        whether the exact small-pool path was taken (if enabled and pool size allows).
    '''
    if rng is None:
        rng = random.Random()
    w = weights if weights is not None else DEFAULT_SCORING_WEIGHTS
    opt = optimization if optimization is not None else GreedyOptimizationConfig()

    # (ScheduleRow, TechScoringProfile) pairs; list so we can remove assigned techs in place.
    pool = list(build_pool_scoring_profiles(available_techs, tech_profiles_by_name))
    all_profiles_by_tech_id = {profile.tech_id: profile for _, profile in pool}
    task_slots = _expand_task_slots(task_requests)
    # Indices into task_slots: fill hardest slots first using current pool dislike sets.
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
        task_name = task_slots[slot_index]
        scored: list[tuple[float, ScheduleRow, TechScoringProfile]] = []
        for row, profile in pool:
            s = compatibility_score(profile, task_name, scoring_context, w)
            scored.append((s, row, profile))

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
                task_name=task_name,
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
