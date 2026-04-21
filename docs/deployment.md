# Deployment

How the hosted demo of Auto Assign is wired up: where the app runs, where the database lives, and how the same codebase serves both local development and production without code changes.

---

## Stack summary

| Layer | Choice | Notes |
|-------|--------|-------|
| **App host** | Streamlit Community Cloud | Free, GitHub-integrated, runs the long-lived Streamlit server natively. Redeploys on `git push` to the tracked branch. |
| **Database** | Managed PostgreSQL on Supabase | Free-tier Postgres with TLS and connection pooling. The app uses standard SQLAlchemy + psycopg v3 — there is no Supabase SDK dependency, so any managed Postgres would work. |
| **Schema migrations** | Alembic, run from a developer laptop | Migrations are versioned files under `alembic/versions/`. A one-shot `alembic upgrade head` pointed at the production DB brings it up to the latest schema. |
| **Config** | `DATABASE_URL` environment variable | Resolved at startup in [`src/auto_assign/db/session.py`](../src/auto_assign/db/session.py). In development it's read from `.env`; in production it's injected by Streamlit Community Cloud's **Secrets** panel. |

---

## Why this combination

- **Streamlit Community Cloud over serverless platforms**. Streamlit runs a persistent WebSocket server per session; serverless platforms (Vercel, Lambda) don't fit that model. Streamlit Community Cloud is purpose-built for it and redeploys on `git push`.
- **Managed Postgres over self-hosted**. Backups, TLS, and monitoring come for free and don't add differentiating value for a portfolio project.
- **Supabase specifically, but swappable**. The only coupling to the provider is the `DATABASE_URL` string. Moving to Neon, RDS, or a self-hosted Postgres is a configuration change, not a code change.
- **Migrations from a laptop, not on app boot**. Running `alembic upgrade head` at startup would add cold-start latency and muddy error reporting when a migration fails. For a low-deploy-frequency portfolio app, applying migrations manually when a new one lands is simpler and safer.

---

## Supabase connection strings

Supabase exposes three URLs for the same database. Use them for different jobs:

| URL type | Host / port | When to use | Why |
|----------|-------------|-------------|-----|
| **Direct connection** | `db.<project>.supabase.co:5432` | Rare — one-off DBA tasks. | Default connection limit; not built for many clients. |
| **Session pooler** | `<region>.pooler.supabase.com:5432` | `alembic upgrade head`. | Preserves session state; prepared statements and multi-statement transactions work correctly. |
| **Transaction pooler** | `<region>.pooler.supabase.com:6543` | Live app runtime (goes into Streamlit secrets). | Resets between statements; ideal for the app's short transactional queries. **Not** safe for Alembic. |

Always append `?sslmode=require` — Supabase enforces TLS.

---

## Deploying from scratch

Assuming a fresh Supabase project and a Streamlit Community Cloud account:

1. **Provision the cloud DB**. In Supabase, create a new project. From Project Settings → Database → Connection string, copy the **session pooler** and **transaction pooler** URLs.
2. **Apply migrations** from your laptop, one-shot, without persisting the URL in `.env`:
   ```bash
   DATABASE_URL="<session-pooler-url>?sslmode=require" uv run alembic upgrade head
   ```
3. **Seed demo data** (optional; recommended for the hosted demo). Run the app locally but point it at Supabase for a single session:
   ```bash
   DATABASE_URL="<transaction-pooler-url>?sslmode=require" uv run streamlit run app.py
   ```
   Click **Load demo data** on the Home page, confirm success, then stop the local server. See [seed_demo_data.md](seed_demo_data.md) for what gets written.
4. **Deploy the app**. Push the repo to GitHub, then on [share.streamlit.io](https://share.streamlit.io):
   - Create an app pointing at `app.py` on the `main` branch.
   - Under **Advanced settings → Secrets**, paste:
     ```toml
     DATABASE_URL = "<transaction-pooler-url>?sslmode=require"
     ```
   - Deploy. First build takes a couple of minutes; subsequent `git push`es redeploy in under a minute.
5. **Verify**. The hosted URL should render the Home page with the seeded demo data visible.

---

## Shipping a schema change

1. Land the migration file under `alembic/versions/` on `main`.
2. From your laptop, one-shot against the session pooler:
   ```bash
   DATABASE_URL="<session-pooler-url>?sslmode=require" uv run alembic upgrade head
   ```
3. `git push` — Streamlit Community Cloud auto-redeploys. No further action.

If you ship the code before the migration, the deployed app will raise `UndefinedColumn` / `UndefinedTable` errors until step 2 runs. Order matters.

---

## Local development is unchanged

Keep your local `.env` pointing at local Postgres via either `DATABASE_URL=postgresql+psycopg://…@localhost:5432/auto_assign` or the discrete `POSTGRES_*` variables (see [operator_runbook.md §2](operator_runbook.md)). Production uses its own `DATABASE_URL` injected by Streamlit secrets; the two environments never share state.

---

## Notes on the shared public demo

The hosted app is a single process writing to a single shared database. Worth knowing if you link a hiring manager or reviewer to it:

- Every visitor mutates the same rows. One visitor's **Publish** is immediately visible to the next.
- Re-clicking **Load demo data** is safe. The seeder upserts tasks and technicians by id and atomically replaces each `(date, time_slot)` slice of confirmed history, so it can be clicked repeatedly without corruption. It also re-anchors the 14-day past window on today.
- **Reset demo data** is destructive. It truncates all four tables. Recovery is a single click on **Load demo data**, but if you want a visitor-proof demo, gate or remove the Reset control before deploying.
- There are no per-user accounts; any per-user isolation would require adding an auth layer and partitioning writes by user.
