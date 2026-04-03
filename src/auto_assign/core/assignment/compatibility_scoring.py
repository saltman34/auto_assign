'''
Pure compatibility score for one technician and one task name.

Implements the additive model from ``docs/assignment_algorithm.md`` without
I/O or assignment side effects, so unit tests can pin each term independently.
'''
from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

from auto_assign.domain import Assignment
from auto_assign.domain.enums import DailyPreference
from auto_assign.domain.validators.primitives import normalize_string, normalize_tech_id

from .scoring_types import AssignmentScoringContext, ScoringWeights, TechScoringProfile


def _assignment_in_lookback(a: Assignment, ctx: AssignmentScoringContext) -> bool:
    '''
    Purpose:
        Decide whether one past assignment should count toward fairness scoring
        (repeat-dislike and disliked-task load) for the current scheduling run.

    Inputs:
        ``a``: A single confirmed past assignment (who, what task, which date/slot).
        ``ctx``: The current run's context, including ``work_date``, ``lookback_days``,
        and the full list of confirmed history the caller supplied.

    Returns:
        ``True`` if ``a.date_assigned`` lies between the lookback cutoff and
        ``ctx.work_date`` (inclusive), or if ``lookback_days`` is ``None`` (use all
        supplied rows). Otherwise ``False``.
    '''
    # If no lookback window configured: every supplied confirmed row counts toward fairness terms.
    if ctx.lookback_days is None:
        return True

    # Only consider history from (work_date - lookback ) through work_date inclusive (no future rows).
    cutoff = ctx.work_date - timedelta(days=ctx.lookback_days)
    return cutoff <= a.date_assigned <= ctx.work_date


def _confirmed_for_fairness(ctx: AssignmentScoringContext) -> list[Assignment]:
    '''
    Purpose:
        Produce the slice of ``ctx.confirmed_assignments`` that may be used for
        fairness-related score terms, using one shared date-window rule.

    Inputs:
        ``ctx``: Must include ``confirmed_assignments`` (caller should pass only
        published/confirmed rows per product rules) and ``work_date`` / ``lookback_days``.

    Returns:
        A new list containing only assignments for which ``_assignment_in_lookback``
        is true. Empty if none qualify.
    '''
    return [a for a in ctx.confirmed_assignments if _assignment_in_lookback(a, ctx)]


def _tech_matches_assignment(profile: TechScoringProfile, assignment: Assignment) -> bool:
    '''
    Purpose:
        Tell whether a past assignment row refers to the same person as ``profile``.

    Inputs:
        ``profile``: Scoring view for one technician (uses ``tech_name``).
        ``assignment``: Past row; identity is compared via ``technician_id``.

    Returns:
        ``True`` if normalized names match, else ``False``.
    '''
    return normalize_tech_id(assignment.technician_id) == normalize_tech_id(profile.tech_id)


def _count_disliked_task_repeats(
    profile: TechScoringProfile,
    task_name: str,
    ctx: AssignmentScoringContext,
) -> int:
    '''
    Purpose:
        Count how many times this tech was already assigned this **same** task in
        the fairness window, **only when** that task is on their dislike list.
        Used to add an extra penalty for repeating disliked work.

    Inputs:
        ``profile``: Technician favorites/dislikes and identity.
        ``task_name``: Candidate task name for the slot being scored.
        ``ctx``: Confirmed history and date/slot for the current run.

    Returns:
        A non-negative integer; ``0`` if the task is not disliked or there are
        no matching historical rows in the window.
    '''
    task_n = normalize_string(task_name)
    # If they do not dislike this task, we do not apply the "repeat disliked task" penalty term.
    if task_n not in profile.dislikes:
        return 0
    # Count prior confirmed placements of this exact task for this tech (within the window).
    return sum(
        1
        for a in _confirmed_for_fairness(ctx)
        if _tech_matches_assignment(profile, a) and normalize_string(a.task_name) == task_n
    )


def _count_any_disliked_assignments(profile: TechScoringProfile, ctx: AssignmentScoringContext) -> int:
    '''
    Purpose:
        Count how many confirmed assignments in the window gave this tech **any**
        task on their dislike list—drives rotation when many people dislike the
        same kind of work.

    Inputs:
        ``profile``: Technician identity and dislike set (empty dislikes ⇒ always 0).
        ``ctx``: Confirmed history and window settings.

    Returns:
        A non-negative integer count of matching historical rows.
    '''
    if not profile.dislikes:
        return 0
    dis = profile.dislikes
    # Each past confirmed row where the task was on their dislike list increases the load penalty.
    return sum(
        1
        for a in _confirmed_for_fairness(ctx)
        if _tech_matches_assignment(profile, a) and normalize_string(a.task_name) in dis
    )


