'''Browse confirmed assignments by date with optional filters.'''

from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from auto_assign.db import (
    list_distinct_work_dates_with_confirmed,
    load_confirmed_assignment_rows_for_date,
    session_scope,
)
from auto_assign.ui.db_state import database_url_configured
from auto_assign.ui.page import render_page_header

_SS_HISTORY_UI_REVISION = '_aa_assignment_history_ui_revision'


def bump_assignment_history_ui_revision() -> None:
    '''Invalidate cached Streamlit widget keys so History defaults to the latest data after publish.'''
    st.session_state[_SS_HISTORY_UI_REVISION] = int(st.session_state.get(_SS_HISTORY_UI_REVISION, 0)) + 1


def render_assignment_history_page() -> None:
    render_page_header(
        'Assignment history',
        'Review published (confirmed) assignments by date. Filter by shift, technician, or task.',
        kicker='Read-only',
    )
    if not database_url_configured():
        st.info(
            'Database URL is not configured. Set `DATABASE_URL` (or Postgres env vars) in `.env`, '
            'then run migrations.'
        )
        return

    rev = int(st.session_state.get(_SS_HISTORY_UI_REVISION, 0))
    st.caption(
        'Only **published** (confirmed) rows appear here—not drafts. After you **Publish** on Home, '
        'this page selects the newest date automatically; change the date to see other days.'
    )

    try:
        with session_scope() as session:
            dates = list_distinct_work_dates_with_confirmed(session, limit=730)
    except Exception as e:
        st.error(f'Could not load assignment dates: {e}')
        return

    if not dates:
        st.markdown(
            '<div class="aa-empty">No confirmed assignments yet. Publish a schedule from '
            '<strong>Home → Assignment Engine</strong> to see history here.</div>',
            unsafe_allow_html=True,
        )
        return

    pick = st.selectbox(
        'Work date',
        options=dates,
        format_func=lambda d: d.isoformat(),
        index=0,
        key=f'history_pick_date_{rev}',
    )

    try:
        with session_scope() as session:
            rows = load_confirmed_assignment_rows_for_date(session, pick)
    except Exception as e:
        st.error(f'Could not load assignments: {e}')
        return

    if not rows:
        st.info('No confirmed rows for this date.')
        return

    df = pd.DataFrame(rows)

    slots = sorted(df['time_slot'].unique().tolist())
    techs = sorted(df['tech_id'].unique().tolist())
    tasks = sorted(df['task'].unique().tolist())

    fk = pick.isoformat()

    def _universe_or_pick(sel: list, universe: list) -> list:
        '''Empty multiselect means “no filter” — use full universe.'''
        return list(sel) if sel else list(universe)

    c_date, c_filter = st.columns([2, 1], vertical_alignment='center')
    with c_date:
        st.caption(f'**{len(df)}** published row(s) on this date.')
    with c_filter:
        with st.popover('Filter results', use_container_width=True):
            st.caption('Pick one or more values to narrow the table. Leave a field empty to include **all** in that category.')
            slot_sel = st.multiselect(
                'Time block',
                options=slots,
                default=[],
                placeholder='All time blocks',
                key=f'history_filter_slot_{fk}',
            )
            tech_sel = st.multiselect(
                'Technician (`tech_id`)',
                options=techs,
                default=[],
                placeholder='All technicians',
                key=f'history_filter_tech_{fk}',
            )
            task_sel = st.multiselect(
                'Task',
                options=tasks,
                default=[],
                placeholder='All tasks',
                key=f'history_filter_task_{fk}',
            )

    slot_use = _universe_or_pick(slot_sel, slots)
    tech_use = _universe_or_pick(tech_sel, techs)
    task_use = _universe_or_pick(task_sel, tasks)

    def _is_wide_open(sel: list, universe: list) -> bool:
        return not sel or set(sel) == set(universe)

    wide_open = (
        _is_wide_open(slot_sel, slots)
        and _is_wide_open(tech_sel, techs)
        and _is_wide_open(task_sel, tasks)
    )

    view = df[
        df['time_slot'].isin(slot_use)
        & df['tech_id'].isin(tech_use)
        & df['task'].isin(task_use)
    ]

    if wide_open:
        st.caption(f'Showing **all {len(view)}** row(s) for **{pick.isoformat()}**. Open **Filter results** to narrow.')
    else:
        st.caption(
            f'Showing **{len(view)}** of **{len(df)}** row(s) for **{pick.isoformat()}** — filter active.'
        )
    st.dataframe(view, use_container_width=True, hide_index=True)

    if len(view) > 0:
        buf = io.StringIO()
        view.to_csv(buf, index=False)
        st.download_button(
            'Download filtered view as CSV',
            data=buf.getvalue().encode('utf-8'),
            file_name=f'confirmed_assignments_{pick.isoformat()}.csv',
            mime='text/csv',
            key='history_download_csv',
        )
