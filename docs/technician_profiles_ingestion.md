# Technician profiles: desired features and system integration

How a technician profile enters the system — whether via bulk CSV upload or the in-app form — how each incoming row is turned into the `Tech` object the rest of the app uses, and how duplicate profiles are prevented across both paths so every technician appears exactly once.

---

## 1. Product goals

| # | Feature | Intent |
|---|---------|--------|
| **A** | **CSV upload** | User uploads a tech profile CSV; rows are parsed, validated, mapped to domain **`Tech`**, then persisted into the **`technicians`** table. |
| **B** | **Manual form** | User fills a form (one technician at a time); fields map to **`Tech`**, then the row is saved to **`technicians`**. |
| **C** | **No duplicate technicians** | Each real person should appear **at most once** in `technicians`: stable identity (`tech_id`) and a single canonical display name (`tech_name`) for schedule matching and FK integrity on assignments. |

Features **A** and **B** are **already implemented** in the Streamlit UI. Feature **C** is **partially enforced** by the schema and upsert logic; see §4.

---

## 2. Data model (single source of truth)

- **Table:** `technicians` ([`Technician`](../src/auto_assign/db/models/technician.py) ORM).
- **Primary key:** `tech_id` — stable business id (matches CSV, assignment FKs, and domain `Assignment.technician_id`).
- **Display / schedule matching:** `tech_name` — normalized (title case) in domain [`Tech`](../src/auto_assign/domain/entities/tech.py); must align with schedule CSV **`tech_name`** for `load_tech_profiles_by_name` lookups.
- **Uniqueness:** `UNIQUE (tech_name)` on the table (`uq_technicians_tech_name`) so **two different `tech_id`s cannot share the same stored name** — avoids ambiguous schedule resolution.

Downstream, assignment scoring loads profiles with [`load_tech_profiles_by_name`](../src/auto_assign/db/scheduling_repository.py), which keys by **normalized `tech_name`** and **raises** if two rows collapse to the same key.

---

## 3. Path A — CSV upload

### Desired behavior

1. User selects a file in the **Technician profiles** expander → **Upload CSV** tab ([`technicians_panel.py`](../src/auto_assign/ui/technicians_panel.py)).
2. CSV is read and validated for required columns.
3. Each row becomes a **`Tech`** instance (constructor runs validation / normalization).
4. All rows are written in one transaction via **`upsert_technicians`**.

### Current integration (call chain)

```
Streamlit (technicians_panel.py)
  → load_tech_profile_csv(file)     # core/csv_parsing/parse_tech_profiles.py
  → parse_tech_profiles(df)         # → list[Tech]
  → session_scope()
       → upsert_technicians(session, techs)   # db/tech_repository.py
            → merge_technician_from_tech(session, t) per row
```

- **`merge_technician_from_tech`:** If `tech_id` **already exists**, the existing row is **updated** (same person, refreshed fields). If it does **not** exist, a new row is **inserted**.

### CSV contract

Column names, types, and validation rules live in [`csv_contract.md`](csv_contract.md) §2. Favorites/dislikes are validated by [`validate_tech_preference_lists`](../src/auto_assign/core/task_management/validate_tech_preferences.py) against the DB-backed `tasks` catalog (no duplicates in a list, no overlap between favorites and dislikes, at most three each). Sample: [`data/sample_tech_profiles.csv`](../data/sample_tech_profiles.csv).

### Duplicate semantics (CSV)

- **Same `tech_id` appears twice in one file:** Both rows are processed in order; the **last** row wins for that id (upsert overwrites). There is still **only one** DB row per `tech_id`.
- **Two rows, different `tech_id`, same `tech_name` (after normalization):** The **second** insert/update can hit **`uq_technicians_tech_name`** and fail the transaction — user sees a DB/integrity error unless you add **pre-flight validation** (recommended hardening below).

---

## 4. Path B — Manual form

### Desired behavior

