#!/usr/bin/env python3
'''
CLI for greedy scoring benchmarks. Run from repo root:

    python scripts/run_greedy_simulation.py --mode paired

No PYTHONPATH needed: this prepends ``<repo>/src`` for imports.
'''
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / 'src'
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from auto_assign.core.assignment import (  # noqa: E402
    GreedyOptimizationConfig,
    build_random_scenarios,
    run_paired_benchmark,
    run_policy_on_scenarios,
    summarize_metrics,
    summarize_paired,
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Run greedy scoring simulation benchmarks.')
    p.add_argument(
        '--mode',
        choices=('sanity', 'paired'),
        default='paired',
        help='sanity = one policy on generated scenarios; paired = baseline vs improved on same scenarios',
    )
    p.add_argument('--scenario-count', type=int, default=10, help='Number of random scenarios to generate.')
    p.add_argument('--seed', type=int, default=20260409, help='Random seed for reproducible scenarios.')
    p.add_argument(
        '--fairness-lookback-days',
        type=int,
        default=14,
        help='Lookback window used by scoring fairness terms.',
    )
    return p.parse_args()


def _print_sanity(args: argparse.Namespace) -> None:
    scenarios = build_random_scenarios(scenario_count=args.scenario_count, seed=args.seed)
    metrics = run_policy_on_scenarios(
        scenarios,
        optimization=GreedyOptimizationConfig(),
        seed=args.seed,
        fairness_lookback_days=args.fairness_lookback_days,
    )
    summary = summarize_metrics(metrics)

    print('# Greedy Scoring Sanity Run')
    print()
    print(f'- Scenarios: {args.scenario_count}')
    print(f'- Seed: {args.seed}')
    print(f'- Policy: improved defaults (`{GreedyOptimizationConfig()}`)')
    print()
    print('| Scenario | N | Score | Optimal | Worst | Optimality % | Fav | Neutral | Disliked | Satisfaction | Runtime (ms) |')
    print('|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|')
    for s, m in zip(scenarios, metrics, strict=True):
        print(
            f'| {s.scenario_idx} | {s.n_techs} | {m.score_total:.1f} | {m.optimal_score:.1f} | '
            f'{m.worst_score:.1f} | {m.optimality_pct:.1f} | {m.fav} | {m.neutral} | '
            f'{m.disliked} | {m.satisfaction:.1f} | {m.runtime_ms:.2f} |'
        )
    print()
    print('## Aggregate')
    print()
    print(f"- Average score: **{summary['avg_score']:.2f}**")
    print(f"- Average optimality: **{summary['avg_optimality_pct']:.1f}%**")
    print(f"- Average satisfaction: **{summary['avg_satisfaction']:.1f} / 100**")
    print(f"- Exact-optimal runs: **{int(summary['exact_optimal_runs'])} / {args.scenario_count}**")
    print(f"- Runs with disliked assignments: **{int(summary['runs_with_disliked'])} / {args.scenario_count}**")
    print(f"- Average runtime: **{summary['avg_runtime_ms']:.2f} ms**")


def _print_paired(args: argparse.Namespace) -> None:
    scenarios = build_random_scenarios(scenario_count=args.scenario_count, seed=args.seed)
    baseline_cfg = GreedyOptimizationConfig(
        local_search_post_pass=False,
        lookahead_tie_breaks=False,
        exact_fallback_max_pool_size=None,
        strict_dislike_avoidance=False,
    )
    improved_cfg = GreedyOptimizationConfig()
    rows = run_paired_benchmark(
        scenarios,
        baseline=baseline_cfg,
        improved=improved_cfg,
        seed=args.seed,
        fairness_lookback_days=args.fairness_lookback_days,
    )
    deltas = summarize_paired(rows)

    print('# Greedy Scoring Paired Benchmark')
    print()
    print(f'- Scenarios: {args.scenario_count}')
    print(f'- Seed: {args.seed}')
    print(f'- Baseline: `{baseline_cfg}`')
    print(f'- Improved: `{improved_cfg}`')
    print()
    print(
        '| Scenario | N | Base Score | New Score | Delta Score | Base Opt% | New Opt% | Delta Opt% | '
        'Base Sat | New Sat | Delta Sat | Base Disliked | New Disliked | Delta Disliked | '
        'Base ms | New ms | Delta ms |'
    )
    print(
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|'
    )
    for r in rows:
        s = r.scenario
        b = r.baseline
        n = r.improved
        print(
            f'| {s.scenario_idx} | {s.n_techs} | {b.score_total:.1f} | {n.score_total:.1f} | {n.score_total - b.score_total:+.1f} | '
            f'{b.optimality_pct:.1f} | {n.optimality_pct:.1f} | {n.optimality_pct - b.optimality_pct:+.1f} | '
            f'{b.satisfaction:.1f} | {n.satisfaction:.1f} | {n.satisfaction - b.satisfaction:+.1f} | '
            f'{b.disliked} | {n.disliked} | {n.disliked - b.disliked:+d} | '
            f'{b.runtime_ms:.2f} | {n.runtime_ms:.2f} | {n.runtime_ms - b.runtime_ms:+.2f} |'
        )
    print()
    print('## Aggregate Deltas')
    print()
    print(f"- Average score delta: **{deltas['delta_avg_score']:+.2f}**")
    print(f"- Average optimality delta: **{deltas['delta_avg_optimality_pct']:+.1f} pts**")
    print(f"- Average satisfaction delta: **{deltas['delta_avg_satisfaction']:+.1f}**")
    print(f"- Total disliked delta: **{int(deltas['delta_total_disliked']):+d}**")
    print(f"- Average runtime delta: **{deltas['delta_avg_runtime_ms']:+.2f} ms**")
    print(
        f"- Improved scenarios (score/optimality/satisfaction): "
        f"**{int(deltas['improved_score_runs'])}/{args.scenario_count}**, "
        f"**{int(deltas['improved_optimality_runs'])}/{args.scenario_count}**, "
        f"**{int(deltas['improved_satisfaction_runs'])}/{args.scenario_count}**"
    )


def main() -> None:
    args = _parse_args()
    if args.mode == 'sanity':
        _print_sanity(args)
    else:
        _print_paired(args)


if __name__ == '__main__':
    main()
