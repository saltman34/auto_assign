'''Tests for compatibility scoring and greedy assignment (in-memory, no DB).'''

import random
from datetime import date

import pytest

from auto_assign.core.assignment import (
    AssignmentScoringContext,
    DEFAULT_SCORING_WEIGHTS,
    GreedyOptimizationConfig,
    NoEligibleTechnicianError,
    ScoringWeights,
    TaskSlotRef,
    assign_greedy,
    assign_tasks,
    compatibility_score,
    non_disliker_count,
    tech_scoring_profile_for_schedule_row,
    tech_scoring_profile_from_entity,
)
from auto_assign.core.assignment.greedy_assigner import _slot_indices_most_constrained_first
from auto_assign.domain import Assignment
from auto_assign.domain.entities import Tech
from auto_assign.domain.enums import DailyPreference, TaskProficiencyLevel, TimeSlot
from auto_assign.ingestion import ScheduleRow, TaskRequest


def _tech(
    name: str,
    *,
    favorites: list[str] | None = None,
    dislikes: list[str] | None = None,
    preference: DailyPreference = DailyPreference.CONSISTENCY,
    eligible_by_task_id: dict[str, bool] | None = None,
    proficiency_by_task_id: dict[str, TaskProficiencyLevel] | None = None,
) -> Tech:
    return Tech(
        tech_id=name.lower(),
        tech_name=name,
        daily_preference=preference,
        favorites=favorites or [],
        dislikes=dislikes or [],
        eligible_by_task_id=dict(eligible_by_task_id or {}),
        proficiency_by_task_id=dict(proficiency_by_task_id or {}),
    )


def _row(name: str, d: date | None = None) -> ScheduleRow:
    d = d or date(2026, 4, 1)
    return ScheduleRow(name, d, True, True, True)


@pytest.fixture
def work_date() -> date:
    return date(2026, 4, 1)


def test_compatibility_score_favorite_bonus(work_date: date) -> None:
    profile = tech_scoring_profile_from_entity(_tech('A', favorites=['Scrolls']))
    ctx = AssignmentScoringContext(work_date, TimeSlot.AM, (), None)
    w = ScoringWeights(favorite_bonus=5.0)
    assert compatibility_score(profile, '1', 'Scrolls', ctx, w) == 5.0
    assert compatibility_score(profile, '2', 'Other', ctx, w) == 0.0


def test_compatibility_score_dislike_and_repeat(work_date: date) -> None:
    # VARIATION avoids a consistency +bonus here (same task already on the other slot).
    profile = tech_scoring_profile_from_entity(
        _tech('A', dislikes=['Grunge'], preference=DailyPreference.VARIATION)
    )
    confirmed = (
        Assignment('Grunge', 'a', work_date, TimeSlot.PM),
    )
    ctx = AssignmentScoringContext(work_date, TimeSlot.AM, confirmed, lookback_days=30)
    w = ScoringWeights(
        dislike_base_penalty=10.0,
        disliked_task_repeat_penalty=2.0,
        max_repeat_penalty_multiplier=5,
        # Isolate repeat term; same row would also increment fairness load otherwise.
        fairness_disliked_load_penalty=0.0,
    )
    s = compatibility_score(profile, '1', 'Grunge', ctx, w)
    assert s == -(10.0 + 2.0)


def test_compatibility_score_consistency_same_day_other_slot(work_date: date) -> None:
    profile = tech_scoring_profile_from_entity(
        _tech('A', preference=DailyPreference.CONSISTENCY)
    )
    confirmed = (Assignment('Same', 'a', work_date, TimeSlot.MID),)
    ctx = AssignmentScoringContext(work_date, TimeSlot.AM, confirmed, None)
    w = ScoringWeights(consistency_bonus=4.0)
    assert compatibility_score(profile, '1', 'Same', ctx, w) == 4.0
    assert compatibility_score(profile, '2', 'Different', ctx, w) == 0.0


