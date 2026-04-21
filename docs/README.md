# Auto Assign — documentation index

**Auto Assign** is a Streamlit app that takes a shift's task list (from CSV) plus the technicians you've stored in the database and produces a scored **draft** assignment — who should do what — which you can review, edit, and then **confirm** to lock it in as history. Fairness and workload balancing are always computed from confirmed history only, so regenerating a draft never distorts the scoring.

This folder holds the design, operator, and evaluation docs. Use the table below to pick a reading path that matches what you're trying to do, or skim the one-liners further down to decide whether a specific doc is worth opening.

---

## Start here depending on you

| If you are… | Read in this order |
|-------------|--------------------|
| **Browsing the repo for the first time**  | Root [`README.md`](../README.md) → [`assignment_algorithm.md`](assignment_algorithm.md) → [`architecture_overview.md`](architecture_overview.md) → [`greedy_scoring_policy_and_simulation.md`](greedy_scoring_policy_and_simulation.md) |
| **Installing and running the app** (operator, new dev setting it up) | [`operator_runbook.md`](operator_runbook.md) → [`seed_demo_data.md`](seed_demo_data.md) → [`csv_contract.md`](csv_contract.md) → [`proficiency_rubric.md`](proficiency_rubric.md) |
| **Changing code or extending the system** (contributor) | [`architecture_overview.md`](architecture_overview.md) → [`persistence_database.md`](persistence_database.md) → [`technician_profiles_ingestion.md`](technician_profiles_ingestion.md) → [`../REPO_CONTEXT.md`](../REPO_CONTEXT.md) |
| **Evaluating the algorithm** (reviewer, benchmark reader) | [`greedy_scoring_policy_and_simulation.md`](greedy_scoring_policy_and_simulation.md) → [`greedy_scoring_paired_benchmark_report.md`](greedy_scoring_paired_benchmark_report.md) |
| **Deploying the hosted demo** (portfolio reviewer, future ops) | [`deployment.md`](deployment.md) → [`persistence_database.md`](persistence_database.md) → [`seed_demo_data.md`](seed_demo_data.md) |

---

## Every doc in one table

| Doc | One-line description |
|-----|----------------------|
| [`operator_runbook.md`](operator_runbook.md) | How to install, migrate, import technicians, generate a draft, and confirm it. Includes the errors you may hit and how to fix them. |
| [`seed_demo_data.md`](seed_demo_data.md) | One-click "Load demo data" path: 18 technicians, a 6-task catalog, and 14 days of confirmed history so the scheduler has something to work with on the first click. |
| [`csv_contract.md`](csv_contract.md) | Every CSV the app reads or writes: required columns, allowed enum values, and the shape of each export. |
| [`proficiency_rubric.md`](proficiency_rubric.md) | How to rate each technician's combined speed-and-quality proficiency per task, and why eligibility is a separate yes/no decision. |
| [`technician_profiles_ingestion.md`](technician_profiles_ingestion.md) | How technician profiles enter the system (CSV or form), become `Tech` objects, and stay de-duplicated across both paths. |
| [`assignment_algorithm.md`](assignment_algorithm.md) | How each task slot gets its technician: the compatibility score, the greedy placement loop, the exact solve for small pools, and the pairwise swap post-pass. |
| [`persistence_database.md`](persistence_database.md) | How assignments live in Postgres: the editable draft vs confirmed history split, and the full schema behind it. |
| [`architecture_overview.md`](architecture_overview.md) | How the whole app fits together — algorithm, domain types, database, and UI — with a system diagram and a file-level map. Best read after the algorithm and schema docs. |
| [`greedy_scoring_policy_and_simulation.md`](greedy_scoring_policy_and_simulation.md) | How the scorer is tuned (which knobs balance fairness vs preference vs proficiency) and how to run offline simulations on synthetic schedules to evaluate changes. |
| [`greedy_scoring_paired_benchmark_report.md`](greedy_scoring_paired_benchmark_report.md) | Dated snapshot of one baseline-vs-improved simulation run; regenerate when weights or policy change so the numbers don't drift. |
| [`deployment.md`](deployment.md) | How the hosted demo is wired up: Streamlit Community Cloud + managed Postgres on Supabase, the `DATABASE_URL` config model, which pooler URL to use for migrations vs runtime, and the shipping workflow for schema changes. |

---

## How the docs fit together

- **Concept layer** → `assignment_algorithm.md` (what the scorer does), `persistence_database.md` §0 (draft vs confirmed).
- **Schema layer** → `persistence_database.md` (tables, indexes, overrides).
- **Integration layer** → `architecture_overview.md` (how algorithm + schema + UI wire up).
- **Operator layer** → `operator_runbook.md`, `seed_demo_data.md`, `csv_contract.md`, `proficiency_rubric.md`.
- **Evaluation layer** → `greedy_scoring_policy_and_simulation.md` + `greedy_scoring_paired_benchmark_report.md`.
- **Deployment layer** → `deployment.md` (hosted demo on Streamlit Community Cloud + managed Postgres).
