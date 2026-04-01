'''Tests for schedule DataFrame validation and column standardization.'''

import pandas as pd
import pytest

from auto_assign.core.csv_parsing.validate_schedule import (
    REQUIRED_COLUMNS,
    _check_required_columns_exist,
    _ensure_not_empty,
    standardize_schedule_column_names,
)


class TestStandardizeScheduleColumnNames:
    def test_strips_column_whitespace(self) -> None:
        df = pd.DataFrame(columns=['  tech_name  ', ' date '])
        out = standardize_schedule_column_names(df)
        assert list(out.columns) == ['tech_name', 'date']

    def test_renames_legacy_camel_case_headers_when_snake_missing(self) -> None:
        df = pd.DataFrame(
            columns=['tech_name', 'date', 'availableAM', 'availableMID', 'availablePM']
        )
        out = standardize_schedule_column_names(df)
        assert list(out.columns) == [
            'tech_name',
            'date',
            'available_AM',
            'available_MID',
            'available_PM',
        ]

    def test_does_not_rename_when_snake_already_present(self) -> None:
        '''If ``available_AM`` exists, keep ``availableAM`` as separate column (no collision rename).'''
        df = pd.DataFrame(
            columns=['tech_name', 'date', 'availableAM', 'available_AM', 'available_MID', 'available_PM']
        )
        out = standardize_schedule_column_names(df)
        assert 'availableAM' in out.columns
        assert 'available_AM' in out.columns

    def test_non_string_column_labels_coerced(self) -> None:
        df = pd.DataFrame(columns=[123, 'date'])
        out = standardize_schedule_column_names(df)
        assert list(out.columns) == ['123', 'date']


class TestCheckRequiredColumnsExist:
    def test_all_present_no_op(self) -> None:
        df = pd.DataFrame(columns=REQUIRED_COLUMNS)
        _check_required_columns_exist(df)

    def test_missing_one_column_lists_it(self) -> None:
        df = pd.DataFrame(columns=['tech_name', 'date', 'available_AM', 'available_MID'])
        with pytest.raises(ValueError, match='missing') as exc:
            _check_required_columns_exist(df)
        assert 'available_PM' in str(exc.value)

    def test_missing_multiple_columns(self) -> None:
        df = pd.DataFrame(columns=['tech_name'])
        with pytest.raises(ValueError) as exc:
            _check_required_columns_exist(df)
        msg = str(exc.value)
        assert 'date' in msg and 'available_AM' in msg


class TestEnsureNotEmpty:
    def test_no_na_passes(self) -> None:
        df = pd.DataFrame({'tech_name': ['a', 'b']})
        _ensure_not_empty(df, 'tech_name')

    def test_any_na_raises(self) -> None:
        df = pd.DataFrame({'tech_name': ['a', None]})
        with pytest.raises(ValueError, match='empty values'):
            _ensure_not_empty(df, 'tech_name')

    def test_nat_in_datetime_column_raises(self) -> None:
        df = pd.DataFrame({'date': pd.to_datetime(['2026-01-01', pd.NaT])})
        with pytest.raises(ValueError, match='empty values'):
            _ensure_not_empty(df, 'date')
