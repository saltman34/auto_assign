'''Demo-data seeder for portfolio demos and local development.

Public entry points:

- ``seed_demo_data(session, *, today, seed)`` — populate tasks, technicians, and
  14 days of confirmed assignment history relative to ``today``.
- ``reset_demo_data(session)`` — truncate tasks, technicians, and every assignment
  row so the DB is back to an empty schema.
- ``write_sample_csvs(data_dir)`` — regenerate the checked-in ``data/*.csv``
  fixtures from the same fixture data the seeder uses.

See ``docs/seed_demo_data.md`` for the full dataset description.
'''
from auto_assign.demo.csv_export import write_sample_csvs
from auto_assign.demo.fixtures import (
    DEMO_TASKS,
    DEMO_TECHS,
    DemoTaskSpec,
    DemoTechSpec,
    build_demo_schedule_rows,
)
from auto_assign.demo.seed import reset_demo_data, seed_demo_data

__all__ = [
    'DEMO_TASKS',
    'DEMO_TECHS',
    'DemoTaskSpec',
    'DemoTechSpec',
    'build_demo_schedule_rows',
    'reset_demo_data',
    'seed_demo_data',
    'write_sample_csvs',
]
