# Persistence and database design (scoring + scheduling)

This document complements [`assignment_algorithm.md`](assignment_algorithm.md) **§1 Persistence model**. It describes how to back the greedy scorer with a database, which tables you need at minimum, and what is optional as the product grows.

---

## 1. Layers: SQLAlchemy vs Pydantic

| Layer | Role |
|--------|------|
| **SQLAlchemy** | ORM models = **tables**, relationships, migrations (Alembic). This is the **source of truth** for stored data. |
| **Pydantic** | **Schemas** for boundaries: CSV import rows, API request/response bodies, and explicit validation before you build domain `Tech` / `Assignment` objects. Optional: small mappers `orm_instance → domain` and `domain → orm`. |

You do **not** need a separate database table for **`TechScoringProfile`**. It remains an in-memory view built when you load a `Tech` (or join technician + favorites/dislikes) for `compatibility_score`.

---

## 2. Tables required for the current scoring design

### 2.1 `technicians` (from tech CSV → DB)

**Purpose:** Stable identity and preference data used to build **`TechScoringProfile`** (and domain `Tech`).

**Typical columns**

| Column | Notes |
|--------|--------|
| `id` / `tech_id` | Primary key; stable business id (matches CSV and FK targets). |
| `tech_name` | Normalized display name; schedule CSV matches by name; persisted assignments use **`tech_id`** on `Assignment.technician_id` and FK `assignments.technician_id`. |
| `daily_preference` | Enum: consistency / variation. |
| `staff_status` | If you use it for eligibility (see domain `Tech`). |
| `available_am`, `available_mid`, `available_pm` | Or equivalent; mirrors current `Tech` if scheduling still depends on them. |
| `favorites` / `dislikes` | Either **JSON arrays** of normalized task names, or **junction tables** `technician_favorites(technician_id, task_id)` / `technician_dislikes(...)` (see §4). |

**CSV → DB:** One import job validates each row (Pydantic or domain `Tech`), upserts by `tech_id`, then the app reads technicians when building `tech_profiles_by_name` for `assign_tasks`.

For **CSV vs form**, **uniqueness**, and a **hardening checklist**, see [`technician_profiles_ingestion.md`](technician_profiles_ingestion.md).

---

### 2.2 `assignments` (history + draft workspace)

**Purpose:** Official **history** for fairness and same-day preference, plus **draft** rows for the current generate/regenerate cycle. Behavior matches **§1.3** in `assignment_algorithm.md`: **one table**, **`status`** = draft | confirmed.

**Typical columns**

| Column | Notes |
|--------|--------|
| `id` | Surrogate PK (recommended). |
| `technician_id` | FK → `technicians.tech_id` (or same string key if you defer FK). |
| `work_date` | `DATE`. |
| `time_slot` | Enum/string: AM / MID / PM. |
| `task_name` or `task_id` | Normalized task label; prefer **`task_id` FK** if you add a `tasks` table (§3). |
| `status` | `draft` \| `confirmed`. |
| `slot_index` | Optional but useful when two rows are “same task, two heads” for one `(date, slot)`—disambiguates without composite uniqueness hacks. |
| `created_at`, `updated_at`, `confirmed_at` | Optional audit fields. |

**Scoring rule (from algorithm doc):** Queries that feed **`AssignmentScoringContext.confirmed_assignments`** must filter **`status = confirmed`** only. Draft rows must not affect fairness, repeat-dislike, or cross-slot consistency.

**Indexes (recommended for lookbacks):**

- `(status, work_date)` or `(work_date, status)` for “confirmed in date range”.
- `(technician_id, work_date, status)` for per-tech history windows.

---

## 3. Recommended extra table (not strictly required)

### 3.1 `tasks` (task catalog)

**Why:** Assignments currently use normalized **task names**. A **`tasks`** table gives you:

- One persisted source of truth for task names/default headcounts used by the UI.
- Stable **`task_id`** for catalog records and future referential integrity upgrades.

This table is now part of the default app schema and is managed on the **Task Catalog** page.

---

## 4. `assignment_overrides` (manual override audit + draft)

The Assignment Engine now persists day-of override edits in a dedicated table.

| Column | Notes |
|--------|-------|
| `work_date` | Date the override applies to. |
| `time_slot` | Nullable; set for slice-scoped manual assignments, null for day-scoped availability edits. |
| `scope` | `day` (availability override across AM/MID/PM) or `slice` (manual pre-assignment for one shift). |
| `kind` | `call_off`, `overtime`, or `manual_assignment`. |
| `technician_id` | FK to `technicians.tech_id`. |
| `task_name` | Set only for `manual_assignment`. |
| `status` | `draft` during planning, promoted to `confirmed` at publish for audit retention. |

