'''Demo dataset definitions: task catalog, 18 technician archetypes, schedule generator.

These fixtures intentionally describe a small, readable histology-style workflow
(Clinicals, Recuts, Scrolls, Embedding, Grossing, Exhaust Checks) so a hiring
manager can see the algorithm do something meaningful in one screenful.

Technicians are grouped into four archetypes so every scoring term has something
to express:

- **Specialists** (6 techs across 4 disciplines): EXPERT proficiency on their
  discipline, STRONG on one or two neighbors, INDEPENDENT elsewhere. Favorites
  aligned with their discipline. Drive "favorite match" and "high proficiency"
  scoring.
- **Generalists** (9 techs): INDEPENDENT nearly everywhere with two STRONG tasks
  each. A few carry dislikes. Show the scorer picking "the most reasonable
  person on the bench" when specialists are unavailable.
- **Trainees** (3 techs): NOVICE everywhere with one ineligibility each so the
  pool filter and manual-override flow both have something to demo.

The task catalog keeps default headcounts small (0–2 per task per slot). Two
tasks (Recuts, Exhaust Checks) ship at ``default_count=0`` to model "on-demand"
work — operators add headcount deliberately from Step 5 when the day calls for
it. Sum of defaults ≈ 6 against a typical pool of 10–12 leaves several slots of
headroom for count-allocation exploration.
'''
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta

from auto_assign.domain.enums import (
    DailyPreference,
    Staffing_Status,
    TaskProficiencyLevel,
)
from auto_assign.ingestion.csv_schema import ScheduleRow

# ---------------------------------------------------------------------------
# Task catalog
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DemoTaskSpec:
    '''One task catalog row in the demo dataset.'''

    task_id: str
    task_name: str
    default_count: int


DEMO_TASKS: tuple[DemoTaskSpec, ...] = (
    DemoTaskSpec(task_id='T-CLIN', task_name='Clinicals', default_count=2),
    DemoTaskSpec(task_id='T-RECUT', task_name='Recuts', default_count=0),
    DemoTaskSpec(task_id='T-SCROLL', task_name='Scrolls', default_count=1),
    DemoTaskSpec(task_id='T-EMBED', task_name='Embedding', default_count=2),
    DemoTaskSpec(task_id='T-GROSS', task_name='Grossing', default_count=1),
    DemoTaskSpec(task_id='T-EXHAUST', task_name='Exhaust Checks', default_count=0),
)


def _task_name_by_id() -> dict[str, str]:
    return {t.task_id: t.task_name for t in DEMO_TASKS}


# ---------------------------------------------------------------------------
# Technician archetypes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DemoTechSpec:
    '''One technician row in the demo dataset.

    Proficiency and eligibility are keyed by **catalog task_id** (not name) to
    mirror the production schema. Favorites and dislikes use task **names** to
    match the CSV contract.
    '''

    tech_id: str
    tech_name: str
    daily_preference: DailyPreference
    archetype: str
    favorites: tuple[str, ...] = ()
    dislikes: tuple[str, ...] = ()
    eligible_by_task_id: dict[str, bool] = field(default_factory=dict)
    proficiency_by_task_id: dict[str, TaskProficiencyLevel] = field(default_factory=dict)


_IND = TaskProficiencyLevel.INDEPENDENT
_NOV = TaskProficiencyLevel.NOVICE
_STR = TaskProficiencyLevel.STRONG
_EXP = TaskProficiencyLevel.EXPERT


def _prof(**overrides: TaskProficiencyLevel) -> dict[str, TaskProficiencyLevel]:
    '''Build a proficiency map defaulting to INDEPENDENT for every catalog task.'''
    base: dict[str, TaskProficiencyLevel] = {t.task_id: _IND for t in DEMO_TASKS}
    base.update(overrides)
    return base


def _novice_all() -> dict[str, TaskProficiencyLevel]:
    return {t.task_id: _NOV for t in DEMO_TASKS}


