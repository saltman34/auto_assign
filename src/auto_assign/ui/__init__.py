'''Streamlit UI composition (keeps ``app.py`` thin).'''

from collections.abc import Callable

import streamlit as st

from auto_assign.ui.about import render_about_page
from auto_assign.ui.assets import logo_data_uri
from auto_assign.ui.assignment_history import render_assignment_history_page
from auto_assign.ui.db_state import database_url_configured
from auto_assign.ui.home import render_home_page
from auto_assign.ui.page import configure_page, render_page_header, render_theme
from auto_assign.ui.schedule import render_schedule_section, render_schedule_workflow
from auto_assign.ui.task_catalog import render_task_catalog_page
from auto_assign.ui.technicians_panel import render_technician_profiles_page

_NAV_PAGES: tuple[tuple[str, Callable[[], None]], ...] = (
    ('Home', render_home_page),
    ('Technician Profiles', render_technician_profiles_page),
    ('Task Catalog', render_task_catalog_page),
    ('Assignment history', render_assignment_history_page),
    ('About this app', render_about_page),
)


def _render_sidebar_brand() -> None:
    db_pill = (
        '<span class="aa-pill aa-pill--ok">Database ready</span>'
        if database_url_configured()
        else '<span class="aa-pill aa-pill--warn">No DATABASE_URL</span>'
    )
    st.sidebar.markdown(
        f'''<div class="aa-sidebar-brand">
  <div class="aa-sidebar-brand-row">
    <img class="aa-sidebar-brand-mark" src="{logo_data_uri()}" alt="Auto Assign logo" />
    <div class="aa-sidebar-brand-text">
      <div class="aa-sidebar-brand-title">Auto Assign</div>
      <p class="aa-sidebar-brand-tagline">Shift task scheduler · Portfolio project</p>
    </div>
  </div>
  <div class="aa-sidebar-meta">{db_pill}</div>
</div>''',
        unsafe_allow_html=True,
    )


def render_app() -> None:
    render_theme()
    _render_sidebar_brand()
    labels = tuple(label for label, _ in _NAV_PAGES)
    selected = st.sidebar.radio('Navigation', options=labels)
    renderer = dict(_NAV_PAGES)[selected]
    renderer()


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
