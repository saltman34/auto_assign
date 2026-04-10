'''Tests for tech profile CSV → domain ``Tech``.'''

import io

import pandas as pd
import pytest

from auto_assign.core.csv_parsing.parse_tech_profiles import (
    load_tech_profile_csv,
    parse_tech_profiles,
    task_names_from_form_field,
)
from auto_assign.core.task_management import validate_tech_preference_lists
from auto_assign.domain.enums import DailyPreference

TASK_NAMES = ['Clinicals', 'Recuts', 'Scrolls', 'Embedding', 'Exhaust Checks', 'Grossing']


def test_task_names_from_form_field() -> None:
    assert task_names_from_form_field('A; B; C') == ['A', 'B', 'C']
    assert task_names_from_form_field('X, Y') == ['X', 'Y']


def test_parse_tech_profiles_sample_rows() -> None:
    df = pd.DataFrame(
        [
            {
                'tech_id': 'x1',
                'tech_name': 'Pat Lee',
                'daily_preference': 'consistency',
                'favorites': 'Scrolls; Clinicals',
                'dislikes': 'Recuts',
            }
        ]
    )
    techs = parse_tech_profiles(df, allowed_task_names=TASK_NAMES)
    assert len(techs) == 1
    t = techs[0]
    assert t.tech_id == 'x1'
    assert t.tech_name == 'Pat Lee'
    assert t.daily_preference == DailyPreference.CONSISTENCY
    assert t.favorites == ['Scrolls', 'Clinicals']
    assert t.dislikes == ['Recuts']


def test_load_and_parse_sample_csv_file() -> None:
    raw = (
        'tech_id,tech_name,daily_preference\n'
        'a,Ann,variation\n'
    )
    df = load_tech_profile_csv(io.BytesIO(raw.encode('utf-8')))
    techs = parse_tech_profiles(df, allowed_task_names=TASK_NAMES)
    assert techs[0].daily_preference == DailyPreference.VARIATION


def test_parse_missing_column_raises() -> None:
    df = pd.DataFrame([{'tech_id': 'a'}])
    with pytest.raises(ValueError, match='missing required'):
        parse_tech_profiles(df, allowed_task_names=TASK_NAMES)


def test_validate_duplicate_favorite_raises() -> None:
    with pytest.raises(ValueError, match='Duplicate favorite'):
        validate_tech_preference_lists(
            ['Scrolls', 'scrolls'],
            [],
            allowed_task_names=TASK_NAMES,
        )


def test_validate_overlap_favorite_dislike_raises() -> None:
    with pytest.raises(ValueError, match='both a favorite and a dislike'):
        validate_tech_preference_lists(
            ['Clinicals'],
            ['Clinicals'],
            allowed_task_names=TASK_NAMES,
        )


def test_parse_csv_raises_when_favorite_and_dislike_share_task() -> None:
    '''Same task in both columns (after normalization) must error through CSV parse.'''
    df = pd.DataFrame(
        [
            {
                'tech_id': 'x',
                'tech_name': 'Pat',
                'daily_preference': 'consistency',
                'favorites': 'Clinicals',
                'dislikes': 'clinicals',
            }
        ]
    )
    with pytest.raises(ValueError, match='both a favorite and a dislike'):
        parse_tech_profiles(df, allowed_task_names=TASK_NAMES)


def test_validate_unknown_task_raises() -> None:
    with pytest.raises(ValueError, match='Invalid task name'):
        validate_tech_preference_lists(['NotATask'], [], allowed_task_names=TASK_NAMES)


def test_parse_csv_raises_when_task_not_in_catalog() -> None:
    '''Unknown favorite/dislike names must fail validation against the task catalog.'''
    df = pd.DataFrame(
        [
            {
                'tech_id': 'x',
                'tech_name': 'Pat',
                'daily_preference': 'consistency',
                'favorites': 'MadeUpTaskName',
                'dislikes': '',
            }
        ]
    )
    with pytest.raises(ValueError, match='Invalid task name'):
        parse_tech_profiles(df, allowed_task_names=TASK_NAMES)


def test_validate_too_many_favorites_raises() -> None:
    with pytest.raises(ValueError, match='At most 3 favorites'):
        validate_tech_preference_lists(
            ['Clinicals', 'Recuts', 'Scrolls', 'Embedding'],
            [],
            allowed_task_names=TASK_NAMES,
        )


def test_validate_empty_lists_ok() -> None:
    f, d = validate_tech_preference_lists([], [], allowed_task_names=TASK_NAMES)
    assert f == [] and d == []
