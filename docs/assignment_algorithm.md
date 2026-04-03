# Greedy assignment algorithm — design notes

This document captures the intended behavior for moving from random assignment to **greedy, score-based** matching using technician preferences, fairness, and **persisted** tech and history data.

For **concrete tables**, SQLAlchemy/Pydantic layering, and optional extras beyond technicians + assignments, see [`persistence_database.md`](persistence_database.md).

---

## 1. Persistence model

### 1.1 Two logical stores

| Store | Role |
|--------|------|
| **Technicians** | Stable profile: `tech_id`, display name, daily preference (consistency / variation), favorite task names, disliked task names, eligibility flags as needed. |
| **Assignments** | Rows that tie **who** was assigned **what**, **when**, and in **which shift** (`date`, `time_slot`, `task_id` or task name, `tech_id`). |

The scorer reads **tech** profiles for bonuses/penalties. It reads **assignment rows** for same-day consistency/variation, recency on dislikes, and **global fairness** (how often someone drew disliked work)—using only rows that count as **confirmed** (see below).

### 1.2 Scope: one generation per `work_date` + `time_slot`

The product flow generates assignments for **exactly one** calendar date and **one** shift band (AM / MID / PM) per action. There is **no** batch “whole week” or “all slots today” generation in this iteration; each run is scoped to `(work_date, time_slot)` only. Other dates and slots in the database are not modified by that run.

### 1.3 One assignments table + `status` column (chosen design)

Use a **single** assignments table. Each row includes a **`status`** that distinguishes **draft** from **confirmed** (names can be `draft` / `confirmed` or equivalent enums).

| Action | Behavior |
|--------|----------|
| **Generate** / **Regenerate schedule** | For the current `(work_date, time_slot)` scope: **delete** existing **`draft`** rows for that pair, then **insert** the new greedy result as **`draft`**. Rows for other `(work_date, time_slot)` pairs are unchanged. **Confirmed** rows for this scope are not touched by regenerate (until confirm replaces them—see below). |
| **Confirm schedule** | For that same `(work_date, time_slot)`: in **one transaction**, **delete** all **`draft` and `confirmed`** rows for that pair, then **insert** the chosen assignment set as **`confirmed`** (atomic whole-slice replace). UI warns only before confirm if confirmed rows already exist. |

**Fairness and scoring** (recent dislikes, rotation, “how often drew any disliked task,” reporting) should query **`status = confirmed`** only. **Draft** rows are scratch space: regenerating must **not** inflate penalties or history as if people had already worked those tasks.

**Summary:** Overwrite-in-place is applied **within** the table by scope `(work_date, time_slot)` and **status**: regenerate replaces **draft**; confirm promotes that slice to **confirmed** and overwrites the previous confirmed slice for that pair.

### 1.4 What to store per assignment row (minimum)

- `tech_id`, `task_id` (or normalized task name key), `work_date`, `time_slot`, **`status`**
- Distinguish multiple headcount slots for the same task if needed: e.g. `slot_index` or stable surrogate key per open slot
- Optional: `created_at`, `confirmed_at`, `updated_at` for audit UI

No separate draft vs confirmed **tables** in this design—only the **`status`** column (Option A as agreed).

---

## 2. Greedy procedure

### 2.1 Slot ordering — most constrained first

Process **task slots** in an order that handles scarcity first (e.g. few technicians with acceptable scores, or globally unpopular tasks). For each slot in that order, pick the **best remaining** technician (highest score among those not yet assigned in this run).

This reduces wasting strong matches on easy slots while leaving impossible-looking slots for last.

### 2.2 Compatibility score (conceptual)

Use a **weighted sum** (tune via config/constants):

- **Base** (optional): neutral or small prior per tech–task pair.
- **Favorite bonus** if task ∈ `tech.favorites` (normalized name match).
- **Dislike penalty** if task ∈ `tech.dislikes`.
- **Extra dislike penalty** if task ∈ `tech.dislikes` **and** assigned recently (see history); scale with recency/repeat count as needed.
- **Global fairness penalty** proportional to how often this tech has drawn **any** disliked task over a rolling window (supports rotation on “everyone hates it” work).
- **Same-day preference (consistency / variation)**  
  Applies when this tech already has a **confirmed** assignment on the **same** `work_date` for a **different** `time_slot` (e.g. AM vs MID). Single-run generation only fills one slot band; cross-slot bonuses use persisted **confirmed** rows only, not draft.
  - **Consistency:** bonus if the new task matches the task from that other slot the same day.
  - **Variation:** bonus if the new task **differs** from that other slot’s task.

Tasks **not** in favorites or dislike lists: **no** favorite/dislike bonus or penalty (neutral).

### 2.3 Ties and reproducibility

- If multiple techs share the **same** top score for a slot, choose **uniformly at random** among ties.
- Use a **seeded RNG** (pass seed from config or UI) so runs are reproducible for debugging and tests; different seed → different tie breaks.

Optional: shuffle technician order **before** greedy with the same RNG so tie-breaking does not always favor the same ID ordering.

---

## 3. Weights and configuration

- Centralize weights (e.g. favorite bonus, dislike base penalty, recency multiplier, fairness frequency penalty, consistency/variation bonus) in **config** or constants with short comments.
- Document units only loosely (“relative points”); tune empirically with stakeholders.

---

## 4. Future upgrades

- If greedy quality is insufficient, keep the **same scoring function** and swap the optimizer (e.g. **minimum-cost bipartite matching**) without changing business rules.

---

## 5. Relation to the current codebase

The Streamlit app already selects **one** `work_date` and **one** `time_slot` per session and assigns from **`ScheduleRow`** + **`TaskRequest`**. That matches the **single-scope** persistence model above.

Next steps align with the doc: persist **tech** profiles; persist assignments in **one table** with **`draft` / `confirmed`**; wire **Generate** → draft replace, **Confirm** → promote slice to confirmed; use **confirmed** rows only for fairness and same-day preference when scoring.
