import math
import numbers
from datetime import date, datetime


AVAILABLE_VALUES = ['yes', 'true', 'y', '1']
NOT_AVAILABLE_VALUES = ['no', 'false', 'n', '0']

def _normalize_tech_name(tech_name: str) -> str:
    '''
    Normalize the tech name to a consistent format.
    '''
    return tech_name.strip().title()


def _normalize_date(value) -> date:
    '''
    Normalize a date cell to a ``datetime.date`` (YYYY-MM-DD string or existing date).
    '''
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value.strip(), '%Y-%m-%d').date()
        except ValueError as e:
            raise ValueError(
                f"Invalid date format: {value!r}. Expected format: YYYY-MM-DD"
            ) from e
    raise ValueError(f"Invalid date type: {type(value).__name__}")


def _normalize_available(available) -> bool:
    '''
    Normalize a cell value to True/False for AM/MID/PM availability columns.

    Accepts booleans, 0/1 (including floats from CSV), and yes/no style strings.
    '''
    if available is None:
        raise ValueError("Availability value cannot be empty or None")
    if isinstance(available, float) and math.isnan(available):
        raise ValueError("Availability value cannot be NaN")
    if isinstance(available, bool):
        return available
    # ``numbers.Integral`` / ``Real`` cover numpy int64/float64 and similar scalars
    # (``bool`` is handled above; it is also an Integral in Python).
    if isinstance(available, numbers.Integral):
        iv = int(available)
        if iv == 1:
            return True
        if iv == 0:
            return False
        raise ValueError(f"Invalid numeric availability: {available}. Use 0 or 1.")
    if isinstance(available, numbers.Real):
        fv = float(available)
        if fv == 1.0:
            return True
        if fv == 0.0:
            return False
        raise ValueError(f"Invalid numeric availability: {available}. Use 0 or 1.")
    if isinstance(available, str):
        s = available.strip().lower()
        if s in AVAILABLE_VALUES:
            return True
        if s in NOT_AVAILABLE_VALUES:
            return False
        raise ValueError(
            f"Invalid available value: {available!r}. "
            f"Expected one of: {AVAILABLE_VALUES} or {NOT_AVAILABLE_VALUES}"
        )
    raise ValueError(f"Invalid available value type: {type(available).__name__}")
