'''Streamlit UI composition (keeps ``app.py`` thin).'''

from auto_assign.ui.page import configure_page, render_header
from auto_assign.ui.schedule_assignments import render_schedule_section
from auto_assign.ui.technicians_panel import render_technicians_expander


def render_app() -> None:
    render_header()
    render_technicians_expander()
    render_schedule_section()


__all__ = [
    'configure_page',
    'render_app',
    'render_header',
    'render_schedule_section',
    'render_technicians_expander',
]
