# Repository context (maintainer / agent map)

Living index of what lives where. **Last full pass:** 2026-04-09.

---

## Purpose

Streamlit app **Auto Assign**: upload a **schedule CSV**, choose **date** + **shift** (AM / MID / PM), set **task headcounts** from the DB task catalog, optionally apply **day-level** (call-off / overtime) and **slice-level** manual assignments, **generate** a greedy **draft**, then **Publish** (confirm) to PostgreSQL. Scoring uses **confirmed** assignment history only.

---

## Root

| Item | Notes |
|------|--------|
| `app.py` | `configure_page()` + `render_app()` → Streamlit. |
| `pyproject.toml` | Package `auto-assign-practice`, Python ≥3.11, deps: streamlit, sqlalchemy, alembic, pandas, psycopg, python-dotenv. Dev: pytest, ruff. |
| `uv.lock` | Locked deps for `uv`. |
| `.python-version` | `3.11`. |
| `.env` | **Local only**; listed in `.gitignore`. DB URL — see `.env.example`. |
| `.streamlit/config.toml` | Theme colors (committed). `secrets.toml` gitignored. |
| `alembic.ini` | Alembic config; DB URL from code, not this file. |
| `REPO_CONTEXT.md` | This file. |

---

## `src/auto_assign/`

### Package surface

- **`__init__.py`**: package marker only.
- **`core/__init__.py`**: re-exports CSV parsing, `assign_tasks`, `validate_tech_preference_lists`, availability helpers.

### UI (`ui/`)

| Module | Role |
|--------|------|
| `__init__.py` | Sidebar nav: Home, Technician Profiles, Task Catalog, Assignment history, About. DB pill via `database_url_configured()`. |
| `page.py` | `configure_page`, global CSS/theme, `render_page_header` (chrome only — no schedule coupling). |
| `home.py` | `render_home_page`: hero + cards, then embedded assignment engine via `schedule` package. |
| `components.py` | Shared Streamlit snippets: `render_step_panel`, `render_step_divider`, `render_context_chips` (classes from `page.render_theme`). |
| `schedule/` | **Package** for the assignment engine UI (split by concern); see table below. |
| `technicians_panel.py` | CSV + form CRUD for `technicians` via `db` helpers (`load_tech_by_tech_id`, `find_tech_id_for_normalized_tech_name`, etc.); task catalog required for favorites/dislikes validation. |
| `task_catalog.py` | CRUD `tasks` table via `task_repository`. |
| `assignment_history.py` | Read-only confirmed rows by date; filters; CSV export. |
| `about.py` | Long-form in-app engineering / operator copy. |
| `db_state.py` | `database_url_configured`, `tech_id_to_display_name`. |

**`ui/schedule/`** (workflow uses `assign_tasks`, repositories, `technician_ids_missing_from_db` for FK safety):

| File | Role |
|------|------|
| `__init__.py` | Public exports for the package. |
| `workflow.py` | Step machine: upload → date → day overrides → shift → pool → headcounts → manual rows → generate draft → publish/discard (~1k lines; Streamlit state + orchestration). |
| `state.py` | `session_state` key constants shared across schedule UI. |
| `helpers.py` | Pure helpers (slice keys, override signatures, `tech_id_for_row`). |
| `session_ops.py` | `start_new_schedule_run`, clearing keys for a new upload. |
| `discard.py` | Discard draft + slice overrides; sets flash / “start new run” flags. |
| `outcome_banner.py` | Post-publish CSV download + flash below the engine. |
| `copy.py` | Static markdown: quick reference expander + schedule CSV requirements card. |

### Database (`db/`)

| Module | Role |
|--------|------|
| `session.py` | `.env` load, `get_database_url`, engine, `session_scope`, `reset_engine_cache` (tests). |
| `base.py` | SQLAlchemy `Base`. |
| `models/technician.py` | `technicians`: PK `tech_id`, unique `tech_name`, JSON favorites/dislikes, `daily_preference`. |
| `models/assignment_record.py` | `assignments`: FK `technician_id`, `task_id` (stores task **name** string today), `work_date`, `time_slot`, `status` draft/confirmed, `slot_index`. |
| `models/task_catalog.py` | `tasks`: `task_id`, `task_name`, `default_count`. |
| `models/assignment_override.py` | `assignment_overrides`: audit for call-off, overtime, manual_assignment; scope day vs slice. |
| `assignment_repository.py` | `replace_draft_slice`, `confirm_slice`, `delete_draft_slice`, load helpers, `technician_ids_missing_from_db`. |
| `tech_repository.py` | upsert, list, delete, merge; `load_tech_by_tech_id`, `find_tech_id_for_normalized_tech_name` (read helpers for UI / services without ORM in callers). |
| `task_repository.py` | create/list/update/delete tasks; name uniqueness. |
| `override_repository.py` | Draft overrides; confirm promotion with slice. |
| `scheduling_repository.py` | `load_tech_profiles_by_name`, `load_confirmed_assignments_for_scoring` (confirmed only). |
| `tech_import_plan.py` | Import planning / dedupe / apply. |
| `adapters.py` | ORM ↔ domain `Assignment` / `Tech`. |
| `__init__.py` | Public DB API barrel export. |