DEMO_TECHS: tuple[DemoTechSpec, ...] = (
    # Clinicals specialists
    DemoTechSpec(
        tech_id='t-01',
        tech_name='Alice Morgan',
        daily_preference=DailyPreference.CONSISTENCY,
        archetype='specialist:clinicals',
        favorites=('Clinicals', 'Recuts'),
        dislikes=('Exhaust Checks',),
        proficiency_by_task_id=_prof(**{'T-CLIN': _EXP, 'T-RECUT': _STR}),
    ),
    DemoTechSpec(
        tech_id='t-02',
        tech_name='Ben Rivera',
        daily_preference=DailyPreference.CONSISTENCY,
        archetype='specialist:clinicals',
        favorites=('Clinicals',),
        dislikes=('Grossing',),
        proficiency_by_task_id=_prof(**{'T-CLIN': _EXP, 'T-SCROLL': _STR}),
    ),
    # Grossing specialists
    DemoTechSpec(
        tech_id='t-03',
        tech_name='Carla Okafor',
        daily_preference=DailyPreference.CONSISTENCY,
        archetype='specialist:grossing',
        favorites=('Grossing',),
        dislikes=('Recuts',),
        proficiency_by_task_id=_prof(**{'T-GROSS': _EXP, 'T-EMBED': _STR}),
    ),
    DemoTechSpec(
        tech_id='t-04',
        tech_name='Dmitri Petrov',
        daily_preference=DailyPreference.VARIATION,
        archetype='specialist:grossing',
        favorites=('Grossing', 'Embedding'),
        proficiency_by_task_id=_prof(**{'T-GROSS': _EXP, 'T-EXHAUST': _STR}),
    ),
    # Generalists
    DemoTechSpec(
        tech_id='t-05',
        tech_name='Elena Harper',
        daily_preference=DailyPreference.VARIATION,
        archetype='generalist',
        favorites=('Scrolls',),
        dislikes=('Exhaust Checks',),
        proficiency_by_task_id=_prof(**{'T-SCROLL': _STR, 'T-EMBED': _STR}),
    ),
    DemoTechSpec(
        tech_id='t-06',
        tech_name='Farouk Ali',
        daily_preference=DailyPreference.VARIATION,
        archetype='generalist',
        favorites=('Embedding',),
        dislikes=('Recuts',),
        proficiency_by_task_id=_prof(**{'T-EMBED': _STR, 'T-EXHAUST': _STR}),
    ),
    DemoTechSpec(
        tech_id='t-07',
        tech_name='Grace Liu',
        daily_preference=DailyPreference.CONSISTENCY,
        archetype='generalist',
        favorites=('Recuts',),
        proficiency_by_task_id=_prof(**{'T-RECUT': _STR, 'T-CLIN': _STR}),
    ),
    DemoTechSpec(
        tech_id='t-08',
        tech_name='Hiro Nakamura',
        daily_preference=DailyPreference.VARIATION,
        archetype='generalist',
        favorites=('Exhaust Checks',),
        proficiency_by_task_id=_prof(**{'T-EXHAUST': _STR, 'T-GROSS': _STR}),
    ),
    DemoTechSpec(
        tech_id='t-09',
        tech_name='Ines Delacroix',
        daily_preference=DailyPreference.CONSISTENCY,
        archetype='generalist',
        favorites=('Scrolls',),
        proficiency_by_task_id=_prof(**{'T-SCROLL': _STR, 'T-CLIN': _STR}),
    ),
    DemoTechSpec(
        tech_id='t-10',
        tech_name='Jamal Owens',
        daily_preference=DailyPreference.VARIATION,
        archetype='generalist',
        favorites=('Embedding',),
        proficiency_by_task_id=_prof(**{'T-EMBED': _STR, 'T-RECUT': _STR}),
    ),
    # Trainees — eligible-by-default on most things, one hard ineligibility each
    DemoTechSpec(
        tech_id='t-11',
        tech_name='Kim Park',
        daily_preference=DailyPreference.CONSISTENCY,
        archetype='trainee',
        eligible_by_task_id={'T-EXHAUST': False},
        proficiency_by_task_id=_novice_all(),
    ),
    DemoTechSpec(
        tech_id='t-12',
        tech_name='Luca Bianchi',
        daily_preference=DailyPreference.VARIATION,
        archetype='trainee',
        eligible_by_task_id={'T-GROSS': False},
        proficiency_by_task_id=_novice_all(),
    ),
    # Embedding specialist — covers a discipline that currently had no "expert".
    DemoTechSpec(
        tech_id='t-13',
        tech_name='Maria Soto',
        daily_preference=DailyPreference.CONSISTENCY,
        archetype='specialist:embedding',
        favorites=('Embedding', 'Grossing'),
        proficiency_by_task_id=_prof(**{'T-EMBED': _EXP, 'T-GROSS': _STR}),
    ),
    # Recuts specialist — strong on Scrolls as a natural neighbor.
    DemoTechSpec(
        tech_id='t-14',
        tech_name='Nikhil Desai',
        daily_preference=DailyPreference.VARIATION,
        archetype='specialist:recuts',
        favorites=('Recuts', 'Scrolls'),
        dislikes=('Grossing',),
        proficiency_by_task_id=_prof(**{'T-RECUT': _EXP, 'T-SCROLL': _STR}),
    ),
    # More generalists to fill out the pool.
    DemoTechSpec(
        tech_id='t-15',
        tech_name='Olivia Chen',
        daily_preference=DailyPreference.CONSISTENCY,
        archetype='generalist',
        favorites=('Clinicals',),
        dislikes=('Grossing',),
        proficiency_by_task_id=_prof(**{'T-CLIN': _STR, 'T-EMBED': _STR}),
    ),
    DemoTechSpec(
        tech_id='t-16',
        tech_name='Priya Joshi',
        daily_preference=DailyPreference.VARIATION,
        archetype='generalist',
        favorites=('Grossing', 'Exhaust Checks'),
        proficiency_by_task_id=_prof(**{'T-GROSS': _STR, 'T-EXHAUST': _STR}),
    ),
    DemoTechSpec(
        tech_id='t-17',
        tech_name='Quinn Walker',
        daily_preference=DailyPreference.CONSISTENCY,
        archetype='generalist',
        favorites=('Scrolls',),
        proficiency_by_task_id=_prof(**{'T-SCROLL': _STR, 'T-RECUT': _STR}),
    ),
    # Trainee — third ineligibility variation to broaden the manual-override demo.
    DemoTechSpec(
        tech_id='t-18',
        tech_name='Riya Shah',
        daily_preference=DailyPreference.CONSISTENCY,
        archetype='trainee',
        eligible_by_task_id={'T-CLIN': False},
        proficiency_by_task_id=_novice_all(),
    ),
)


