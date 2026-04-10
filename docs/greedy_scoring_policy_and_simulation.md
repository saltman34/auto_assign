# Greedy Scoring Policy and Simulation Guide

Date: 2026-04-09

## Default Policy (Current)

The app now defaults to the improved greedy policy everywhere assignments are generated:

- local swap post-pass: **ON**
- lookahead tie-breaks: **ON**
- exact fallback for small pools: **ON** (`pool <= 9`)
- strict dislike avoidance: **ON**

Backend source of truth is `GreedyOptimizationConfig` in `src/auto_assign/core/assignment/scoring_types.py`.
The Assignment Engine passes `greedy_optimization=None` so these defaults always apply; operators do not see scoring toggles on Home. Fairness lookback for scoring and history loading is fixed at **14 days** in `src/auto_assign/ui/schedule/workflow.py`.

### Why 14 days for fairness lookback?

- **Recent signal:** Fairness and repeat-dislike terms should reflect *recent* confirmed work, not months-old patterns (roles, preferences, and staffing mix change).
- **Simple story for operators:** “About the last two weeks of **published** assignments” is easy to explain and matches common payroll or scheduling horizons.
- **Enough data for typical use:** For labs that run most weekdays, two weeks usually yields enough per-person history for rotation to bite; if volume is very low per tech, a longer window (e.g. 30 days) is a reasonable product tweak—document any change in `workflow.py` next to `_FAIRNESS_LOOKBACK_DAYS` and in the About page copy.

## Why this is the default

On a fixed paired 10-scenario benchmark (same seeded scenarios for baseline and improved):

- average score delta: **+2.20**
- average optimality delta: **+12.1 points**
- average satisfaction delta: **+6.1**
- total disliked assignments delta: **+0** (no net change)
- average runtime delta: **+0.17 ms**

See the detailed per-scenario table in `docs/greedy_scoring_paired_benchmark_report.md`.

## Run a simulation yourself

Use the repo-level script:

- Paired benchmark (recommended):
  - `python scripts/run_greedy_simulation.py --mode paired`
- Single-policy sanity run:
  - `python scripts/run_greedy_simulation.py --mode sanity`

Optional flags:

- `--scenario-count <N>` (default `10`)
- `--seed <int>` (default `20260409`)
- `--fairness-lookback-days <int>` (default `14`)

Example:

- `python scripts/run_greedy_simulation.py --mode paired --scenario-count 25 --seed 12345`

## Module entry points (for custom tooling)

Simulation logic lives in `src/auto_assign/core/assignment/simulation.py`.

The benchmark CLI lives in `scripts/run_greedy_simulation.py` (not under `tests/`, so it is never collected by pytest).

Assignment implementation is split for clarity:

- `greedy_assigner.py` — orchestration (slot order, per-slot picks, wiring)
- `greedy_exact_match.py` — exact small-pool DP
- `greedy_local_swap.py` — pairwise swap post-pass
- `compatibility_scoring.py` — pure score + shared helpers such as `task_is_disliked`

Key functions:

- `build_random_scenarios(...)`
- `run_policy_on_scenarios(...)`
- `run_paired_benchmark(...)`
- `summarize_metrics(...)`
- `summarize_paired(...)`

This is intended for notebooks, future CI benchmarks, and policy experiments without touching UI code.