### Assignment engine (`core/assignment/`)

| Module | Role |
|--------|------|
| `assignment_service.py` | `assign_tasks`: legacy shuffle vs greedy (`use_greedy_assignment`). |
| `greedy_assigner.py` | Slot ordering, greedy fill, hooks to exact match / local swap. |
| `compatibility_scoring.py` | Weighted score vs context + profile. |
| `scoring_types.py` | `GreedyOptimizationConfig`, `AssignmentScoringContext`, profiles. |
| `scoring_weights_config.py` | `DEFAULT_SCORING_WEIGHTS`. |
| `manual_overrides.py` | Apply day overrides; residual pool + task requests after manual rows. |
| `greedy_exact_match.py`, `greedy_local_swap.py` | Optimization passes. |
| `simulation.py` | Random scenarios + benchmarks (used by script). |

### CSV & validation (`core/csv_parsing/`, `ingestion/`)

| Module | Role |
|--------|------|
| `ingestion/csv_schema.py` | `ScheduleRow` dataclass + validation (`staffing_status`, availability flags). |
| `ingestion/task_request.py` | `TaskRequest` headcount request. |
| `validate_schedule.py` | `REQUIRED_COLUMNS`, `standardize_schedule_column_names` (legacy camelCase headers). |
| `normalize_schedule.py` | Title-case names, `YYYY-MM-DD` dates, availability bool normalization. |
| `parse_schedule.py` | `load_schedule`, `parse_schedule`. |
| `parse_tech_profiles.py` | Tech CSV → `Tech` list; `allowed_task_names` from catalog. |
| `get_available_techs.py` | Filter by date/slot; **`call_off` → never available** for assignment. |
| `get_available_dates.py` | Distinct dates in schedule. |
| `core/task_management/validate_task_request.py` | Headcount sum must equal pool size. |
| `core/task_management/validate_tech_preferences.py` | Favorites/dislikes rules (max 3 each, no overlap, catalog names). |

### Domain (`domain/`)

- `entities/tech.py`, `assignment.py`, `tasks.py`, `daily_staff.py`
- `enums.py`: `DailyPreference`, `TimeSlot`, `Staffing_Status`, `AssignmentStatus`, override enums
- `validators/primitives.py`: strings, dates, `normalize_tech_id`

---

## `alembic/`

- `env.py`: `get_database_url()`, `target_metadata = Base.metadata` (ensure new models imported for autogenerate).
- `versions/`: linear migrations from initial technicians+assignments → profile-only techs → slot_index → tasks catalog → assignment_overrides.

---

## `tests/`

- `conftest.py`: minimal (placeholder comment).
- Coverage: DB session URL rewriting, repositories, parsers, greedy assignment, overrides, scheduling, tech merge/delete, normalization, etc.
- Many tests use **SQLite in-memory** via monkeypatched `DATABASE_URL` and `reset_engine_cache`.

---

## `scripts/`

- `run_greedy_simulation.py`: CLI benchmark; prepends `src` to path; `--mode paired|sanity`.

---

## `data/`

- `sample_schedule.csv`, `sample_tech_profiles.csv`: align with `docs/csv_contract.md`.
- `tech_profiles.csv`: larger fixture-style file.

---

## `docs/` (markdown)

| File | Focus |
|------|--------|
| `assignment_algorithm.md` | Greedy design, draft vs confirmed semantics. |
| `persistence_database.md` | Schema, indexes, overrides. |
| `assignment_persistence_feature_summary.md` | E2E implementation narrative. |
| `technician_profiles_ingestion.md` | CSV vs form, uniqueness. |
| `greedy_scoring_policy_and_simulation.md` | Default policy + running simulations. |
| `greedy_scoring_paired_benchmark_report.md` | Benchmark table. |
| `operator_runbook.md` | **Operator quick path + troubleshooting** (added with README refresh). |
| `csv_contract.md` | **Authoritative column / enum reference** for CSVs (added with README refresh). |
| `examples/sample_task_list.yaml` | Illustrative task list only; app uses DB **Task Catalog**. |

---

## Gaps / follow-ups

- `alembic/env.py` imports only `AssignmentRecord`, `Technician` for metadata; other models are pulled via relationships — OK if `Base.metadata` registers all linked tables; verify when adding **new** unreferenced tables.
- `config.yaml` at repo root **removed**; replaced by `docs/examples/sample_task_list.yaml`.
- Streamlit **About** page does not link to markdown files on disk (in-app copy only); README and runbook point to `docs/`.
