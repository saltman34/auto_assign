'''
Greedy one-to-one matching: task slots to technicians by descending compatibility.

Processes **most constrained** task slots first (fewest pool members who do not
dislike that task), then picks the highest-scoring remaining technician with
random tie breaks—see ``docs/assignment_algorithm.md``.
'''
from __future__ import annotations

import random
from collections.abc import Mapping, Sequence

from auto_assign.domain import Assignment
from auto_assign.domain.entities import Tech
from auto_assign.ingestion import TaskRequest, ScheduleRow

from .compatibility_scoring import compatibility_score, non_disliker_count
from .scoring_types import (
    AssignmentScoringContext,
    ScoringWeights,
    TechScoringProfile,
    build_pool_scoring_profiles,
)
from .scoring_weights_config import DEFAULT_SCORING_WEIGHTS


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


def assign_greedy(
    task_requests: list[TaskRequest],
    available_techs: list[ScheduleRow],
    *,
    scoring_context: AssignmentScoringContext,
    tech_profiles_by_name: Mapping[str, Tech] | None = None,
    weights: ScoringWeights | None = None,
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
        ``rng``: Random source for breaking **score** ties; new ``Random()`` if ``None``.

    Returns:
        A list of ``Assignment`` rows, **one per input tech**, in **slot processing
        order** (most constrained slot first), not alphabetical by technician.
        Each row uses ``chosen_row.work_date``, ``scoring_context.time_slot``, and
        ``technician_id`` = ``tech_id`` from the scoring profile (resolved from schedule name).
    '''
    if rng is None:
        rng = random.Random()
    w = weights if weights is not None else DEFAULT_SCORING_WEIGHTS

    # (ScheduleRow, TechScoringProfile) pairs; list so we can remove assigned techs in place.
    pool = list(build_pool_scoring_profiles(available_techs, tech_profiles_by_name))
    task_slots = _expand_task_slots(task_requests)
    # Indices into task_slots: fill hardest slots first using current pool dislike sets.
    order = _slot_indices_most_constrained_first(task_slots, [p for _, p in pool])

    assignments: list[Assignment] = []
    time_slot = scoring_context.time_slot

    for slot_index in order:
        task_name = task_slots[slot_index]
        scored: list[tuple[float, ScheduleRow, TechScoringProfile]] = []
        for row, profile in pool:
            s = compatibility_score(profile, task_name, scoring_context, w)
            scored.append((s, row, profile))

        best_score = max(t[0] for t in scored)
        tied = [t for t in scored if t[0] == best_score]
        # Same top score: pick uniformly among tied techs so runs are reproducible with a fixed seed.
        _score, chosen_row, chosen_profile = rng.choice(tied)
        pool = [pair for pair in pool if pair[0] is not chosen_row]

        assignments.append(
            Assignment(
                task_name=task_name,
                technician_id=chosen_profile.tech_id,
                date_assigned=chosen_row.work_date,
                time_slot=time_slot,
            )
        )

    return assignments
