# Persistence and database design (scoring + scheduling)

How assignments are stored in Postgres. Each shift goes through a two-stage lifecycle — an editable **draft** that can be regenerated freely, and a **confirmed** slice that becomes the historical record used by fairness scoring — and this doc covers the full schema (tables, indexes, and the optional override/audit tables) that makes that split work.

---

## 0. Persistence concept: draft vs confirmed, one slice at a time

The scorer and the UI share one invariant: **assignments live in one table with a `status` column**, and every write happens within a single `(work_date, time_slot)` **slice**.

### 0.1 Two logical stores the scorer reads

| Store | Role |
|--------|------|
| **Technicians** | Stable profile: `tech_id`, display name, daily preference (consistency / variation), favorite/disliked **task names**, plus per–catalog-task **eligibility** (hard gate) and **proficiency** (ordinal bonus). See [`proficiency_rubric.md`](proficiency_rubric.md). |
| **Assignments** | Rows that tie **who** was assigned **what**, **when**, and in **which shift** (`date`, `time_slot`, display task label, optional `catalog_task_id`, `tech_id`). |

The scorer reads **tech** profiles for bonuses/penalties. It reads **assignment rows** for same-day consistency/variation, recency on dislikes, and **global fairness**—using only rows that count as **confirmed** (see §0.3).

### 0.2 Scope: one generation per `work_date` + `time_slot`

Every generate/publish action is scoped to **exactly one** calendar date and **one** shift band (AM / MID / PM). There is **no** batch “whole week” or “all slots today” generation in this iteration; other dates and slots are never modified by a given run.

### 0.3 One assignments table + `status` column (chosen design)

Each assignment row has a **`status`** that distinguishes **draft** from **confirmed**.

| Action | Behavior |
|--------|----------|
| **Generate** / **Regenerate schedule** | For the current `(work_date, time_slot)` scope: **delete** existing **`draft`** rows for that pair, then **insert** the new greedy result as **`draft`**. Rows for other `(work_date, time_slot)` pairs are unchanged. **Confirmed** rows for this scope are not touched by regenerate (until confirm replaces them—see below). |
| **Confirm schedule** | For that same `(work_date, time_slot)`: in **one transaction**, **delete** all **`draft` and `confirmed`** rows for that pair, then **insert** the chosen assignment set as **`confirmed`** (atomic whole-slice replace). UI warns only before confirm if confirmed rows already exist. |

**Fairness and scoring** queries filter **`status = confirmed`** only. **Draft** rows are scratch space: regenerating must **not** inflate penalties or history as if people had already worked those tasks.

**Summary:** Overwrite-in-place is applied **within** the table by scope `(work_date, time_slot)` and **status**: regenerate replaces **draft**; confirm promotes that slice to **confirmed** and overwrites the previous confirmed slice for that pair. There are **no** separate draft vs confirmed tables.

### 0.4 What to store per assignment row (minimum)

- `tech_id`, `task_id` (or normalized task name key), `work_date`, `time_slot`, **`status`**.
- Distinguish multiple headcount slots for the same task if needed (e.g. `slot_index`).
- Optional: `created_at`, `confirmed_at`, `updated_at` for audit UI.

---

## 1. Layers: SQLAlchemy vs Pydantic

| Layer | Role |
|--------|------|
| **SQLAlchemy** | ORM models = **tables**, relationships, migrations (Alembic). This is the **source of truth** for stored data. |
| **Pydantic** | **Schemas** for boundaries: CSV import rows, API request/response bodies, and explicit validation before you build domain `Tech` / `Assignment` objects. Optional: small mappers `orm_instance → domain` and `domain → orm`. |


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
| `favorites` / `dislikes` | **JSON arrays** of normalized task **names** (same convention as domain `Tech`). |
| `eligible_by_task_id` | JSON object: catalog **`tasks.task_id`** → `false` to hard-exclude; absent keys = eligible. |
| `proficiency_by_task_id` | JSON object: catalog **`tasks.task_id`** → proficiency enum value string (`novice`, `independent`, `strong`, `expert`). Absent keys = independent (no proficiency bonus). |

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
| `task_id` (ORM column) | Normalized **display** task label for UI and favorites alignment (legacy name in code: `AssignmentRecord.task_id`). |
| `catalog_task_id` | Optional catalog **`tasks.task_id`** for eligibility/proficiency scoring; null on older rows (scoring falls back to display label). |
| `status` | `draft` \| `confirmed`. |
| `slot_index` | Optional but useful when two rows are “same task, two heads” for one `(date, slot)`—disambiguates without composite uniqueness hacks. |
| `eligibility_overridden` | Boolean (default `false`). True only for manual pre-assignments where the operator explicitly placed a tech the catalog flags as ineligible (training / shadowing). Greedy-produced rows are always `false`. Carried through draft → confirmed so the audit badge survives round-trips. |
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
| `eligibility_overridden` | Boolean (default `false`). Set to `true` on a `manual_assignment` row when the operator explicitly placed a tech whose `eligible_by_task_id[catalog_task_id]` is `false`. Always `false` for `call_off` / `overtime` rows. |

Draft overrides reload with the slice and are cleared or promoted by publish/discard workflows.

**Eligibility-override flow (Step 6, manual assignments):** the UI evaluates `eligible_by_task_id` on Add; ineligible pairs trigger a two-stage confirmation (warning banner + **Override eligibility** / **Cancel**). Confirmed overrides persist the flag on both `assignments.eligibility_overridden` and `assignment_overrides.eligibility_overridden` so the audit trail survives publish and the local-swap post-pass pins overridden techs (see [`assignment_algorithm.md`](assignment_algorithm.md) §2.3).

---

## 5. Optional tables (product-dependent)

| Table / concern | When you need it |
|-----------------|------------------|
| **Availability / schedule** (e.g. `schedule_rows`: `work_date`, `time_slot`, `technician_id`, flags) | When daily “who is on the floor” stops being a CSV-only ingest and must be queried from the DB for the assignment pool. |
| **Junction `technician_favorites` / `technician_dislikes`** | When favorites/dislikes are many-to-many, need per-row metadata, or you want strict FK to `tasks`. |
| **Import staging / audit** | When you must trace each CSV batch (filename, imported_at, row-level errors). |
| **Profile history** | When you need time-travel (“score using prefs as of date X”)—usually overkill initially. |


---

## 6. Necessary items for scoring

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
| `TechScoringProfile` | Not persisted. Built in memory from `Tech` (or directly from ORM + normalization). |
| `Assignment` (for `confirmed_assignments`) | Rows from `assignments` where `status = confirmed`, mapped to domain `Assignment` (`task_name`, `technician_id`, `date_assigned`, `time_slot`). |

---

## 8. Operator runbook

Operator steps (install → migrate → publish → troubleshoot) live in a single place: [`operator_runbook.md`](operator_runbook.md). This doc intentionally does not duplicate them.

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
