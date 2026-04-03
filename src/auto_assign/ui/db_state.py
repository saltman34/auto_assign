'''Streamlit helpers: whether the app database is configured.'''

from __future__ import annotations

from auto_assign.db.session import get_database_url


def database_url_configured() -> bool:
    try:
        get_database_url()
        return True
    except ValueError:
        return False


def tech_id_to_display_name(tech_id: str, profiles_by_name: dict) -> str:
    for tech in profiles_by_name.values():
        if tech.tech_id == tech_id:
            return tech.tech_name
    return tech_id
