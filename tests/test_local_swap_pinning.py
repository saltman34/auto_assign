'''Regression test: local-swap post-pass must not relocate pinned technicians.'''

from datetime import date

from auto_assign.core.assignment.greedy_local_swap import local_swap_improvement
from auto_assign.core.assignment.scoring_types import (
    AssignmentScoringContext,
    ScoringWeights,
    tech_scoring_profile_from_entity,
)
from auto_assign.domain import Assignment
from auto_assign.domain.entities import Tech
from auto_assign.domain.enums import DailyPreference, TimeSlot


def _tech(tech_id: str, name: str, favorites: list[str] | None = None) -> Tech:
    return Tech(
        tech_id=tech_id,
        tech_name=name,
        daily_preference=DailyPreference.CONSISTENCY,
        favorites=favorites or [],
        dislikes=[],
    )


def test_pinned_tech_is_not_swapped_even_when_profitable() -> None:
    '''
    Scenario: both techs are eligible and swapping A onto Beta / B onto Alpha is strictly
    higher scoring (B favors Alpha; A has no preferences), but A is pinned. The swap must
    be rejected even though it would normally improve the score.
    '''
    work_date = date(2026, 10, 10)
    slot = TimeSlot.AM
    a = _tech('a', 'Ann')
    b = _tech('b', 'Ben', favorites=['Alpha'])
    profiles = {
        'a': tech_scoring_profile_from_entity(a),
        'b': tech_scoring_profile_from_entity(b),
    }
    ctx = AssignmentScoringContext(work_date, slot, (), None)
    weights = ScoringWeights(favorite_bonus=100.0)

    assignments = [
        Assignment('Alpha', 'a', work_date, slot),
        Assignment('Beta', 'b', work_date, slot),
    ]

    unpinned = local_swap_improvement(
        list(assignments),
        profiles_by_tech_id=profiles,
        scoring_context=ctx,
        weights=weights,
        strict_dislike_avoidance=False,
    )
    by_tech_unpinned = {x.technician_id: x.task_name for x in unpinned}
    assert by_tech_unpinned['b'] == 'Alpha'

    pinned = local_swap_improvement(
        list(assignments),
        profiles_by_tech_id=profiles,
        scoring_context=ctx,
        weights=weights,
        strict_dislike_avoidance=False,
        pinned_tech_ids=frozenset({'a'}),
    )
    by_tech_pinned = {x.technician_id: x.task_name for x in pinned}
    assert by_tech_pinned['a'] == 'Alpha'
    assert by_tech_pinned['b'] == 'Beta'
