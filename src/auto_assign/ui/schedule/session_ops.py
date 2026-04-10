'''Session reset helpers for starting a new schedule run.'''

from __future__ import annotations

import streamlit as st

from auto_assign.ui.schedule.state import (
    _SS_LAST_UPLOAD_ID,
    _SS_OFFER_START_NEW_RUN,
    _SS_PUBLISH_CSV_SLICE,
    _SS_SCHED_NONCE,
)


def clear_session_keys_containing(fragment: str) -> None:
    for k in list(st.session_state.keys()):
        if isinstance(k, str) and fragment in k:
            st.session_state.pop(k, None)


def start_new_schedule_run(current_upload_id: str | None) -> None:
    if current_upload_id:
        clear_session_keys_containing(current_upload_id)
    st.session_state.pop(_SS_LAST_UPLOAD_ID, None)
    st.session_state.pop(_SS_PUBLISH_CSV_SLICE, None)
    st.session_state.pop(_SS_OFFER_START_NEW_RUN, None)
    st.session_state[_SS_SCHED_NONCE] = int(st.session_state.get(_SS_SCHED_NONCE, 0)) + 1
