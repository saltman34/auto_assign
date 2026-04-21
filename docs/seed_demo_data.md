# Seed demo data

How to populate an empty database with a realistic starter dataset — 18 technicians, a 6-task catalog, and two weeks of confirmed assignment history — so the scheduler has something to work with on the first click. This is the fastest path from an empty app to a meaningful demo and the only path that populates the eligibility and proficiency that CSV imports cannot carry today.

---

## 1. Why the seeder exists

The CSV import path covers half the data the scorer needs: tech names, daily preferences, favorites, and dislikes. Two things are missing:

- **Eligibility and proficiency** are stored in the `technicians` table keyed by catalog `task_id` and are edited through the **Technician Profiles** UI, not the CSV. A CSV-only import leaves every tech eligible-by-default with zero proficiency — the greedy scorer has almost nothing to distinguish candidates.
- **Confirmed history** is what drives the fairness lookback (`lookback_days=14`). An empty DB gives you an empty history, so fairness terms contribute nothing on the first few drafts.

The seeder fills both gaps: it creates the catalog, upserts 18 technicians with full eligibility + proficiency maps, and then runs the real greedy scorer once per past day and time slot to generate 14 days of confirmed rows.

---

## 2. What gets written

### Task catalog (6 rows)

| `task_id`    | `task_name`     | `default_count` |
|--------------|-----------------|:---:|
| `T-CLIN`     | Clinicals       | 2 |
| `T-RECUT`    | Recuts          | 0 |
| `T-SCROLL`   | Scrolls         | 1 |
| `T-EMBED`    | Embedding       | 2 |
| `T-GROSS`    | Grossing        | 1 |
| `T-EXHAUST`  | Exhaust Checks  | 0 |

Defaults sum to **6**. Recuts and Exhaust Checks ship at `0` to model "on-demand" tasks — Step 5 shows them with a zero count until an operator deliberately bumps them up. A typical pool of 10–12 available techs per slot leaves several slots of headroom so count allocation is an actual exercise, not a fixed answer.

### 18 technicians across four archetypes

Each archetype exists so a distinct scoring term has something to express in the output:

| Archetype | Count | Signal they drive | Shape |
|-----------|:---:|---|---|
| **Clinicals specialist** | 2 | Favorites + expert proficiency bonuses | `EXPERT` on Clinicals, `STRONG` on a neighbor, `INDEPENDENT` elsewhere |
| **Grossing specialist** | 2 | Same, on a different discipline | `EXPERT` on Grossing, `STRONG` on a neighbor, `INDEPENDENT` elsewhere |
| **Embedding specialist** | 1 | Expert coverage for a high-default task | `EXPERT` on Embedding, `STRONG` on Grossing |
| **Recuts specialist** | 1 | Expert coverage for an on-demand task | `EXPERT` on Recuts, `STRONG` on Scrolls |
| **Generalist** | 9 | The "reasonable bench pick" case | `INDEPENDENT` everywhere with 2 `STRONG` tasks each; a few dislikes |
| **Trainee** | 3 | Pool filtering + manual override flow | `NOVICE` everywhere, one ineligibility each (`Exhaust Checks`, `Grossing`, `Clinicals`) |

Three hard ineligibilities are baked in on purpose so you can demo:

- the pool filter quietly skipping an ineligible tech, and
- the Step 6 two-stage manual-override flow if you want to force a trainee onto a task they are not certified for.

### Availability and confirmed history

The seeder generates 21 consecutive days of `ScheduleRow`s starting 14 days before `today`. Per tech per day it rolls a small chance of `call_off` and a smaller chance of `overtime`, then flips AM / MID / PM flags independently. At least one slot is always available on scheduled days so no row is a no-op.

For each of the 14 past days and 3 time slots, the seeder:

