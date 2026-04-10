'''Post-publish CSV / flash messaging below the assignment engine.'''

from __future__ import annotations

import io
from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from auto_assign.db import load_confirmed_assignment_rows_for_slice, session_scope
from auto_assign.domain.enums import TimeSlot
from auto_assign.ui.db_state import database_url_configured
from auto_assign.ui.schedule.session_ops import start_new_schedule_run
from auto_assign.ui.schedule.state import (
    _SS_ASSIGN_FLASH,
    _SS_DAY_OVERRIDE_FLASH,
    _SS_LAST_UPLOAD_ID,
    _SS_OFFER_START_NEW_RUN,
    _SS_PUBLISH_CSV_SLICE,
)


def render_assignment_engine_outcome_banner() -> None:
    '''
    One-shot flash (e.g. discard) and/or post-publish follow-up.

    When a slice was just published, the success line and CSV download stay in one bordered
    group so the download never appears without publish context. Discard-only messages omit
    the download block.
    '''
    flash = st.session_state.pop(_SS_ASSIGN_FLASH, None)
    day_override_flash = st.session_state.pop(_SS_DAY_OVERRIDE_FLASH, None)
    ctx = st.session_state.get(_SS_PUBLISH_CSV_SLICE)
    offer_start_new_run = bool(st.session_state.get(_SS_OFFER_START_NEW_RUN))

    if ctx and not database_url_configured():
        st.session_state.pop(_SS_PUBLISH_CSV_SLICE, None)
        ctx = None

    if day_override_flash:
        st.success(day_override_flash)

    if not flash and not ctx and not offer_start_new_run:
        return

    if flash and not ctx:
        _render_post_discard_start_new_run_panel(flash)
        return

    if offer_start_new_run and not ctx:
        _render_post_discard_start_new_run_panel(None)
        return

    if ctx is None:
        return

    work_date = date.fromisoformat(ctx['date'])
    slot = TimeSlot[ctx['slot']]
    rows: list[dict[str, Any]] = []
    load_error: str | None = None
    try:
        with session_scope() as session:
            rows = load_confirmed_assignment_rows_for_slice(session, work_date, slot)
    except Exception as e:
        load_error = str(e)

    with st.container(border=True):
        st.markdown('##### Published — next steps')
        if flash:
            st.success(flash.get('message', ''))
            for w in flash.get('warnings', ()):
                st.warning(w)
        else:
            st.caption(
                f'Confirmed slice for **{work_date.isoformat()}** · **{slot.value}** is saved. '
                'Download a CSV below, dismiss this panel, or start a new run.'
            )
        if load_error:
            st.warning(f'Could not load rows for CSV: {load_error}')
        else:
            st.caption(
                'CSV matches the database record for this date and shift. '
                'For other dates, use **Assignment history** in the sidebar.'
            )
            buf = io.StringIO()
            pd.DataFrame(rows).to_csv(buf, index=False)
            dl_col, dis_col, new_col = st.columns((2, 1, 1))
            with dl_col:
                st.download_button(
                    label='Download published slice as CSV',
                    data=buf.getvalue().encode('utf-8'),
                    file_name=f'published_assignments_{work_date}_{slot.name}.csv',
                    mime='text/csv',
                    key='post_publish_csv_download',
                )
            with dis_col:
                if st.button('Dismiss', key='post_publish_csv_dismiss'):
                    st.session_state.pop(_SS_PUBLISH_CSV_SLICE, None)
                    st.rerun()
            with new_col:
                if st.button(
                    'Start a new run',
                    key='post_publish_start_new_run',
                    help='Clear upload state and reset date, shift, overrides, and draft state.',
                ):
                    start_new_schedule_run(st.session_state.get(_SS_LAST_UPLOAD_ID))
                    st.rerun()


def _render_post_discard_start_new_run_panel(flash: dict[str, Any] | None) -> None:
    with st.container(border=True):
        if flash:
            st.success(flash.get('message', ''))
            for w in flash.get('warnings', ()):
                st.warning(w)
        else:
            st.markdown('##### Ready for another run')
            st.caption(
                'Draft was discarded. Use **Start a new run** when you want a different schedule file. '
                'Published schedules are unchanged.'
            )
        if st.button(
            'Start a new run',
            key='post_discard_start_new_run',
            help='Clear upload state and reset date, shift, overrides, and draft state.',
        ):
            start_new_schedule_run(st.session_state.get(_SS_LAST_UPLOAD_ID))
            st.rerun()
