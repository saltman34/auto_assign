'''Streamlit UI composition (keeps ``app.py`` thin).'''

import streamlit as st

from auto_assign.ui.about import render_about_page
from auto_assign.ui.assignment_history import render_assignment_history_page
from auto_assign.ui.db_state import database_url_configured
from auto_assign.ui.home import render_home_page
from auto_assign.ui.page import configure_page, render_page_header, render_theme
from auto_assign.ui.schedule import render_schedule_section, render_schedule_workflow
from auto_assign.ui.task_catalog import render_task_catalog_page
from auto_assign.ui.technicians_panel import render_technician_profiles_page


def render_app() -> None:
    render_theme()
    db_pill = (
        '<span class="aa-pill aa-pill--ok">Database ready</span>'
        if database_url_configured()
        else '<span class="aa-pill aa-pill--warn">No DATABASE_URL</span>'
    )
    st.sidebar.markdown(
        f'''<div class="aa-sidebar-brand">
  <div class="aa-sidebar-brand-title">Auto Assign</div>
  <p class="aa-sidebar-brand-tagline">Biotech workflow assistant</p>
  <div class="aa-sidebar-meta">{db_pill}</div>
</div>''',
        unsafe_allow_html=True,
    )
    page = st.sidebar.radio(
        'Navigation',
        options=('Home', 'Technician Profiles', 'Task Catalog', 'Assignment history', 'About this app'),
    )
    if page == 'Home':
        render_home_page()
    elif page == 'Technician Profiles':
        render_technician_profiles_page()
    elif page == 'Task Catalog':
        render_task_catalog_page()
    elif page == 'Assignment history':
        render_assignment_history_page()
    else:
        render_about_page()


__all__ = [
    'configure_page',
    'render_about_page',
    'render_assignment_history_page',
    'render_app',
    'render_home_page',
    'render_page_header',
    'render_theme',
    'render_schedule_section',
    'render_schedule_workflow',
    'render_task_catalog_page',
    'render_technician_profiles_page',
]