def test_compatibility_score_variation_bonus(work_date: date) -> None:
    profile = tech_scoring_profile_from_entity(
        _tech('A', preference=DailyPreference.VARIATION)
    )
    confirmed = (Assignment('First', 'a', work_date, TimeSlot.MID),)
    ctx = AssignmentScoringContext(work_date, TimeSlot.AM, confirmed, None)
    w = ScoringWeights(variation_bonus=7.0)
    assert compatibility_score(profile, '1', 'Second', ctx, w) == 7.0
    assert compatibility_score(profile, '2', 'First', ctx, w) == 0.0


def test_non_disliker_count(work_date: date) -> None:
    p1 = tech_scoring_profile_from_entity(_tech('A', dislikes=['Bad']))
    p2 = tech_scoring_profile_from_entity(_tech('B', dislikes=[]))
    assert non_disliker_count('Bad', (p1, p2)) == 1
    assert non_disliker_count('Good', (p1, p2)) == 2


def test_assign_greedy_prefers_favorite_when_one_slot_each(work_date: date) -> None:
    alice = _row('Alice', work_date)
    bob = _row('Bob', work_date)
    profiles = {
        'Alice': _tech('Alice', favorites=['T1'], dislikes=[]),
        'Bob': _tech('Bob', favorites=[], dislikes=[]),
    }
    reqs = [
        TaskRequest('1', 'T1', 1, work_date, TimeSlot.AM),
        TaskRequest('2', 'T2', 1, work_date, TimeSlot.AM),
    ]
    ctx = AssignmentScoringContext(work_date, TimeSlot.AM, (), None)

    out = assign_greedy(
        reqs,
        [alice, bob],
        scoring_context=ctx,
        tech_profiles_by_name=profiles,
        rng=random.Random(0),
    )
    by_tech = {a.technician_id: a.task_name for a in out}
    assert by_tech['alice'] == 'T1'


def test_assign_tasks_greedy_flag_matches_assign_greedy(work_date: date) -> None:
    alice = _row('Alice', work_date)
    bob = _row('Bob', work_date)
    profiles = {
        'Alice': _tech('Alice', favorites=['T1']),
        'Bob': _tech('Bob'),
    }
    reqs = [
        TaskRequest('1', 'T1', 1, work_date, TimeSlot.AM),
        TaskRequest('2', 'T2', 1, work_date, TimeSlot.AM),
    ]
    out = assign_tasks(
        reqs,
        [alice, bob],
        random_seed=42,
        use_greedy_assignment=True,
        tech_profiles_by_name=profiles,
    )
    assert {a.technician_id: a.task_name for a in out}['alice'] == 'T1'


def test_assign_tasks_legacy_shuffle_unchanged_without_flag(work_date: date) -> None:
    rows = [_row('A', work_date), _row('B', work_date)]
    reqs = [
        TaskRequest('1', 'T', 2, work_date, TimeSlot.AM),
    ]
    out = assign_tasks(reqs, rows, random_seed=99, use_greedy_assignment=False)
    assert len(out) == 2
    assert {a.task_name for a in out} == {'T'}


def test_tie_break_is_reproducible_with_seed(work_date: date) -> None:
    '''Identical scores ⇒ RNG alone decides; same seed ⇒ same pick.'''
    a = _row('A', work_date)
    b = _row('B', work_date)
    profiles = {'A': _tech('A'), 'B': _tech('B')}
    reqs = [TaskRequest('1', 'Same', 2, work_date, TimeSlot.AM)]
    ctx = AssignmentScoringContext(work_date, TimeSlot.AM, (), None)

    first = assign_greedy(reqs, [a, b], scoring_context=ctx, tech_profiles_by_name=profiles, rng=random.Random(123))
    second = assign_greedy(reqs, [a, b], scoring_context=ctx, tech_profiles_by_name=profiles, rng=random.Random(123))
    assert [x.technician_id for x in first] == [x.technician_id for x in second]