1. User opens **Form** tab in the same expander.
2. Submits `tech_id`, `tech_name`, flags, enums, optional favorites/dislikes.
3. Build **`Tech`** via [`task_names_from_form_field`](../src/auto_assign/core/csv_parsing/parse_tech_profiles.py) for list fields.
4. **`merge_technician_from_tech`** inside **`session_scope`** — same upsert semantics as CSV.

### Duplicate semantics (form)

- **Existing `tech_id`:** Row is **updated** (not a second row).
- **New `tech_id` but `tech_name` already used by another id:** Insert fails on **`uq_technicians_tech_name`** unless you catch it and show a friendly message (recommended hardening).

---

## 5. “Each tech only once” — how the system enforces it

| Mechanism | What it guarantees |
|-----------|---------------------|
| **`tech_id` PRIMARY KEY** | At most **one row per id**; upsert is **idempotent** per id. |
| **`tech_name` UNIQUE** | At most **one row per display name** (as stored). Prevents two ids claiming “Alice”. |
| **`load_tech_profiles_by_name`** | Runtime check: no two technicians may map to the same normalized name key when loading for scoring. |

What it does **not** guarantee without extra UX/logic:

- **Friendly errors** when uniqueness fails (user may see raw `IntegrityError`).
- **CSV-internal conflicts** (duplicate `tech_id` or clashing `tech_name`) called out **before** hitting the database.
- **Strict “insert only, never update”** — today the product choice is **upsert** (update-by-`tech_id`), which is usually correct for profile refresh from CSV.

---

## 6. Recommended integrations / hardening (build plan)

These are **optional next steps** if you want the behavior to match the wording “cannot add twice” more explicitly in the UI.

1. **Pre-validate CSV in memory** (before `session_scope`):
   - Detect duplicate `tech_id` in the file → warn or error, or document “last row wins.”
   - Detect duplicate / conflicting `tech_name` (after `normalize_string`) → single clear error listing row numbers.

2. **Pre-check form submit:**
   - Query by `tech_name` (normalized) if `tech_id` is new: if another row owns that name, `st.warning` / block with “Name already assigned to `tech_id` X.”

3. **Catch `IntegrityError`** around `merge` / `upsert` in the UI layer and map **`uq_technicians_tech_name`** to a short operator message.

4. **Document operator rule:** One row per person; **`tech_id`** is the stable key; **`tech_name`** must match the schedule export and must be unique in the DB.

5. **Tests:** SQLite/Postgres tests for duplicate `tech_name` on second insert; CSV parser tests for duplicate keys in-file.

All of this stays **behind** the existing boundaries: parsing in **`core/csv_parsing`**, persistence in **`db/tech_repository.py`**, orchestration messages in **`ui/technicians_panel.py`**.

---

## 7. File map (quick reference)

| Concern | File(s) |
|---------|---------|
| UI (tabs, buttons) | [`src/auto_assign/ui/technicians_panel.py`](../src/auto_assign/ui/technicians_panel.py) |
| CSV → `Tech` | [`src/auto_assign/core/csv_parsing/parse_tech_profiles.py`](../src/auto_assign/core/csv_parsing/parse_tech_profiles.py) |
| Upsert / merge | [`src/auto_assign/db/tech_repository.py`](../src/auto_assign/db/tech_repository.py) |
| ORM + constraints | [`src/auto_assign/db/models/technician.py`](../src/auto_assign/db/models/technician.py) |
| Load for assignment scoring | [`src/auto_assign/db/scheduling_repository.py`](../src/auto_assign/db/scheduling_repository.py) (`load_tech_profiles_by_name`) |
| Broader persistence story | [`docs/persistence_database.md`](persistence_database.md), [`docs/architecture_overview.md`](architecture_overview.md) |

---

## 8. Summary

- **CSV** and **form** paths both produce **`Tech`** and persist via **`merge_technician_from_tech` / `upsert_technicians`** — already wired.
- **Uniqueness** is anchored on **`tech_id` (PK)** and **`tech_name` (unique)**; upsert prevents duplicate **rows for the same id**; conflicting **names across ids** are rejected by the DB.
- To make the product feel bulletproof, add **validation and error messaging** in the UI/parser layer as in §6, without changing the greedy assignment or draft/confirm pipeline.