1. Filters the pool to whoever is available and not called off.
2. Builds task requests whose headcounts sum **exactly** to the pool size (high-default tasks first; low-default tasks drop to zero when the pool is tight).
3. Loads prior confirmed history within the 14-day lookback window.
4. Runs `assign_tasks(..., use_greedy_assignment=True, ...)` — the same entry point the UI uses.
5. Calls `confirm_slice(...)` so the result is persisted as `CONFIRMED` and feeds the next iteration's fairness context.

The future 7 days of availability are **not** persisted. They are returned from `seed_demo_data(...)` as a list of `ScheduleRow` and — in the UI flow — offered as a downloadable CSV for the operator to upload back into the Schedule CSV field. This mirrors the real operator workflow (availability lives in CSV, not in the database) and keeps the "generate a draft" step feeling like a real action rather than a prefilled one.

---

## 3. How to run it

### From the app (recommended for demos)

On the **Home** page:

- If the database is empty, a blue-accented "Load demo data" card sits at the top of the page. Click it.
- If the database already has technicians, the same controls live inside a **Demo data** expander with both "Load" and a two-step "Reset" button.

After a successful load you will see a green banner with a **Download demo schedule CSV** button. Drop that file into the **Schedule CSV** uploader in the Assignment Engine section directly below, pick any day in the 7-day window, and generate a draft.

### From the command line

```bash
python scripts/seed_demo_data.py seed              # populate DB
python scripts/seed_demo_data.py reset             # clear DB
python scripts/seed_demo_data.py regenerate-csvs   # rewrite data/sample_*.csv
```

`seed` and `reset` use the same `DATABASE_URL` your app does. `regenerate-csvs` writes to `data/sample_schedule.csv` and `data/sample_tech_profiles.csv` from the same fixture module, using pinned absolute dates so the files stay reproducible across runs.

### Programmatically (tests, scripts)

```python
from auto_assign.db import session_scope
from auto_assign.demo import seed_demo_data, reset_demo_data

with session_scope() as session:
    result = seed_demo_data(session)  # today=date.today(), seed=20260617 by default

with session_scope() as session:
    reset_demo_data(session)
```

Both functions take an open `Session` and rely on the caller for commit (via `session_scope()`). `seed_demo_data` accepts `today=` (defaults to `date.today()`) and `seed=` (defaults to a fixed RNG seed) so you can pin both for deterministic tests — see `tests/test_demo_seed.py`.

---

## 4. Relationship to persistence

The seeder does **not** change the database schema. It writes through the same repositories (`upsert_technicians`, `TaskCatalog` inserts via the session, `confirm_slice`) that the UI and scheduled runs use. The only invariants worth naming:

- It writes **confirmed rows only**. Drafts are per-slice scratch space and should feel fresh to the operator. Generating a draft is the demo's first user action, not the seeder's.
- It does **not** write any `assignment_overrides` rows. Manual overrides are a deliberate operator action; seeding them would muddy what "overridden" means in the audit trail.
- Past history uses `date.today() - N` at seed time, so running the seeder twice on different calendar days produces two different history windows — by design, so the fairness lookback always lines up with "now."

See [`persistence_database.md`](persistence_database.md) for the full table and index story behind the draft/confirmed split.

---

## 5. Reset semantics

`reset_demo_data(session)` truncates, in order:

1. `assignment_overrides`
2. `assignments` (both draft and confirmed)
3. `technicians`
4. `tasks`

It is **not scoped to demo-seeded rows**. The schema has no way to distinguish demo data from real data once it lives in the database, so `reset` is a full wipe. Intended for local development and portfolio demos; do not wire the button to a production environment.

---

## 6. Related docs

- [`operator_runbook.md`](operator_runbook.md) — overall install/run path, including where the demo button sits in the workflow.
- [`csv_contract.md`](csv_contract.md) — the CSV shapes `write_sample_csvs` produces; references back here for the full-featured demo path.
- [`assignment_algorithm.md`](assignment_algorithm.md) — what the scorer does with the eligibility, proficiency, favorites, and fairness data the seeder produces.
