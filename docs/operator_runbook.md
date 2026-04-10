# Operator runbook

Short path from empty install to a **published** shift slice, plus common failures. Deep design: [assignment_algorithm.md](assignment_algorithm.md), [persistence_database.md](persistence_database.md).

---

## 1. Prerequisites

- Python **3.11+** and [uv](https://docs.astral.sh/uv/) (or install deps from `pyproject.toml` another way).
- **PostgreSQL** reachable from your machine.
- Repo root as working directory for all commands below.

---

## 2. Install and database URL

```bash
uv sync
cp .env.example .env
```

The `.env` file is **gitignored**; never commit credentials.

Edit `.env`: set **`DATABASE_URL`** (`postgresql+psycopg://…`) **or** `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, and optionally `POSTGRES_HOST`, `POSTGRES_PORT`. See comments in `.env.example` and `src/auto_assign/db/session.py`.

Create an empty database if needed (e.g. `createdb auto_assign`).

---

## 3. Migrations

```bash
uv run alembic upgrade head
```

Uses the **same** URL as the app ([alembic/README](../alembic/README)).

---

## 4. Run the app

```bash
uv run streamlit run app.py
```

Sidebar shows **Database ready** when URL resolution succeeds; otherwise configure `.env` and restart.

---

## 5. First-time data order

1. **Task Catalog** — Add every task name you will use in headcounts and in technician favorites/dislikes. Names are normalized when validated; stay consistent with [csv_contract.md](csv_contract.md).
2. **Technician Profiles** — Import CSV or use the form. Each schedule **`tech_name`** must match exactly one saved profile (after normalization, title case for schedule CSV).
3. **Home → Assignment Engine** — Upload schedule CSV, complete steps in order, **Generate draft**, then **Publish**.

**Schedule CSV** requirements: [csv_contract.md](csv_contract.md) §1.

---

## 6. Draft vs published

- **Draft** — Preview for one `(work_date, time_slot)`. Regenerate replaces **draft** rows for that slice only. Does **not** affect fairness / history scoring.
- **Publish** — Atomically replaces **draft + confirmed** for that slice with new **confirmed** rows. Re-publishing the same date/shift overwrites the prior official slice (the UI warns and may require a checkbox).

**Assignment history** lists **confirmed** rows only.

---

## 7. Troubleshooting

| Symptom | What to check |
|---------|----------------|
| Sidebar: “No DATABASE_URL” / app says DB not configured | `.env` missing or incomplete; restart Streamlit after fixing. |
| `alembic upgrade` fails | Same URL as app; DB user can create tables; Postgres running. |
| Schedule upload error (columns / empty values) | Required columns and no blank cells — [csv_contract.md](csv_contract.md) §1. |
| Tech CSV error on favorites/dislikes | Task names must exist in **Task Catalog**; max 3 each; no overlap between favorites and dislikes. |
| “No available dates found” | Dates in CSV must match `YYYY-MM-DD`; rows must exist for the workflow. |
| “number of task requests … not equal to the number of available techs” | Headcounts must sum to the **pool size** for that date/slot (after call-offs and availability flags). Adjust counts or overrides. |
| “Cannot save draft: … tech_id … not in the database” | Every assigned id must exist in `technicians`. Import profiles so **schedule names** map to real `tech_id`s (unmapped names get synthetic ids that are not FK-safe). |
| “Cannot confirm … Missing: … tech_id” | Same as above — fix technician records before **Publish**. |
| Call-off ignored? | `staffing_status` must be `call_off` for that person’s **row on that date**; call-offs exclude from pool for **all** slots that day in code. |

---

## 8. Optional: benchmark script

From repo root:

```bash
python scripts/run_greedy_simulation.py --mode paired
```

Details: [greedy_scoring_policy_and_simulation.md](greedy_scoring_policy_and_simulation.md).

---

## 9. Maintainer map

For a file-by-file overview, see [REPO_CONTEXT.md](../REPO_CONTEXT.md) in the repo root.
