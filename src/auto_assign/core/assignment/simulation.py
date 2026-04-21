'''
Reusable simulation helpers for greedy scoring benchmarks.

This module supports:
- single-policy sanity runs
- paired baseline-vs-improved benchmark runs on fixed scenarios
'''
from __future__ import annotations

import itertools
import random
import time
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta

from auto_assign.domain import Assignment
from auto_assign.domain.entities import Tech
from auto_assign.domain.enums import DailyPreference, TimeSlot
from auto_assign.ingestion import ScheduleRow, TaskRequest

from .assignment_service import assign_tasks
from .compatibility_scoring import compatibility_score
from .scoring_types import (
    AssignmentScoringContext,
    GreedyOptimizationConfig,
    TaskSlotRef,
    TechScoringProfile,
    tech_scoring_profile_from_entity,
)
from .scoring_weights_config import DEFAULT_SCORING_WEIGHTS

DEFAULT_SIM_TASKS: tuple[str, ...] = (
    'Clinicals',
    'Recuts',
    'Scrolls',
    'Embedding',
    'Exhaust Checks',
    'Grossing',
)


@dataclass(frozen=True)
class SimulationScenario:
    scenario_idx: int
    n_techs: int
    work_date: date
    time_slot: TimeSlot
    task_requests: list[TaskRequest]
    available_rows: list[ScheduleRow]
    profiles_by_name: dict[str, Tech]
    confirmed_history: tuple[Assignment, ...]


@dataclass(frozen=True)
class ScenarioMetrics:
    score_total: float
    optimal_score: float
    worst_score: float
    optimality_pct: float
    fav: int
    neutral: int
    disliked: int
    satisfaction: float
    runtime_ms: float


@dataclass(frozen=True)
class PairedScenarioResult:
    scenario: SimulationScenario
    baseline: ScenarioMetrics
    improved: ScenarioMetrics


def build_random_scenarios(
    *,
    scenario_count: int = 10,
    seed: int = 20260409,
    task_names: tuple[str, ...] = DEFAULT_SIM_TASKS,
) -> list[SimulationScenario]:
    scenarios: list[SimulationScenario] = []
    for idx in range(1, scenario_count + 1):
        rng = random.Random(seed + idx * 1009)
        work_date = date(2026, 4, 1) + timedelta(days=idx - 1)
        time_slot = TimeSlot.AM
        n_techs = rng.randint(4, 7)
        techs = [_build_random_tech(f'Tech{idx}_{i + 1}', rng, task_names) for i in range(n_techs)]
        scenarios.append(
            SimulationScenario(
                scenario_idx=idx,
                n_techs=n_techs,
                work_date=work_date,
                time_slot=time_slot,
                task_requests=_build_task_requests(
                    [rng.choice(task_names) for _ in range(n_techs)],
                    work_date,
                    time_slot,
                ),
                available_rows=[ScheduleRow(t.tech_name, work_date, True, True, True) for t in techs],
                profiles_by_name={t.tech_name: t for t in techs},
                confirmed_history=_build_confirmed_history(
                    techs=techs,
                    work_date=work_date,
                    time_slot=time_slot,
                    rng=rng,
                    task_names=task_names,
                ),
            )
        )
    return scenarios


def run_policy_on_scenarios(
    scenarios: list[SimulationScenario],
    *,
    optimization: GreedyOptimizationConfig,
    seed: int = 20260409,
    fairness_lookback_days: int | None = 14,
) -> list[ScenarioMetrics]:
    return [
        _evaluate_policy(
            s,
            optimization=optimization,
            seed=seed,
            fairness_lookback_days=fairness_lookback_days,
        )
        for s in scenarios
    ]


def run_paired_benchmark(
    scenarios: list[SimulationScenario],
    *,
    baseline: GreedyOptimizationConfig,
    improved: GreedyOptimizationConfig,
    seed: int = 20260409,
    fairness_lookback_days: int | None = 14,
) -> list[PairedScenarioResult]:
    rows: list[PairedScenarioResult] = []
    for s in scenarios:
        base_m = _evaluate_policy(
            s,
            optimization=baseline,
            seed=seed,
            fairness_lookback_days=fairness_lookback_days,
        )
        imp_m = _evaluate_policy(
            s,
            optimization=improved,
            seed=seed,
            fairness_lookback_days=fairness_lookback_days,
        )
        rows.append(PairedScenarioResult(scenario=s, baseline=base_m, improved=imp_m))
    return rows