def test_tie_break_can_differ_with_different_seeds(work_date: date) -> None:
    '''Symmetric techs and tasks ⇒ many seeds must eventually pick a different first assignee.'''
    a = _row('A', work_date)
    b = _row('B', work_date)
    profiles = {'A': _tech('A'), 'B': _tech('B')}
    reqs = [
        TaskRequest('1', 'Same', 1, work_date, TimeSlot.AM),
        TaskRequest('2', 'Same', 1, work_date, TimeSlot.AM),
    ]
    ctx = AssignmentScoringContext(work_date, TimeSlot.AM, (), None)
    baseline_opt = GreedyOptimizationConfig(
        lookahead_tie_breaks=False,
        local_search_post_pass=False,
        exact_fallback_max_pool_size=None,
        strict_dislike_avoidance=False,
    )
    first_ids = {
        assign_greedy(
            reqs,
            [a, b],
            scoring_context=ctx,
            tech_profiles_by_name=profiles,
            optimization=baseline_opt,
            rng=random.Random(seed),
        )[
            0
        ].technician_id
        for seed in range(300)
    }
    assert first_ids == {'a', 'b'}


def test_slot_indices_most_constrained_first_orders_by_non_dislikers() -> None:
    '''Hardest slot (fewest techs who do not dislike it) gets index first; ties by slot index.'''
    p0 = tech_scoring_profile_from_entity(_tech('A', dislikes=['hard']))
    p1 = tech_scoring_profile_from_entity(_tech('B'))
    p2 = tech_scoring_profile_from_entity(_tech('C'))
    profiles = (p0, p1, p2)
    task_slots = [
        TaskSlotRef('easy', 'easy'),
        TaskSlotRef('hard', 'hard'),
        TaskSlotRef('med', 'med'),
    ]
    assert _slot_indices_most_constrained_first(task_slots, profiles) == [1, 0, 2]


def test_assign_greedy_one_tech_one_slot(work_date: date) -> None:
    solo = _row('Solo', work_date)
    profiles = {'Solo': _tech('Solo')}
    reqs = [TaskRequest('1', 'OnlyTask', 1, work_date, TimeSlot.AM)]
    ctx = AssignmentScoringContext(work_date, TimeSlot.AM, (), None)
    out = assign_greedy(reqs, [solo], scoring_context=ctx, tech_profiles_by_name=profiles, rng=random.Random(0))
    assert len(out) == 1
    assert out[0].technician_id == 'solo'
    assert out[0].task_name == 'Onlytask'


def test_assign_greedy_when_everyone_dislikes_one_task(work_date: date) -> None:
    '''Still produces a full matching; the hated slot is filled by a least-bad score.'''
    a = _row('A', work_date)
    b = _row('B', work_date)
    profiles = {
        'A': _tech('A', dislikes=['Hated', 'Other']),
        'B': _tech('B', dislikes=['Hated', 'Other']),
    }
    reqs = [
        TaskRequest('1', 'Hated', 1, work_date, TimeSlot.AM),
        TaskRequest('2', 'Other', 1, work_date, TimeSlot.AM),
    ]
    ctx = AssignmentScoringContext(work_date, TimeSlot.AM, (), None)
    out = assign_greedy(reqs, [a, b], scoring_context=ctx, tech_profiles_by_name=profiles, rng=random.Random(0))
    assert len(out) == 2
    assert {a.task_name for a in out} == {'Hated', 'Other'}
    assert {a.technician_id for a in out} == {'a', 'b'}


def test_compatibility_score_no_history_neutral_task_scores_zero(work_date: date) -> None:
    '''Empty confirmed rows: no fairness load, no same-day term; neutral task ⇒ 0 with defaults.'''
    profile = tech_scoring_profile_from_entity(_tech('A', dislikes=['X']))
    ctx = AssignmentScoringContext(work_date, TimeSlot.AM, (), None)
    assert compatibility_score(profile, '1', 'Y', ctx, DEFAULT_SCORING_WEIGHTS) == 0.0


