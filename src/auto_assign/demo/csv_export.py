'''Regenerate the checked-in ``data/*.csv`` sample files from the demo fixtures.

The in-app seed button uses ``date.today()`` so the demo always feels current,
but the CSV fixtures need **absolute, stable dates** so unit tests do not
become time-dependent. This module is the bridge: it emits schedule + tech
profile CSVs at a pinned anchor date.

Only the columns currently supported by the CSV contracts
(``docs/csv_contract.md``) are written — eligibility and proficiency are
database-only today.
'''
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from auto_assign.demo.fixtures import DEMO_TECHS, build_demo_schedule_rows

SAMPLE_ANCHOR_DATE = date(2026, 6, 1)
'''Absolute start date used for all CSV fixtures so tests are reproducible.'''

SAMPLE_DAYS = 21
SAMPLE_SEED = 20260601
'''Independent seed for CSV fixtures (distinct from the runtime demo seed).'''


def write_sample_csvs(
    data_dir: Path | str = 'data',
    *,
    anchor_date: date = SAMPLE_ANCHOR_DATE,
    num_days: int = SAMPLE_DAYS,
    seed: int = SAMPLE_SEED,
) -> tuple[Path, Path]:
    '''Write ``sample_schedule.csv`` and ``sample_tech_profiles.csv`` into ``data_dir``.

    Returns the two paths written, in order.
    '''
    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)

    schedule_path = data_path / 'sample_schedule.csv'
    profiles_path = data_path / 'sample_tech_profiles.csv'

    _write_schedule_csv(
        schedule_path,
        anchor_date=anchor_date,
        num_days=num_days,
        seed=seed,
    )
    _write_tech_profiles_csv(profiles_path)
    return schedule_path, profiles_path


def _write_schedule_csv(
    path: Path,
    *,
    anchor_date: date,
    num_days: int,
    seed: int,
) -> None:
    rows = build_demo_schedule_rows(
        start_date=anchor_date,
        num_days=num_days,
        seed=seed,
    )
    with path.open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                'tech_name',
                'date',
                'available_AM',
                'available_MID',
                'available_PM',
                'staffing_status',
            ]
        )
        for r in rows:
            writer.writerow(
                [
                    r.tech_name,
                    r.work_date.isoformat(),
                    int(r.available_AM),
                    int(r.available_MID),
                    int(r.available_PM),
                    r.staffing_status.value,
                ]
            )


def _write_tech_profiles_csv(path: Path) -> None:
    with path.open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(
            ['tech_id', 'tech_name', 'daily_preference', 'favorites', 'dislikes']
        )
        for spec in DEMO_TECHS:
            writer.writerow(
                [
                    spec.tech_id,
                    spec.tech_name,
                    spec.daily_preference.value,
                    '; '.join(spec.favorites),
                    '; '.join(spec.dislikes),
                ]
            )
