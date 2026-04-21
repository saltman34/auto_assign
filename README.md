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
| **Technician Profiles** | CSV import or form; stable `tech_id`, display `tech_name` (must match schedule CSV names); per-task **eligibility** (hard gate) and **proficiency** on the form ([`docs/proficiency_rubric.md`](docs/proficiency_rubric.md)). |
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

Start at [`docs/README.md`](docs/README.md) — it groups docs by audience (stranger / operator / contributor / evaluator) and lists every file with a one-line purpose.

| Document | Contents |
|----------|----------|
| [`docs/README.md`](docs/README.md) | **Index**: audience-based map of every doc in this folder. |
| [`docs/operator_runbook.md`](docs/operator_runbook.md) | Install → migrate → first publish; troubleshooting table. |
| [`docs/csv_contract.md`](docs/csv_contract.md) | Reference: schedule and tech CSV columns, enums, exports. |
| [`docs/assignment_algorithm.md`](docs/assignment_algorithm.md) | Greedy procedure, scoring terms, tie handling (concept). |
| [`docs/proficiency_rubric.md`](docs/proficiency_rubric.md) | Manager rubric for per-task eligibility and proficiency ordinals. |
| [`docs/persistence_database.md`](docs/persistence_database.md) | Draft/confirmed concept, tables, indexes, overrides. |
| [`docs/architecture_overview.md`](docs/architecture_overview.md) | End-to-end narrative tying algorithm → schema → UI, with system diagram. |
| [`docs/technician_profiles_ingestion.md`](docs/technician_profiles_ingestion.md) | Profile lifecycle: CSV vs form, uniqueness, name alignment. |
| [`docs/greedy_scoring_policy_and_simulation.md`](docs/greedy_scoring_policy_and_simulation.md) | **Living** guide: default greedy policy flags, fairness lookback, how to run benchmarks (see section below). |
| [`docs/greedy_scoring_paired_benchmark_report.md`](docs/greedy_scoring_paired_benchmark_report.md) | **Snapshot** of one paired benchmark run (full table + narrative); optional read unless you want dated evidence in-repo. |
| [`docs/seed_demo_data.md`](docs/seed_demo_data.md) | One-click "Load demo data" path: 18 technicians, a 6-task catalog, and 14 days of confirmed history for the fastest route to a working draft. |
| [`alembic/README`](alembic/README) | Common Alembic commands. |
| [`.env.example`](.env.example) | Environment variable template (no secrets). |

### Greedy scoring benchmarks (offline CLI)

These are **not** the Streamlit app: they use **synthetic** crews and tasks from `simulation.py` to stress the assigner and print tables to the terminal (no Postgres).

| Artifact | What it is for |
|----------|----------------|
| [`scripts/run_greedy_simulation.py`](scripts/run_greedy_simulation.py) | **How you reproduce numbers.** `--mode paired` (**default**): same random scenarios run twice—once with a deliberately minimal baseline policy, once with **current production defaults**—so score/optimality deltas are apples-to-apples. `--mode sanity`: runs **only** the current defaults (simpler table, less work); use for a quick smoke check. Optional: `--scenario-count`, `--seed`, `--fairness-lookback-days`. |
| [`docs/greedy_scoring_policy_and_simulation.md`](docs/greedy_scoring_policy_and_simulation.md) | **What the defaults mean**, why fairness lookback is 14 days, summary deltas, and the same CLI examples—read this before the frozen report. |
| [`docs/greedy_scoring_paired_benchmark_report.md`](docs/greedy_scoring_paired_benchmark_report.md) | A **dated paste** of one `paired` run (per-scenario table + interpretation). It can go **stale** if you change `ScoringWeights`, `GreedyOptimizationConfig`, or scenario generation—re-run the script and update this file if you rely on it for PRs or hiring collateral. |

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
