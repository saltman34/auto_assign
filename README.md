# Auto Assign

Streamlit app that generates **draft** shift task assignments from a schedule CSV, technician preferences, and a **greedy compatibility scorer**, then **publishes** confirmed rows to PostgreSQL. Scoring uses **confirmed** history only; drafts are scratch space until publish.

**Stack:** Python 3.11+, Streamlit, SQLAlchemy 2, Alembic, PostgreSQL (psycopg v3), pandas.

---

## Quick start

1. **Install** (from repo root; [uv](https://docs.astral.sh/uv/) matches `uv.lock`):

   ```bash
   uv sync
   ```

2. **Configure the database** — copy [`.env.example`](.env.example) to `.env` beside `pyproject.toml` (`.env` is gitignored), then set either:

   - `DATABASE_URL` (prefer `postgresql+psycopg://…`), or  
   - `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, and optionally `POSTGRES_HOST`, `POSTGRES_PORT`.

   Bare `postgresql://` URLs are rewritten to use psycopg v3. Details: `src/auto_assign/db/session.py`.

3. **Migrate:**

   ```bash
   uv run alembic upgrade head
   ```

   Alembic uses the same URL as the app ([`alembic/README`](alembic/README)).

4. **Run the UI:**

   ```bash
   uv run streamlit run app.py
   ```

Step-by-step onboarding and troubleshooting: **[`docs/operator_runbook.md`](docs/operator_runbook.md)**.

---

## Using the app

| Area | Purpose |
|------|---------|
| **Home** | Upload schedule CSV, pick date and shift (AM / MID / PM), set task headcounts, optional manual rows, **Generate** draft, **Publish** (confirm) or discard. |
| **Technician Profiles** | CSV import or form; stable `tech_id`, display `tech_name` (must match schedule CSV names). |
| **Task Catalog** | Persisted tasks and default headcounts for the engine. |
| **Assignment history** | Published (confirmed) assignments; audit / export. |
| **About this app** | In-app overview of behavior. |

Sample CSV shapes: `data/sample_schedule.csv`, `data/sample_tech_profiles.csv`. **Column rules:** [`docs/csv_contract.md`](docs/csv_contract.md).

---

## Repository layout

| Path | Role |
|------|------|
| `app.py` | Streamlit entrypoint. |
| `src/auto_assign/` | UI, assignment engine, CSV parsing, domain types, DB models and repositories. |
| `alembic/` | Schema migrations. |
| `tests/` | `pytest` suite (`pythonpath` includes `src`). |
| `scripts/run_greedy_simulation.py` | Greedy policy benchmarks (see docs below). |
| [`REPO_CONTEXT.md`](REPO_CONTEXT.md) | Maintainer / agent map of the codebase (updated with the doc refresh). |

---

## Documentation

| Document | Contents |
|----------|----------|
| [`docs/operator_runbook.md`](docs/operator_runbook.md) | Install → migrate → first publish; troubleshooting table. |
| [`docs/csv_contract.md`](docs/csv_contract.md) | Schedule and tech CSV columns, enums, exports. |
| [`docs/assignment_algorithm.md`](docs/assignment_algorithm.md) | Greedy procedure, scoring terms, draft vs confirmed slices. |
| [`docs/persistence_database.md`](docs/persistence_database.md) | Tables, indexes, overrides. |
| [`docs/assignment_persistence_feature_summary.md`](docs/assignment_persistence_feature_summary.md) | UI ↔ services ↔ DB implementation summary. |
| [`docs/technician_profiles_ingestion.md`](docs/technician_profiles_ingestion.md) | CSV vs form, uniqueness, name alignment. |
| [`docs/greedy_scoring_policy_and_simulation.md`](docs/greedy_scoring_policy_and_simulation.md) | Default `GreedyOptimizationConfig`, running simulations. |
| [`docs/greedy_scoring_paired_benchmark_report.md`](docs/greedy_scoring_paired_benchmark_report.md) | Fixed-scenario benchmark numbers. |
| [`docs/examples/sample_task_list.yaml`](docs/examples/sample_task_list.yaml) | Illustrative task list only (app uses DB Task Catalog). |
| [`alembic/README`](alembic/README) | Common Alembic commands. |
| [`.env.example`](.env.example) | Environment variable template (no secrets). |

---

## Development

```bash
uv run pytest
uv run ruff check .
```

---

## Further documentation (optional)

- **API / HTTP layer** — not present today; if added, a small OpenAPI or ADR would complement the persistence docs.
- **Deployment** — no container or platform guide in-repo; add when you standardize hosting (Streamlit Cloud, internal k8s, etc.).
