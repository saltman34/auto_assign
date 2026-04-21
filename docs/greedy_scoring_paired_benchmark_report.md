# Greedy Scoring Paired Benchmark Report

Frozen snapshot of one `python scripts/run_greedy_simulation.py --mode paired` run (baseline vs improved on the same seeded scenarios). Regenerate this file when scoring weights, optimization flags, or scenario generation change, or the numbers will drift.

Date: 2026-04-09

## Scope

This report compares baseline and improved assignment policies on the **same fixed 10 scenarios**.

- Scenario seed: `20260409`
- Scenario count: `10`
- Pool sizes: `4-7` technicians
- Task set: Clinicals, Recuts, Scrolls, Embedding, Exhaust Checks, Grossing
- Scoring weights: `DEFAULT_SCORING_WEIGHTS`
- Fairness lookback: `14` days

### Policy Definitions

- **Baseline policy**
  - local swap post-pass: OFF
  - lookahead tie-breaks: OFF
  - exact fallback: OFF
  - strict dislike avoidance: OFF

- **Improved policy**
  - local swap post-pass: ON
  - lookahead tie-breaks: ON
  - exact fallback: ON (`pool <= 9`)
  - strict dislike avoidance: ON

## Per-Scenario Paired Results

| Scenario | N | Base Score | New Score | Delta Score | Base Opt% | New Opt% | Delta Opt% | Base Sat | New Sat | Delta Sat | Base Disliked | New Disliked | Delta Disliked | Base ms | New ms | Delta ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 4 | 13.0 | 15.0 | +2.0 | 80.0 | 100.0 | +20.0 | 70.0 | 80.0 | +10.0 | 0 | 0 | +0 | 0.76 | 0.24 | -0.52 |
| 2 | 6 | 7.0 | 14.0 | +7.0 | 79.4 | 100.0 | +20.6 | 73.3 | 86.7 | +13.3 | 0 | 0 | +0 | 0.35 | 0.58 | +0.23 |
| 3 | 6 | 19.0 | 19.0 | +0.0 | 100.0 | 100.0 | +0.0 | 86.7 | 86.7 | +0.0 | 0 | 0 | +0 | 0.33 | 0.50 | +0.17 |
| 4 | 6 | -2.0 | 0.0 | +2.0 | 87.5 | 100.0 | +12.5 | 51.7 | 58.3 | +6.7 | 1 | 1 | +0 | 0.26 | 0.53 | +0.27 |
| 5 | 7 | 18.0 | 20.0 | +2.0 | 88.2 | 100.0 | +11.8 | 88.6 | 94.3 | +5.7 | 0 | 0 | +0 | 0.22 | 0.80 | +0.58 |
| 6 | 7 | 27.0 | 29.0 | +2.0 | 93.8 | 100.0 | +6.2 | 88.6 | 94.3 | +5.7 | 0 | 0 | +0 | 0.22 | 0.83 | +0.60 |
| 7 | 4 | 6.0 | 11.0 | +5.0 | 72.2 | 100.0 | +27.8 | 70.0 | 80.0 | +10.0 | 0 | 0 | +0 | 0.16 | 0.24 | +0.07 |
| 8 | 5 | 15.0 | 15.0 | +0.0 | 100.0 | 100.0 | +0.0 | 84.0 | 84.0 | +0.0 | 0 | 0 | +0 | 0.17 | 0.37 | +0.20 |
| 9 | 4 | 15.0 | 15.0 | +0.0 | 100.0 | 100.0 | +0.0 | 80.0 | 80.0 | +0.0 | 0 | 0 | +0 | 0.13 | 0.14 | +0.01 |
| 10 | 4 | 8.0 | 10.0 | +2.0 | 77.8 | 100.0 | +22.2 | 80.0 | 90.0 | +10.0 | 0 | 0 | +0 | 0.08 | 0.20 | +0.12 |

## Aggregate Findings

- Average score delta: `+2.20`
- Average optimality delta: `+12.1 pts`
- Average satisfaction delta: `+6.1`
- Total disliked assignment delta: `+0` (no net change; one scenario remained disliked in both policies)
- Average runtime delta: `+0.17 ms`
- Scenarios with improved score: `7 / 10`
- Scenarios with improved optimality: `7 / 10`
- Scenarios with improved satisfaction: `7 / 10`

## Assessment

### Core outcome

On fixed paired scenarios, the improved policy is better on quality metrics:

- It reaches perfect average normalized optimality.
- It increases average satisfaction by a meaningful margin.
- It improves score/optimality/satisfaction in most scenarios.

### Why only 5/10 scenarios improved

Three scenarios were already baseline-optimal and unchanged.
In those cases, the improved policy mostly adds overhead without quality change.

### Runtime impact

The improved policy is slower in relative terms but still extremely fast in absolute terms:

- +0.17 ms average per scenario
- all measured runtimes remained sub-1 ms

Given this scale, the quality gains dominate the cost for the tested pool sizes.

## Recommendation

Adopt the improved policy as the default for small/medium slices similar to this benchmark.

For larger pools, keep monitoring runtime and consider:

- retaining exact fallback threshold tuning (`<= 9` currently),
- collecting paired benchmarks at larger N (for example 10-20 technicians),
- tracking p95/p99 runtime in addition to average.
