#!/usr/bin/env python3
'''CLI for the demo dataset. Run from the repo root.

    python scripts/seed_demo_data.py seed
        Populate the configured database with tasks, 18 technicians, and 14 days
        of confirmed assignment history ending today. Uses ``DATABASE_URL``
        from the environment or the app's default session factory.

    python scripts/seed_demo_data.py reset
        Truncate all tasks, technicians, assignment rows, and override rows.
        Destructive. Intended for local dev only.

    python scripts/seed_demo_data.py regenerate-csvs
        Rewrite ``data/sample_schedule.csv`` and ``data/sample_tech_profiles.csv``
        from the same fixture data the seeder uses. Uses pinned absolute dates
        so the CSVs stay stable across runs.

Does not need ``PYTHONPATH`` — this prepends ``<repo>/src`` for imports.
'''
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / 'src'
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _cmd_seed() -> int:
    from auto_assign.db import session_scope  # noqa: E402
    from auto_assign.demo import seed_demo_data  # noqa: E402

    with session_scope() as session:
        result = seed_demo_data(session)

    print(
        f'Seeded demo data: '
        f'{result.tasks_created} tasks, '
        f'{result.technicians_upserted} technicians, '
        f'{result.past_days_confirmed} past days confirmed '
        f'({result.confirmed_assignments_written} assignments), '
        f'{len(result.future_schedule_rows)} future schedule rows available for upload.'
    )
    return 0


def _cmd_reset() -> int:
    from auto_assign.db import session_scope  # noqa: E402
    from auto_assign.demo import reset_demo_data  # noqa: E402

    with session_scope() as session:
        reset_demo_data(session)
    print('Reset complete. All tasks, technicians, assignments, and overrides deleted.')
    return 0


def _cmd_regenerate_csvs(data_dir: Path) -> int:
    from auto_assign.demo import write_sample_csvs  # noqa: E402

    schedule_path, profiles_path = write_sample_csvs(data_dir)
    print(f'Wrote {schedule_path}')
    print(f'Wrote {profiles_path}')
    return 0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Seed, reset, or regenerate demo data.')
    sub = p.add_subparsers(dest='command', required=True)

    sub.add_parser('seed', help='Populate database with demo dataset.')
    sub.add_parser('reset', help='Truncate all demo-related tables.')
    regen = sub.add_parser(
        'regenerate-csvs',
        help='Rewrite data/sample_*.csv from the fixtures.',
    )
    regen.add_argument(
        '--data-dir',
        default=str(_REPO_ROOT / 'data'),
        help='Directory to write CSVs into (default: <repo>/data).',
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    if args.command == 'seed':
        return _cmd_seed()
    if args.command == 'reset':
        return _cmd_reset()
    if args.command == 'regenerate-csvs':
        return _cmd_regenerate_csvs(Path(args.data_dir))
    raise AssertionError(f'Unhandled command: {args.command}')


if __name__ == '__main__':
    raise SystemExit(main())