Draft overrides reload with the slice and are cleared or promoted by publish/discard workflows.

---

## 5. Optional tables (product-dependent)

| Table / concern | When you need it |
|-----------------|------------------|
| **Availability / schedule** (e.g. `schedule_rows`: `work_date`, `time_slot`, `technician_id`, flags) | When daily “who is on the floor” stops being a CSV-only ingest and must be queried from the DB for the assignment pool. |
| **Junction `technician_favorites` / `technician_dislikes`** | When favorites/dislikes are many-to-many, need per-row metadata, or you want strict FK to `tasks`. |
| **Import staging / audit** | When you must trace each CSV batch (filename, imported_at, row-level errors). |
| **Profile history** | When you need time-travel (“score using prefs as of date X”)—usually overkill initially. |

---

## 6. Are you missing anything for scoring?

For **this** scoring mechanism and `assignment_algorithm.md`:

| Need | Covered by |
|------|------------|
| Tech identity + prefs → `TechScoringProfile` | **`technicians`** (+ favorites/dislikes representation). |
| Confirmed history + draft cycle | **`assignments`** + **`status`**. |
| Day-of availability/manual pre-assign edits | **`assignment_overrides`** (`draft`/`confirmed`). |
| Task catalog + defaults | **`tasks`** (managed in Task Catalog UI). |
| Daily candidate pool from DB | **Optional** availability table (not required if pool still comes from schedule CSV/API). |

You do **not** need a separate table for **score weights**; defaults live in code (`scoring_weights_config.py`) unless you later add a **config** table for runtime tuning.

---

## 7. Mapping to current domain types

| Domain / scoring type | DB source |
|------------------------|-----------|
| `Tech` | Row(s) from `technicians` (+ favorites/dislikes). |
| `TechScoringProfile` | Built in memory from `Tech` (or directly from ORM + normalization). |
| `Assignment` (for `confirmed_assignments`) | Rows from `assignments` where `status = confirmed`, mapped to domain `Assignment` (`task_name`, `technician_id`, `date_assigned`, `time_slot`). |

---

## 8. Operator runbook (current app)

The Streamlit app under [`app.py`](../app.py) delegates UI to [`src/auto_assign/ui/`](../src/auto_assign/ui/). Persistence and greedy scoring are wired as follows.

1. **Install:** `uv sync` (from repo root).  
2. **Database URL:** Set `DATABASE_URL` or `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` in `.env`. Use **`postgresql+psycopg://...`** for psycopg v3, or a bare `postgresql://` URL (the app normalizes it to `+psycopg` when needed).  
3. **Migrate:** `uv run alembic upgrade head`.  
4. **Technicians:** In the app, expand **Technician profiles** and import the tech CSV (or use the form) so every schedule name maps to a **`tech_id`** row. Unmapped names produce synthetic ids that **will not confirm** until profiles exist (FK).  
5. **Schedule:** Upload the schedule CSV, pick date and slot, set task counts, optionally open **Scoring options** (random seed, fairness lookback or unlimited history).  
6. **Overrides (optional):** In Assignment Engine, apply day-wide call-off edits, shift-specific overtime edits, and manual pre-assignments before generate. These save as **draft** override rows.  
7. **Generate:** Writes **draft** assignment rows for `(work_date, time_slot)` and refreshes from DB on reload (with draft overrides).  
8. **Confirm:** Replaces **draft + confirmed** assignments for that slice and promotes related draft override rows to **confirmed** audit rows.

**Current state:** `tasks` is persisted and used by the UI for task maintenance and validation.  
**Future optional step:** add FK-level referential integrity between assignment rows and catalog ids.

---

## 9. Implementation status (reference)

| Piece | Location |
|--------|-----------|
| Models + migrations | `src/auto_assign/db/models/`, `alembic/versions/` |
| Manual override persistence | `db/models/assignment_override.py`, `db/override_repository.py` |
| Load tech profiles by name | `load_tech_profiles_by_name` in `scheduling_repository.py` |
| Confirmed history for scoring | `load_confirmed_assignments_for_scoring` |
| Draft load / slice replace / FK check | `load_draft_assignments_for_slice`, `replace_draft_slice`, `confirm_slice`, `technician_ids_missing_from_db` in `assignment_repository.py` |
| Greedy entrypoint | `assign_tasks(..., use_greedy_assignment=True, ...)` |

The greedy scorer and weights stay in `src/auto_assign/core/assignment/`; the DB is only an adapter feeding `tech_profiles_by_name` and `confirmed_assignments`.
