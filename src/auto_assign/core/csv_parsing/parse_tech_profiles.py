'''
Load technician profile CSVs into validated domain ``Tech`` instances.

Expected columns (header row, snake_case):

- **Required:** ``tech_id``, ``tech_name``, ``daily_preference``
- **Optional:** ``favorites``, ``dislikes`` — semicolon-separated task names
  (comma also accepted if no semicolons present). Each list is validated: names must match
  ``task_config`` tasks, no duplicates within a list, no task in both lists, at most three
  per list (see ``validate_tech_preference_lists``).

'''
from __future__ import annotations

from typing import BinaryIO

import pandas as pd

from auto_assign.core.task_management.validate_tech_preferences import validate_tech_preference_lists
from auto_assign.domain.entities import Tech
from auto_assign.domain.enums import DailyPreference

TECH_REQUIRED_COLUMNS = [
    'tech_id',
    'tech_name',
    'daily_preference',
]


def load_tech_profile_csv(file_obj: BinaryIO) -> pd.DataFrame:
    try:
        return pd.read_csv(file_obj).copy()
    except Exception as e:
        raise ValueError(f'Error loading tech profile CSV: {e}') from e


def _strip_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip() for c in out.columns]
    return out


def _check_required_columns(df: pd.DataFrame) -> None:
    missing = [c for c in TECH_REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f'Tech profile CSV missing required columns: {missing}')


def _cell_str(raw: object) -> str:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return ''
    return str(raw).strip()


def task_names_from_form_field(text: str) -> list[str]:
    '''Parse a semicolon- or comma-separated favorites/dislikes line from a UI form.'''
    return _split_task_list(text)


def _split_task_list(raw: object) -> list[str]:
    s = _cell_str(raw)
    if not s:
        return []
    if ';' in s:
        return [p.strip() for p in s.split(';') if p.strip()]
    return [p.strip() for p in s.split(',') if p.strip()]


def _parse_daily_preference(raw: object) -> DailyPreference:
    s = _cell_str(raw).lower().replace(' ', '_').replace('-', '_')
    if not s:
        raise ValueError('daily_preference cannot be empty')
    for e in DailyPreference:
        if s == e.value or s == e.name.lower():
            return e
    allowed = ', '.join(f'{e.name} ({e.value})' for e in DailyPreference)
    raise ValueError(f'Invalid daily_preference {raw!r}. Use one of: {allowed}')


def parse_tech_profiles(df: pd.DataFrame) -> list[Tech]:
    '''
    Validate headers and parse each row into ``Tech`` (domain validation in ``Tech.__post_init__``).
    '''
    df = _strip_columns(df)
    _check_required_columns(df)
    if df.empty:
        raise ValueError('Tech profile CSV has no data rows')

    rows: list[Tech] = []
    for i, rec in enumerate(df.to_dict(orient='records'), start=2):
        try:
            fav_col = rec.get('favorites', '')
            dis_col = rec.get('dislikes', '')
            fav_list, dis_list = validate_tech_preference_lists(
                _split_task_list(fav_col),
                _split_task_list(dis_col),
            )
            rows.append(
                Tech(
                    tech_id=_cell_str(rec['tech_id']),
                    tech_name=_cell_str(rec['tech_name']),
                    daily_preference=_parse_daily_preference(rec['daily_preference']),
                    favorites=fav_list,
                    dislikes=dis_list,
                )
            )
        except Exception as e:
            raise ValueError(f'Error parsing tech profile row {i} (spreadsheet row): {e}') from e
    return rows