def _other_slot_same_day_assignment(
    profile: TechScoringProfile,
    ctx: AssignmentScoringContext,
) -> Assignment | None:
    '''
    Purpose:
        Find a confirmed assignment for the same tech on the **same calendar day**
        but a **different** time band than ``ctx.time_slot``, so consistency vs
        variation bonuses can compare tasks across AM/MID/PM.

    Inputs:
        ``profile``: Technician identity.
        ``ctx``: Includes ``work_date``, ``time_slot`` being scored, and full
        ``confirmed_assignments`` (not only the fairness-filtered list).

    Returns:
        The first matching ``Assignment`` in iteration order, or ``None`` if
        there is no other-slot same-day row for this tech.
    '''
    for a in ctx.confirmed_assignments:
        if not _tech_matches_assignment(profile, a):
            continue
        # Same-day preference compares across slots, not across different dates.
        if a.date_assigned != ctx.work_date:
            continue
        # We are scoring the current slot (ctx.time_slot); ignore rows for that same band.
        if a.time_slot == ctx.time_slot:
            continue
        return a
    return None


def compatibility_score(
    profile: TechScoringProfile,
    task_name: str,
    ctx: AssignmentScoringContext,
    weights: ScoringWeights,
) -> float:
    '''
    Purpose:
        Compute a single **higher-is-better** number for assigning ``task_name``
        to the technician described by ``profile``, combining favorites, dislikes,
        fairness history, and same-day preference.

    Inputs:
        ``profile``: Technician scoring view (favorites, dislikes, daily preference).
        ``task_name``: Task label for the open slot (normalized internally for comparisons).
        ``ctx``: Current ``work_date``, ``time_slot``, confirmed history, lookback.
        ``weights``: Numeric bonuses and penalties for each score term.

    Returns:
        A ``float`` score (not normalized); ties in the greedy assigner are broken
        elsewhere. Tasks neither favorited nor disliked still get fairness and
        same-day terms when applicable.
    '''
    task_n = normalize_string(task_name)
    score = 0.0

    # Explicit preference: reward tasks the tech marked as favorites.
    if task_n in profile.favorites:
        score += weights.favorite_bonus

    if task_n in profile.dislikes:
        # Base cost for assigning work they dislike.
        score -= weights.dislike_base_penalty
        repeats = _count_disliked_task_repeats(profile, task_name, ctx)
        # Extra cost scales with how often they already did this disliked task (capped to avoid runaway penalties).
        capped = min(repeats, weights.max_repeat_penalty_multiplier)
        score -= weights.disliked_task_repeat_penalty * capped

    # Penalty grows with total past disliked-task exposure—helps rotate widely disliked work.
    disliked_load = _count_any_disliked_assignments(profile, ctx)
    score -= weights.fairness_disliked_load_penalty * disliked_load

    # Same calendar day, different shift: compare candidate task to what they already have confirmed.
    other = _other_slot_same_day_assignment(profile, ctx)
    if other is not None:
        other_task = normalize_string(other.task_name)
        if profile.daily_preference == DailyPreference.CONSISTENCY:
            # Bonus when the new task matches the task they already hold earlier/later that day.
            if other_task == task_n:
                score += weights.consistency_bonus
        elif profile.daily_preference == DailyPreference.VARIATION:
            # Bonus when the new task differs from their other slot that day.
            if other_task != task_n:
                score += weights.variation_bonus

    return score


def non_disliker_count(task_name: str, profiles: Sequence[TechScoringProfile]) -> int:
    '''
    Purpose:
        Count how many technicians in the candidate pool **do not** list the given
        task as a dislike—used to sort task slots so the **most constrained**
        (fewest willing techs) are filled first in the greedy assigner.

    Inputs:
        ``task_name``: Task label for the slot (normalized internally).
        ``profiles``: One scoring profile per person still available in the pool.

    Returns:
        A non-negative integer; ``len(profiles)`` if nobody dislikes this task.
    '''
    task_n = normalize_string(task_name)
    # Pool members who do not dislike this task are "less constrained" options for that slot.
    return sum(1 for p in profiles if task_n not in p.dislikes)