def summarize_metrics(metrics: list[ScenarioMetrics]) -> dict[str, float]:
    n = len(metrics)
    if n == 0:
        return {
            'avg_score': 0.0,
            'avg_optimality_pct': 0.0,
            'avg_satisfaction': 0.0,
            'avg_runtime_ms': 0.0,
            'exact_optimal_runs': 0.0,
            'runs_with_disliked': 0.0,
        }
    return {
        'avg_score': sum(m.score_total for m in metrics) / n,
        'avg_optimality_pct': sum(m.optimality_pct for m in metrics) / n,
        'avg_satisfaction': sum(m.satisfaction for m in metrics) / n,
        'avg_runtime_ms': sum(m.runtime_ms for m in metrics) / n,
        'exact_optimal_runs': float(
            sum(1 for m in metrics if abs(m.score_total - m.optimal_score) < 1e-9)
        ),
        'runs_with_disliked': float(sum(1 for m in metrics if m.disliked > 0)),
    }


def summarize_paired(results: list[PairedScenarioResult]) -> dict[str, float]:
    n = len(results)
    if n == 0:
        return {
            'delta_avg_score': 0.0,
            'delta_avg_optimality_pct': 0.0,
            'delta_avg_satisfaction': 0.0,
            'delta_avg_runtime_ms': 0.0,
            'delta_total_disliked': 0.0,
            'improved_score_runs': 0.0,
            'improved_optimality_runs': 0.0,
            'improved_satisfaction_runs': 0.0,
        }
    return {
        'delta_avg_score': sum(r.improved.score_total - r.baseline.score_total for r in results) / n,
        'delta_avg_optimality_pct': sum(
            r.improved.optimality_pct - r.baseline.optimality_pct for r in results
        )
        / n,
        'delta_avg_satisfaction': sum(r.improved.satisfaction - r.baseline.satisfaction for r in results)
        / n,
        'delta_avg_runtime_ms': sum(r.improved.runtime_ms - r.baseline.runtime_ms for r in results) / n,
        'delta_total_disliked': float(
            sum(r.improved.disliked - r.baseline.disliked for r in results)
        ),
        'improved_score_runs': float(
            sum(1 for r in results if r.improved.score_total > r.baseline.score_total)
        ),
        'improved_optimality_runs': float(
            sum(1 for r in results if r.improved.optimality_pct > r.baseline.optimality_pct)
        ),
        'improved_satisfaction_runs': float(
            sum(1 for r in results if r.improved.satisfaction > r.baseline.satisfaction)
        ),
    }


def _build_task_requests(slot_tasks: list[str], work_date: date, slot: TimeSlot) -> list[TaskRequest]:
    counts = Counter(slot_tasks)
    ordered_unique: list[str] = []
    for task_name in slot_tasks:
        if task_name not in ordered_unique:
            ordered_unique.append(task_name)
    return [
        TaskRequest(
            task_id=str(i + 1),
            task_name=task_name,
            task_count=counts[task_name],
            task_date=work_date,
            time_slot=slot,
        )
        for i, task_name in enumerate(ordered_unique)
    ]


def _build_random_tech(name: str, rng: random.Random, task_names: tuple[str, ...]) -> Tech:
    pref = rng.choice([DailyPreference.CONSISTENCY, DailyPreference.VARIATION])
    fav_n = rng.randint(1, 3)
    favorites = rng.sample(list(task_names), k=fav_n)
    remaining = [t for t in task_names if t not in favorites]
    dis_n = min(rng.randint(0, 2), len(remaining))
    dislikes = rng.sample(remaining, k=dis_n) if dis_n > 0 else []
    return Tech(
        tech_id=name.lower(),
        tech_name=name,
        daily_preference=pref,
        favorites=favorites,
        dislikes=dislikes,
    )


