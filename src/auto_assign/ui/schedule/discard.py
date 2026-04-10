'''Discard draft slice + related session keys.'''

from __future__ import annotations

from datetime import date

import streamlit as st

from auto_assign.db import clear_draft_overrides_for_slice, delete_draft_slice, session_scope
from auto_assign.domain.enums import TimeSlot
from auto_assign.ui.db_state import database_url_configured
from auto_assign.ui.schedule.state import _SS_ASSIGN_FLASH, _SS_OFFER_START_NEW_RUN


def handle_discard_draft_click(
    draft_key: str,
    gen_sig_key: str,
    work_date: date,
    time_slot: TimeSlot,
    session_keys_to_clear: tuple[str, ...] = (),
) -> None:
    if database_url_configured():
        try:
            with session_scope() as session:
                delete_draft_slice(session, work_date, time_slot)
                clear_draft_overrides_for_slice(session, work_date, time_slot)
        except Exception as e:
            st.error(f'Could not discard draft: {e}')
            return
        flash_msg = (
            '**Draft discarded.** Draft assignments and draft overrides for this date are cleared. '
            'Published schedules remain unchanged.'
        )
    else:
        flash_msg = 'Draft cleared from this session (no database configured).'
    st.session_state.pop(draft_key, None)
    st.session_state.pop(gen_sig_key, None)
    for k in session_keys_to_clear:
        st.session_state.pop(k, None)
    st.session_state[_SS_ASSIGN_FLASH] = {'message': flash_msg, 'warnings': ()}
    st.session_state[_SS_OFFER_START_NEW_RUN] = True
    st.rerun()
