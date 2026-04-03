'''Global Streamlit page chrome (title, intro).'''

from __future__ import annotations

import streamlit as st


def configure_page() -> None:
    st.set_page_config(page_title='Auto Assign', page_icon=':robot:', layout='wide')


def render_header() -> None:
    st.title('Auto Assign')
    st.write(
        'This is a simple app to assign technicians to work based on their availability and the work date.'
    )
    st.write(
        'Upload a schedule CSV with **tech_name**, **date** (YYYY-MM-DD), and '
        '**available_AM**, **available_MID**, **available_PM** (one boolean per shift). '
        'Cells can use 1/0, yes/no, or true/false. '
        'Legacy exports without underscores in those three header names are normalized on upload.'
    )
