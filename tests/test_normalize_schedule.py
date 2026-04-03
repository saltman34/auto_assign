'''Tests for schedule cell normalization (tech name, date, availability).'''

from datetime import date, datetime

import numpy as np
import pytest

from auto_assign.core.csv_parsing.normalize_schedule import (
    AVAILABLE_VALUES,
    NOT_AVAILABLE_VALUES,
    _normalize_available,
    _normalize_date,
    _normalize_tech_name,
)


class TestNormalizeTechName:
    def test_strips_and_title_cases(self) -> None:
        assert _normalize_tech_name('  alex smith  ') == 'Alex Smith'

    def test_empty_string_allowed_by_normalizer(self) -> None:
        '''Downstream ``ScheduleRow`` rejects empty names; normalizer itself returns "".'''
        assert _normalize_tech_name('   ') == ''

    def test_tabs_and_newlines_stripped(self) -> None:
        assert _normalize_tech_name('\tjo\n') == 'Jo'


class TestNormalizeDate:
    def test_iso_string(self) -> None:
        assert _normalize_date('2026-03-30') == date(2026, 3, 30)

    def test_string_with_whitespace(self) -> None:
        assert _normalize_date('  2026-03-30  ') == date(2026, 3, 30)

    def test_date_instance_passthrough(self) -> None:
        d = date(2025, 1, 2)
        assert _normalize_date(d) is d

    def test_datetime_becomes_date(self) -> None:
        dt = datetime(2026, 7, 4, 15, 30, 0)
        assert _normalize_date(dt) == date(2026, 7, 4)

    def test_invalid_string_raises(self) -> None:
        with pytest.raises(ValueError, match='Invalid date format'):
            _normalize_date('03-30-2026')

    def test_unsupported_type_raises(self) -> None:
        with pytest.raises(ValueError, match='Invalid date type'):
            _normalize_date(20260330)


class TestNormalizeAvailable:
    def test_boolean_passthrough(self) -> None:
        assert _normalize_available(True) is True
        assert _normalize_available(False) is False

    def test_int_zero_one(self) -> None:
        assert _normalize_available(1) is True
        assert _normalize_available(0) is False

    def test_float_zero_one(self) -> None:
        assert _normalize_available(1.0) is True
        assert _normalize_available(0.0) is False

    @pytest.mark.parametrize(
        'true_s',
        [v.upper() for v in AVAILABLE_VALUES] + list(AVAILABLE_VALUES),
    )
    def test_string_truthy_variants(self, true_s: str) -> None:
        assert _normalize_available(true_s) is True

    @pytest.mark.parametrize('false_s', NOT_AVAILABLE_VALUES)
    def test_string_falsy_variants(self, false_s: str) -> None:
        assert _normalize_available(false_s) is False

    def test_string_whitespace_trimmed(self) -> None:
        assert _normalize_available('  YES  ') is True

    def test_numpy_int64(self) -> None:
        '''Pandas / numpy often surface int64 scalars outside ``Series.apply`` coercion.'''
        assert _normalize_available(np.int64(1)) is True
        assert _normalize_available(np.int64(0)) is False

    def test_numpy_float64(self) -> None:
        assert _normalize_available(np.float64(1.0)) is True
        assert _normalize_available(np.float64(0.0)) is False

    def test_none_raises(self) -> None:
        with pytest.raises(ValueError, match='None'):
            _normalize_available(None)

    def test_nan_raises(self) -> None:
        with pytest.raises(ValueError, match='NaN'):
            _normalize_available(float('nan'))

    def test_numpy_nan_raises(self) -> None:
        with pytest.raises(ValueError, match='NaN'):
            _normalize_available(np.nan)

    def test_numeric_other_than_zero_one_raises(self) -> None:
        with pytest.raises(ValueError, match='Invalid numeric availability'):
            _normalize_available(2)
        with pytest.raises(ValueError, match='Invalid numeric availability'):
            _normalize_available(0.5)

    def test_garbage_string_raises(self) -> None:
        with pytest.raises(ValueError, match='Invalid available value'):
            _normalize_available('maybe')

    def test_list_type_raises(self) -> None:
        with pytest.raises(ValueError, match='Invalid available value type'):
            _normalize_available([1])
