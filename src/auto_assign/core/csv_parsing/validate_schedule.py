import pandas as pd


# Column names expected after standardize_schedule_column_names() (see parse_schedule).
REQUIRED_COLUMNS = ['tech_name', 'date', 'available_AM', 'available_MID', 'available_PM']


def standardize_schedule_column_names(df: pd.DataFrame) -> pd.DataFrame:
    '''
    Prepare headers before validation: strip whitespace; map legacy names if needed.

    **Canonical CSV columns** (what users should author) are ``available_AM``,
    ``available_MID``, ``available_PM``. Some exports use legacy ``availableAM`` /
    ``availableMID`` / ``availablePM`` without underscores; those are renamed here
    only when the canonical names are not already present.
    '''
    out = df.copy()
    out.columns = [str(c).strip() for c in out.columns]
    camel_to_snake = {
        'availableAM': 'available_AM',
        'availableMID': 'available_MID',
        'availablePM': 'available_PM',
    }
    renames = {
        old: new
        for old, new in camel_to_snake.items()
        if old in out.columns and new not in out.columns
    }
    return out.rename(columns=renames)


def _check_required_columns_exist(df: pd.DataFrame, required_columns: list[str] = REQUIRED_COLUMNS) -> None:
    '''
    Check if the DataFrame contains all the required columns.
    '''
    if not all(col in df.columns for col in required_columns):
        missing_cols = [col for col in required_columns if col not in df.columns]
        raise ValueError(f"The DataFrame is missing the following columns: {missing_cols}")


def _ensure_not_empty(df: pd.DataFrame, column: str) -> None:
    '''
    Check if the DataFrame contains any empty values in the specified column.
    '''
    if df[column].isna().sum() > 0:
        raise ValueError(f"The DataFrame contains empty values in the {column} column")


