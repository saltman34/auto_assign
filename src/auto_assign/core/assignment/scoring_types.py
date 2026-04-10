'''
Types and builders for compatibility scoring (greedy assignment).

Separated from numeric scoring logic so context and profiles stay easy to test
and swap without touching the greedy loop. Default coefficient values live in
``scoring_weights_config``.
'''
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from auto_assign.domain import Assignment
from auto_assign.domain.entities import Tech
from auto_assign.domain.enums import DailyPreference, TimeSlot
from auto_assign.domain.validators.primitives import normalize_string, normalize_tech_id
from auto_assign.ingestion import ScheduleRow


@dataclass(frozen=True)
class ScoringWeights:
    '''
    Tunable coefficients for the additive compatibility score.

    All values are in abstract "points"; tune together so no single term
    dominates unless intended.
    '''

    favorite_bonus: float = 2.0
    dislike_base_penalty: float = 3.0
    # Extra penalty when assigning a disliked task the tech already drew
    # (within the fairness window); multiplied by occurrence count, capped below.
    disliked_task_repeat_penalty: float = 2.0
    max_repeat_penalty_multiplier: int = 5
    # Penalty per historical confirmed assignment where the tech worked any
    # task on their dislike list (within the fairness window).
    fairness_disliked_load_penalty: float = 1.0
    consistency_bonus: float = 3.0
    variation_bonus: float = 3.0


@dataclass(frozen=True)
class GreedyOptimizationConfig:
    '''
    Optional strategy upgrades layered on top of baseline greedy assignment.

    - ``local_search_post_pass``: pairwise swap hill-climb after greedy fill.
    - ``lookahead_tie_breaks``: when score ties occur, pick the candidate that
      preserves better future options for remaining slots.
    - ``exact_fallback_max_pool_size``: if pool size <= this value, solve the
      full assignment exactly (max-weight matching via DP) instead of greedy.
      Set to ``None`` to disable exact fallback.
    - ``strict_dislike_avoidance``: prefer solutions that avoid disliked tasks
      whenever a feasible alternative exists.
    '''

    local_search_post_pass: bool = True
    lookahead_tie_breaks: bool = True
    exact_fallback_max_pool_size: int | None = 9
    strict_dislike_avoidance: bool = True


@dataclass(frozen=True)
class AssignmentScoringContext:
    '''
    Everything needed to score a tech–task pair besides the pair itself.

    ``confirmed_assignments`` should be **published/confirmed** rows only (see
    docs); draft regenerations must not be included. ``lookback_days`` limits
    how far back fairness and repeat-dislike terms look; ``None`` means no
    date filter (use every supplied confirmed row).
    '''

    work_date: date
    time_slot: TimeSlot
    confirmed_assignments: tuple[Assignment, ...] = ()
    lookback_days: int | None = 14


@dataclass(frozen=True)
class TechScoringProfile:
    '''
    Minimal read-only view of a technician for scoring.

    Built from ``Tech`` when a profile exists, or as a **neutral** profile when
    the schedule row has no matching persisted tech (no favorite/dislike signal).
    '''

    tech_name: str
    tech_id: str
    daily_preference: DailyPreference
    favorites: frozenset[str]
    dislikes: frozenset[str]


def tech_scoring_profile_from_entity(tech: Tech) -> TechScoringProfile:
    '''
    Purpose:
        Convert ``Tech`` entity into the minimal structure ``compatibility_score`` reads TechScoringProfile.

    Inputs:
        ``tech``: Full entity (already validated; favorites/dislikes lists are normalized).

    Returns:
        A ``TechScoringProfile`` with the same identity and preference data, and
        immutable copies of favorite/dislike sets.
    '''
    # frozenset copies list data so callers cannot mutate lists and affect a frozen profile.
    return TechScoringProfile(
        tech_name=tech.tech_name,
        tech_id=tech.tech_id,
        daily_preference=tech.daily_preference,
        favorites=frozenset(tech.favorites),
        dislikes=frozenset(tech.dislikes),
    )


def tech_scoring_profile_for_schedule_row(
    row: ScheduleRow,
    profiles_by_name: Mapping[str, Tech] | None,
) -> TechScoringProfile:
    '''
    Purpose:
        Pick the scoring view for one available pool row: full profile if we have
        persisted ``Tech`` data keyed by ``row.tech_name``, otherwise a **neutral**
        profile so scoring does not invent favorites/dislikes.

    Inputs:
        ``row``: Parsed schedule row for this tech on this day (name must match map keys).
        ``profiles_by_name``: Optional ``tech_name`` → ``Tech`` from CSV/DB; ``None`` or
        missing key triggers the neutral branch.

    Returns:
        ``TechScoringProfile`` for that row; neutral uses ``tech_id`` = trim(schedule name)
        (not a DB id until the row maps to a ``Tech``), empty sets, and ``CONSISTENCY``.
    '''
    name_key = normalize_string(row.tech_name)
    if profiles_by_name:
        tech = profiles_by_name.get(name_key)
        if tech is not None:
            return tech_scoring_profile_from_entity(tech)
    return TechScoringProfile(
        tech_name=name_key,
        tech_id=normalize_tech_id(row.tech_name),
        daily_preference=DailyPreference.CONSISTENCY,
        favorites=frozenset(),
        dislikes=frozenset(),
    )


def build_pool_scoring_profiles(
    available_techs: Sequence[ScheduleRow],
    profiles_by_name: Mapping[str, Tech] | None,
) -> tuple[tuple[ScheduleRow, TechScoringProfile], ...]:
    '''
    Purpose:
        Precompute one ``TechScoringProfile`` per schedule row in pool order so the
        greedy loop can score without repeated map lookups in the hot path. Where 
        "pool" refers to the list of available technicians for the current date and time slot.

    Inputs:
        ``available_techs``: Filtered list of available technicians for the current date and time slot (order preserved).
        ``profiles_by_name``: Optional mapping of tech names to Tech entities (used to build TechScoringProfile).

    Returns:
        An immutable tuple of ``(ScheduleRow, TechScoringProfile)`` pairs, one per available technician
        member, in the same order as ``available_techs``.
    '''
    return tuple(
        (row, tech_scoring_profile_for_schedule_row(row, profiles_by_name))
        for row in available_techs
    )
