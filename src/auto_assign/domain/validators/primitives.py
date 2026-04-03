'''
Validators for primitive types.
'''
from datetime import date
from enum import Enum

def normalize_string(value: str) -> str:
    '''
    Normalize the string to a consistent format.
    '''
    return value.strip().title()


def normalize_tech_id(value: str) -> str:
    '''
    Stable technician id for FKs and ``Assignment.technician_id``: trim only, preserve casing.
    '''
    s = value.strip()
    if not s:
        raise ValueError('tech_id cannot be empty')
    return s


def require_non_empty_string(value: str) -> str:
    '''
    Require the string to be non-empty.
    '''
    if not value:
        raise ValueError("Value cannot be empty")
    return value

def require_boolean(value: bool) -> bool:
    '''
    Require a proper boolean (True or False).

    Use for flags where False is valid. Rejects any non-bool (including None);
    does not coerce from int/str (normalize in CSV parsing first).
    '''
    if not isinstance(value, bool):
        raise ValueError(f"Expected bool, got {type(value).__name__}")
    return value


def require_non_empty_enum(value: Enum) -> Enum:
    '''
    Require the enum to be non-empty.
    '''
    if not value:
        raise ValueError("Value cannot be empty")
    return value


def require_positive_integer(value: int) -> int:
    '''
    Require the integer to be positive.
    '''
    if value < 0:
        raise ValueError("Value must be a positive integer")
    return value

def require_date(value: date) -> date:
    '''
    Require the date to be a valid date.
    '''
    if value is None:
        raise ValueError("Date cannot be None")
    return value