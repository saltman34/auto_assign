# Greedy assignment algorithm — construction, exact fallback, and local search

How the app decides which technician gets each task slot on a given shift. A weighted compatibility score — combining favorites, dislikes, rolling fairness, per-task proficiency, and same-day consistency — drives a greedy placement loop, with an exact solve for small pools and a pairwise swap pass for final polish.

---

## 1. Inputs (brief)

The scorer uses two logical stores:

- **Technicians** — stable profile: `tech_id`, display name, daily preference (consistency / variation), favorite/disliked task names, per-catalog-task **eligibility** (hard gate) and **proficiency** (ordinal bonus). Rubric: [`proficiency_rubric.md`](proficiency_rubric.md).
- **Confirmed assignments** — past `(tech_id, task, work_date, time_slot)` rows used for same-day consistency/variation, recency on dislikes, and global fairness.

Every run targets **exactly one** `(work_date, time_slot)` slice; generate writes **draft** rows, publish promotes them to **confirmed**. The draft/confirmed model is owned by [`persistence_database.md`](persistence_database.md) §0.

---

## 2. Assignment pipeline

### 2.1 Slot ordering — most constrained first

Process **task slots** in an order that handles scarcity first: count technicians who are **eligible** for the slot’s catalog `task_id` **and** do not dislike the slot’s task **name** (fewest such people = hardest). For each slot in that order, pick the **best remaining** technician (highest score among those not yet assigned in this run).

This reduces wasting strong matches on easy slots while leaving impossible-looking slots for last.

### 2.2 Compatibility score (conceptual)

Use a **weighted sum** (tune via config/constants). Each open slot carries a **catalog `task_id`** (from `TaskRequest`) and a normalized **display name** for favorites/dislikes.

- **Eligibility (hard gate):** if a technician is explicitly **ineligible** for this slot’s catalog `task_id`, they are **omitted** from that slot’s candidate list. If nobody is left, generation raises **`NoEligibleTechnicianError`** (UI explains how to fix profiles or pool). Absent map keys mean **eligible**.
- **Proficiency (soft):** per `(tech_id, catalog_task_id)` ordinal (`novice` … `expert`) adds a small bonus from `ScoringWeights` (`proficiency_*_bonus`). Absent keys behave as **independent** with **zero** proficiency bonus. This is the **only** per-pair starting contribution before favorites, dislikes, fairness, and same-day terms (no separate neutral “base” prior). Rubric: [`proficiency_rubric.md`](proficiency_rubric.md).
- **Favorite bonus** if task is in `tech.favorites` (normalized name match).
- **Dislike penalty** if task is in `tech.dislikes`.
- **Extra dislike penalty** if candidate task is in `tech.dislikes` **and** assigned recently (see history); scales with recency/repeat count. This accounts for how many times in the lookback window the tech was already assigned to this same disliked task. Is on top of base dislike penalty.
- **Global fairness penalty** proportional to how often this tech has drawn **any** disliked task over a rolling window (supports rotation on “everyone hates it” work). This accounts for total recent exposure to disliked work.
- **Same-day preference (consistency / variation)**  
  Applies when this tech already has a **confirmed** assignment on the **same** `work_date` for a **different** `time_slot` (e.g. AM vs MID). Single-run generation only fills one slot band; cross-slot bonuses use persisted **confirmed** rows only, not draft.
  - **Consistency:** bonus if the new task matches the task from that other slot the same day.
  - **Variation:** bonus if the new task **differs** from that other slot’s task.

Tasks **not** in favorites or dislike lists: **no** favorite/dislike bonus or penalty (neutral).

### 2.3 Default policy and tie handling

The default `GreedyOptimizationConfig` is:

- local swap post-pass: **ON**
- lookahead tie-breaks: **ON**
- exact fallback for small pools: **ON** (`pool <= 9`)
- strict dislike avoidance: **ON**

What each flag does, why it’s on, and how to override it for benchmarking lives in [`greedy_scoring_policy_and_simulation.md`](greedy_scoring_policy_and_simulation.md). The flags are set in code (`scoring_types.py`); the Assignment Engine passes `greedy_optimization=None` so defaults always apply.

**Tie handling** inside the greedy loop is two-stage:

1. Find top-scoring technicians for the slot (**among eligible techs only**).
2. If lookahead tie-breaks are enabled, prefer candidates that preserve better future option counts.
3. If still tied, choose uniformly at random among tied candidates.

Use a **seeded RNG** (seed from UI/config) so runs are reproducible for debugging and tests; different seeds can produce different outcomes only where ties remain after lookahead.

**Exact small-pool DP:** ineligible pairs get score **−∞** so they are never chosen; if a slot has no finite score for any remaining tech, generation fails the same way as greedy.

**Local swap:** swaps are rejected if either technician would become **ineligible** for the task they would receive after the swap. Technicians placed via a **manual eligibility override** (see §2.4) are additionally **pinned** — the swap loop skips any pair involving a pinned `tech_id` so an explicit operator decision is never silently relocated.

### 2.4 Manual eligibility overrides (operator intent)

Manual pre-assignments in Step 6 normally respect the eligibility gate. When an operator picks a technician whose catalog `eligible_by_task_id[catalog_task_id]` is `false` (e.g. a trainee shadowing a senior), the UI surfaces a **two-stage confirmation** — a warning banner plus **Override eligibility** / **Cancel** — before adding the row. Confirmed overrides carry `eligibility_overridden=true` on the domain `Assignment` and on both persisted tables (`assignments`, `assignment_overrides`) so the flag survives draft → confirmed round-trips and appears in the audit listing. Overridden techs are **pinned** through the local-swap post-pass. The greedy scorer itself is unchanged: manual rows are applied first and the residual pool flows through the normal eligibility-gated greedy loop.

---

## 3. Weights and configuration

- Centralize weights (favorite bonus, dislike base penalty, recency multiplier, fairness frequency penalty, consistency/variation bonus, **proficiency level bonuses**) in **config** or constants with short comments (`DEFAULT_SCORING_WEIGHTS` in `scoring_weights_config.py`).
- Document units only loosely (“relative points”); tune empirically with stakeholders.

---

## 4. Simulation and benchmarking

The CLI and reporting story lives in [`greedy_scoring_policy_and_simulation.md`](greedy_scoring_policy_and_simulation.md); a frozen paired-benchmark snapshot is in [`greedy_scoring_paired_benchmark_report.md`](greedy_scoring_paired_benchmark_report.md).

---

## 5. Relation to the current codebase

The Streamlit app selects **one** `work_date` and **one** `time_slot` per run and assigns from `ScheduleRow` + `TaskRequest`, matching the single-slice persistence model. Greedy orchestration lives in `core/assignment/greedy_assigner.py`; scoring in `compatibility_scoring.py`; exact DP in `greedy_exact_match.py`; local swap in `greedy_local_swap.py`. See [`architecture_overview.md`](architecture_overview.md) for the full wiring (DB adapters → assign → draft/confirmed persistence).