# ---------------------------------------------------------------------------
# Schedule generator
# ---------------------------------------------------------------------------


def build_demo_schedule_rows(
    *,
    start_date: date,
    num_days: int = 21,
    seed: int = 20260617,
) -> list[ScheduleRow]:
    '''Generate ``num_days`` consecutive days of availability for all demo techs.

    Determinism: given the same ``start_date``, ``num_days``, and ``seed`` you
    get the same rows. That keeps "Reset demo data" predictable and lets tests
    pin an exact expected shape.

    Distribution (per tech per day):

    - ~5% chance of ``call_off`` (entire day unavailable).
    - ~3% chance of ``overtime`` on an otherwise-scheduled day.
    - AM / MID / PM flags each independently True with ~65% probability, with
      a floor that guarantees at least one slot is available on scheduled days
      (otherwise the tech would be a no-op row).
    '''
    if num_days <= 0:
        raise ValueError('num_days must be positive')
    rng = random.Random(seed)
    rows: list[ScheduleRow] = []
    for offset in range(num_days):
        day = start_date + timedelta(days=offset)
        for tech in DEMO_TECHS:
            roll = rng.random()
            if roll < 0.05:
                status = Staffing_Status.CALL_OFF
            elif roll < 0.08:
                status = Staffing_Status.OVERTIME
            else:
                status = Staffing_Status.SCHEDULED

            if status is Staffing_Status.CALL_OFF:
                rows.append(
                    ScheduleRow(
                        tech_name=tech.tech_name,
                        work_date=day,
                        available_AM=False,
                        available_MID=False,
                        available_PM=False,
                        staffing_status=status,
                    )
                )
                continue

            am = rng.random() < 0.65
            mid = rng.random() < 0.65
            pm = rng.random() < 0.65
            if not (am or mid or pm):
                # Guarantee at least one slot on scheduled/overtime days.
                pick = rng.choice(['am', 'mid', 'pm'])
                am = pick == 'am'
                mid = pick == 'mid'
                pm = pick == 'pm'

            rows.append(
                ScheduleRow(
                    tech_name=tech.tech_name,
                    work_date=day,
                    available_AM=am,
                    available_MID=mid,
                    available_PM=pm,
                    staffing_status=status,
                )
            )
    return rows


def task_name_for_id(task_id: str) -> str:
    '''Convenience helper — raises ``KeyError`` if ``task_id`` is not in the demo catalog.'''
    return _task_name_by_id()[task_id]