def _build_confirmed_history(
    *,
    techs: list[Tech],
    work_date: date,
    time_slot: TimeSlot,
    rng: random.Random,
    task_names: tuple[str, ...],
) -> tuple[Assignment, ...]:
    rows: list[Assignment] = []
    other_slot = TimeSlot.PM if time_slot != TimeSlot.PM else TimeSlot.AM
    for tech in techs:
        rows.append(
            Assignment(
                task_name=rng.choice(task_names),
                technician_id=tech.tech_id,
                date_assigned=work_date,
                time_slot=other_slot,
            )
        )
        for _ in range(rng.randint(0, 2)):
            rows.append(
                Assignment(
                    task_name=rng.choice(task_names),
                    technician_id=tech.tech_id,
                    date_assigned=work_date - timedelta(days=rng.randint(1, 14)),
                    time_slot=rng.choice([TimeSlot.AM, TimeSlot.MID, TimeSlot.PM]),
                )
            )
    return tuple(rows)


def _expand_task_slots(task_requests: list[TaskRequest]) -> list[TaskSlotRef]:
    slots: list[TaskSlotRef] = []
    for tr in task_requests:
        for _ in range(tr.task_count):
            slots.append(TaskSlotRef(catalog_task_id=tr.task_id, task_name=tr.task_name))
    return slots


def _tech_profiles_by_id(profiles_by_name: dict[str, Tech]) -> dict[str, TechScoringProfile]:
    return {tech.tech_id: tech_scoring_profile_from_entity(tech) for tech in profiles_by_name.values()}


def _score_total_for_permutation(
    *,
    task_slots: list[TaskSlotRef],
    tech_order: list[Tech],
    ctx: AssignmentScoringContext,
) -> float:
    total = 0.0
    for slot, tech in zip(task_slots, tech_order, strict=True):
        total += compatibility_score(
            tech_scoring_profile_from_entity(tech),
            slot.catalog_task_id,
            slot.task_name,
            ctx,
            DEFAULT_SCORING_WEIGHTS,
        )
    return total


def _optimal_and_worst(
    *,
    task_requests: list[TaskRequest],
    techs: list[Tech],
    ctx: AssignmentScoringContext,
) -> tuple[float, float]:
    slots = _expand_task_slots(task_requests)
    best = float('-inf')
    worst = float('inf')
    for perm in itertools.permutations(techs):
        score = _score_total_for_permutation(task_slots=slots, tech_order=list(perm), ctx=ctx)
        if score > best:
            best = score
        if score < worst:
            worst = score
    return best, worst


def _evaluate_policy(
    scenario: SimulationScenario,
    *,
    optimization: GreedyOptimizationConfig,
    seed: int,
    fairness_lookback_days: int | None,
) -> ScenarioMetrics:
    t0 = time.perf_counter()
    assignments = assign_tasks(
        scenario.task_requests,
        scenario.available_rows,
        random_seed=seed + scenario.scenario_idx,
        use_greedy_assignment=True,
        tech_profiles_by_name=scenario.profiles_by_name,
        confirmed_assignments=scenario.confirmed_history,
        greedy_optimization=optimization,
        fairness_lookback_days=fairness_lookback_days,
    )
    runtime_ms = (time.perf_counter() - t0) * 1000.0

    ctx = AssignmentScoringContext(
        work_date=scenario.work_date,
        time_slot=scenario.time_slot,
        confirmed_assignments=scenario.confirmed_history,
        lookback_days=fairness_lookback_days,
    )
    optimal, worst = _optimal_and_worst(
        task_requests=scenario.task_requests,
        techs=list(scenario.profiles_by_name.values()),
        ctx=ctx,
    )

    profiles_by_id = _tech_profiles_by_id(scenario.profiles_by_name)
    score_total = 0.0
    fav = 0
    neutral = 0
    disliked = 0
    for assignment in assignments:
        p = profiles_by_id[assignment.technician_id]
        score_total += compatibility_score(
            p,
            assignment.effective_catalog_task_id(),
            assignment.task_name,
            ctx,
            DEFAULT_SCORING_WEIGHTS,
        )
        if assignment.task_name in p.favorites:
            fav += 1
        elif assignment.task_name in p.dislikes:
            disliked += 1
        else:
            neutral += 1

    optimality_pct = 100.0 if optimal == worst else ((score_total - worst) / (optimal - worst)) * 100.0
    satisfaction = ((fav * 1.0 + neutral * 0.6 + disliked * 0.1) / scenario.n_techs) * 100.0
    return ScenarioMetrics(
        score_total=score_total,
        optimal_score=optimal,
        worst_score=worst,
        optimality_pct=optimality_pct,
        fav=fav,
        neutral=neutral,
        disliked=disliked,
        satisfaction=satisfaction,
        runtime_ms=runtime_ms,
    )