def test_compatibility_score_fairness_disliked_load_only(work_date: date) -> None:
    '''Past confirmed disliked work increases load penalty even for a neutral candidate task.'''
    profile = tech_scoring_profile_from_entity(_tech('A', dislikes=['Z']))
    confirmed = (Assignment('Z', 'a', work_date, TimeSlot.PM),)
    ctx = AssignmentScoringContext(work_date, TimeSlot.AM, confirmed, None)
    w = ScoringWeights(
        favorite_bonus=0.0,
        dislike_base_penalty=0.0,
        disliked_task_repeat_penalty=0.0,
        max_repeat_penalty_multiplier=0,
        fairness_disliked_load_penalty=4.0,
        consistency_bonus=0.0,
        variation_bonus=0.0,
    )
    assert compatibility_score(profile, '1', 'Neutral', ctx, w) == -4.0


def test_lookahead_tie_break_preserves_future_options(work_date: date) -> None:
    '''
    For slot "B", techs B and C tie on score. Lookahead should pick B because
    removing C would leave fewer options for remaining slot "C".
    '''
    rows = [_row('A', work_date), _row('B', work_date), _row('C', work_date)]
    profiles = {
        'A': _tech('A', dislikes=['B']),
        'B': _tech('B', dislikes=['C']),
        'C': _tech('C'),
    }
    reqs = [
        TaskRequest('1', 'A', 1, work_date, TimeSlot.AM),
        TaskRequest('2', 'B', 1, work_date, TimeSlot.AM),
        TaskRequest('3', 'C', 1, work_date, TimeSlot.AM),
    ]
    ctx = AssignmentScoringContext(work_date, TimeSlot.AM, (), None)
    out = assign_greedy(
        reqs,
        rows,
        scoring_context=ctx,
        tech_profiles_by_name=profiles,
        optimization=GreedyOptimizationConfig(
            lookahead_tie_breaks=True,
            local_search_post_pass=False,
            exact_fallback_max_pool_size=None,
            strict_dislike_avoidance=False,
        ),
        rng=random.Random(1),
    )
    by_task = {a.task_name: a.technician_id for a in out}
    assert by_task['B'] == 'b'


def test_local_swap_post_pass_improves_greedy_tie_outcome(work_date: date) -> None:
    rows = [_row('A', work_date), _row('B', work_date)]
    profiles = {
        'A': _tech('A', favorites=['X', 'Y']),
        'B': _tech('B', favorites=['X']),
    }
    reqs = [
        TaskRequest('1', 'X', 1, work_date, TimeSlot.AM),
        TaskRequest('2', 'Y', 1, work_date, TimeSlot.AM),
    ]
    ctx = AssignmentScoringContext(work_date, TimeSlot.AM, (), None)
    out = assign_greedy(
        reqs,
        rows,
        scoring_context=ctx,
        tech_profiles_by_name=profiles,
        optimization=GreedyOptimizationConfig(
            lookahead_tie_breaks=False,
            local_search_post_pass=True,
            exact_fallback_max_pool_size=None,
            strict_dislike_avoidance=False,
        ),
        rng=random.Random(1),
    )
    by_tech = {a.technician_id: a.task_name for a in out}
    assert by_tech == {'a': 'Y', 'b': 'X'}


def test_exact_fallback_solves_small_slice_optimally(work_date: date) -> None:
    rows = [_row('A', work_date), _row('B', work_date)]
    profiles = {
        'A': _tech('A', favorites=['X', 'Y']),
        'B': _tech('B', favorites=['X']),
    }
    reqs = [
        TaskRequest('1', 'X', 1, work_date, TimeSlot.AM),
        TaskRequest('2', 'Y', 1, work_date, TimeSlot.AM),
    ]
    ctx = AssignmentScoringContext(work_date, TimeSlot.AM, (), None)
    out = assign_greedy(
        reqs,
        rows,
        scoring_context=ctx,
        tech_profiles_by_name=profiles,
        optimization=GreedyOptimizationConfig(
            lookahead_tie_breaks=False,
            local_search_post_pass=False,
            exact_fallback_max_pool_size=9,
            strict_dislike_avoidance=False,
        ),
        rng=random.Random(1),
    )
    by_tech = {a.technician_id: a.task_name for a in out}
    assert by_tech == {'a': 'Y', 'b': 'X'}


