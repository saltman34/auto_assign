'''Global Streamlit page chrome and home page copy.'''

from __future__ import annotations

import streamlit as st


def configure_page() -> None:
    st.set_page_config(page_title='Auto Assign', page_icon=':robot:', layout='wide')


def render_home_page() -> None:
    st.title('Auto Assign')
    st.markdown(
        'Auto Assign helps you keep technician profiles in the database and generate shift-level '
        'task allocations from schedule availability using compatibility scoring + greedy assignment.'
    )
    st.markdown('### App pages')
    st.markdown(
        '- **Home**: overview and quick start\n'
        '- **Technician Profiles**: import/edit technicians and manage the technician database\n'
        '- **Allocation / Assignment**: upload a schedule and generate assignments'
    )
    st.markdown('### Schedule CSV requirements')
    st.markdown(
        'Required columns: `tech_name`, `date` (YYYY-MM-DD), `available_AM`, `available_MID`, '
        '`available_PM`, `staffing_status` (`scheduled`, `call_off`, `overtime`).'
    )
