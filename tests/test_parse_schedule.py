'''Tests for loading and parsing schedule CSVs into ``ScheduleRow`` lists.'''

from datetime import date
from io import BytesIO

import pandas as pd
import pytest

from auto_assign.core.csv_parsing.parse_schedule import load_schedule, parse_schedule
from auto_assign.ingestion import ScheduleRow


def _minimal_valid_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            'tech_name': ['alex'],
            'date': ['2026-03-30'],
            'available_AM': [1],
            'available_MID': [0],
            'available_PM': ['yes'],
        }
    )


def test_parse_schedule_minimal_row() -> None:
    rows = parse_schedule(_minimal_valid_df())
    assert len(rows) == 1
    r = rows[0]
    assert r.tech_name == 'Alex'
    assert r.work_date == date(2026, 3, 30)
    assert r.available_AM is True
    assert r.available_MID is False
    assert r.available_PM is True


def test_parse_schedule_legacy_camel_case_availability_headers() -> None:
    df = pd.DataFrame(
        {
            'tech_name': ['b'],
            'date': ['2026-01-02'],
            'availableAM': [0],
            'availableMID': [1],
            'availablePM': [0],
        }
    )
    rows = parse_schedule(df)
    assert rows[0].available_AM is False
    assert rows[0].available_MID is True
    assert rows[0].available_PM is False


def test_parse_schedule_column_names_with_leading_trailing_spaces() -> None:
    df = pd.DataFrame(
        {
            ' tech_name ': ['c'],
            'date': ['2026-01-03'],
            'available_AM': [1],
            'available_MID': [1],
            'available_PM': [1],
        }
    )
    rows = parse_schedule(df)
    assert rows[0].tech_name == 'C'


def test_parse_schedule_empty_dataframe_returns_empty_list() -> None:
    df = pd.DataFrame(columns=pd.Index(['tech_name', 'date', 'available_AM', 'available_MID', 'available_PM']))
    assert parse_schedule(df) == []


def test_parse_schedule_missing_required_column_raises() -> None:
    df = pd.DataFrame({'tech_name': ['a'], 'date': ['2026-01-01']})
    with pytest.raises(ValueError, match='missing'):
        parse_schedule(df)


def test_parse_schedule_na_in_tech_name_raises() -> None:
    df = _minimal_valid_df()
    df.loc[0, 'tech_name'] = None
    with pytest.raises(ValueError, match='empty values'):
        parse_schedule(df)


def test_parse_schedule_invalid_date_raises() -> None:
    df = _minimal_valid_df()
    df.loc[0, 'date'] = 'not-a-date'
    with pytest.raises(ValueError, match='Invalid date format'):
        parse_schedule(df)


def test_parse_schedule_empty_tech_after_normalize_raises_from_schedule_row() -> None:
    '''Whitespace-only name becomes ""; ``ScheduleRow`` rejects empty string.'''
    df = _minimal_valid_df()
    df.loc[0, 'tech_name'] = '   '
    with pytest.raises(ValueError, match='empty'):
        parse_schedule(df)


def test_parse_schedule_multiple_rows_order_preserved() -> None:
    df = pd.DataFrame(
        {
            'tech_name': ['zoe', 'amy'],
            'date': ['2026-02-01', '2026-02-01'],
            'available_AM': [1, 1],
            'available_MID': [1, 1],
            'available_PM': [1, 1],
        }
    )
    rows = parse_schedule(df)
    assert [r.tech_name for r in rows] == ['Zoe', 'Amy']


def test_load_schedule_reads_csv_bytes() -> None:
    raw = b'tech_name,date,available_AM,available_MID,available_PM\nPat,2026-04-01,1,0,1\n'
    df = load_schedule(BytesIO(raw))
    assert len(df) == 1
    assert df['tech_name'].iloc[0] == 'Pat'


def test_load_schedule_invalid_bytes_raises_value_error() -> None:
    with pytest.raises(ValueError, match='Error loading'):
        load_schedule(BytesIO(b'not,csv,\x00\xff'))


def test_parse_schedule_sample_project_csv() -> None:
    '''Integration-style check against bundled sample data.'''
    df = pd.read_csv('data/sample_schedule.csv')
    rows = parse_schedule(df)
    assert len(rows) >= 1
    assert all(isinstance(r, ScheduleRow) for r in rows)
