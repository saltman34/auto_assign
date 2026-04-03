'''Streamlit UI composition (keeps ``app.py`` thin).'''

import streamlit as st

from auto_assign.ui.page import configure_page, render_home_page
from auto_assign.ui.schedule_assignments import render_schedule_section
from auto_assign.ui.technicians_panel import render_technician_profiles_page


def render_app() -> None:
    page = st.sidebar.radio(
        'Navigation',
        options=('Home', 'Technician Profiles', 'Allocation / Assignment'),
    )
    if page == 'Home':
        render_home_page()
    elif page == 'Technician Profiles':
        render_technician_profiles_page()
    else:
        render_schedule_section()


__all__ = [
    'configure_page',
    'render_app',
    'render_home_page',
    'render_schedule_section',
    'render_technician_profiles_page',
]
