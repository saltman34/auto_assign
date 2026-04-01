import pandas as pd
from typing import BinaryIO

from auto_assign.ingestion import ScheduleRow
from .validate_schedule import (
    _check_required_columns_exist,
    _ensure_not_empty,
    REQUIRED_COLUMNS,
    standardize_schedule_column_names,
)
from .normalize_schedule import _normalize_tech_name, _normalize_date, _normalize_available


def load_schedule(file_obj: BinaryIO) -> pd.DataFrame:
    '''
    Load a schedule CSV into a DataFrame (raw; use parse_schedule for ScheduleRow list).
    '''
    try:
        df = pd.read_csv(file_obj)
        return df.copy()
    except Exception as e:
        raise ValueError(f"Error loading the schedule CSV file: {e}") from e


_AVAILABILITY_COLUMNS = ('available_AM', 'available_MID', 'available_PM')


def parse_schedule(df: pd.DataFrame) -> list[ScheduleRow]:
    '''
    Validate and parse a schedule DataFrame into ``ScheduleRow`` instances.

    Required columns: ``tech_name``, ``date``, ``available_AM``, ``available_MID``,
    ``available_PM``. The ``date`` column becomes ``work_date`` on each row.
    ``standardize_schedule_column_names`` may rewrite legacy availability headers
    before validation (see that function); the **standard** file format uses the
    snake_case names above.
    '''
    df = standardize_schedule_column_names(df)
    _check_required_columns_exist(df, REQUIRED_COLUMNS)
    _ensure_not_empty(df, 'tech_name')
    _ensure_not_empty(df, 'date')
    for col in _AVAILABILITY_COLUMNS:
        _ensure_not_empty(df, col)

    df = df.copy()
    df['tech_name'] = df['tech_name'].apply(_normalize_tech_name)
    df['date'] = df['date'].apply(_normalize_date)
    for col in _AVAILABILITY_COLUMNS:
        df[col] = df[col].apply(_normalize_available)

    rows: list[ScheduleRow] = []
    for rec in df.to_dict(orient='records'):
        rows.append(
            ScheduleRow(
                tech_name=rec['tech_name'],
                work_date=rec['date'],
                available_AM=rec['available_AM'],
                available_MID=rec['available_MID'],
                available_PM=rec['available_PM'],
            )
        )
    return rows