def test_strict_dislike_mode_avoids_disliked_when_possible(work_date: date) -> None:
    rows = [_row('A', work_date), _row('B', work_date)]
    profiles = {
        'A': _tech('A', dislikes=['Tasky'], preference=DailyPreference.CONSISTENCY),
        'B': _tech('B'),
    }
    reqs = [TaskRequest('1', 'Tasky', 1, work_date, TimeSlot.AM)]
    confirmed = (Assignment('Tasky', 'a', work_date, TimeSlot.PM),)
    ctx = AssignmentScoringContext(work_date, TimeSlot.AM, confirmed, None)
    boosted = ScoringWeights(consistency_bonus=8.0)
    out = assign_greedy(
        reqs,
        rows,
        scoring_context=ctx,
        tech_profiles_by_name=profiles,
        weights=boosted,
        optimization=GreedyOptimizationConfig(
            lookahead_tie_breaks=True,
            local_search_post_pass=False,
            exact_fallback_max_pool_size=None,
            strict_dislike_avoidance=True,
        ),
        rng=random.Random(1),
    )
    assert out[0].technician_id == 'b'


def test_neutral_profile_when_name_missing_from_map(work_date: date) -> None:
    '''No profile row: empty favorites/dislikes; scoring stays neutral for arbitrary tasks.'''
    row = _row('NewHire', work_date)
    prof = tech_scoring_profile_for_schedule_row(row, {'SomeoneElse': _tech('SomeoneElse')})
    assert prof.favorites == frozenset()
    assert prof.dislikes == frozenset()
    ctx = AssignmentScoringContext(work_date, TimeSlot.AM, (), None)
    assert compatibility_score(prof, '1', 'Anything', ctx, DEFAULT_SCORING_WEIGHTS) == 0.0


def test_assign_greedy_raises_when_no_one_eligible(work_date: date) -> None:
    a = _row('A', work_date)
    b = _row('B', work_date)
    profiles = {
        'A': _tech('A', eligible_by_task_id={'1': False}),
        'B': _tech('B', eligible_by_task_id={'1': False}),
    }
    reqs = [
        TaskRequest('1', 'Solo', 1, work_date, TimeSlot.AM),
        TaskRequest('2', 'Other', 1, work_date, TimeSlot.AM),
    ]
    ctx = AssignmentScoringContext(work_date, TimeSlot.AM, (), None)
    with pytest.raises(NoEligibleTechnicianError):
        assign_greedy(
            reqs,
            [a, b],
            scoring_context=ctx,
            tech_profiles_by_name=profiles,
            optimization=GreedyOptimizationConfig(
                lookahead_tie_breaks=False,
                local_search_post_pass=False,
                exact_fallback_max_pool_size=None,
            ),
            rng=random.Random(0),
        )


def test_compatibility_score_proficiency_expert_bonus(work_date: date) -> None:
    profile = tech_scoring_profile_from_entity(
        _tech('A', proficiency_by_task_id={'tid': TaskProficiencyLevel.EXPERT})
    )
    ctx = AssignmentScoringContext(work_date, TimeSlot.AM, (), None)
    w = DEFAULT_SCORING_WEIGHTS
    assert compatibility_score(profile, 'tid', 'Anyname', ctx, w) == 1.0


def test_compatibility_score_ineligible_is_neg_inf(work_date: date) -> None:
    profile = tech_scoring_profile_from_entity(
        _tech('A', eligible_by_task_id={'tid': False}, favorites=['Anyname'])
    )
    ctx = AssignmentScoringContext(work_date, TimeSlot.AM, (), None)
    w = ScoringWeights(favorite_bonus=99.0)
    assert compatibility_score(profile, 'tid', 'Anyname', ctx, w) == float('-inf')
