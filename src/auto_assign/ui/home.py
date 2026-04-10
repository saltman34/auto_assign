'''Home dashboard copy and embedded assignment engine.'''

from __future__ import annotations

import streamlit as st

from auto_assign.ui.page import render_page_header
from auto_assign.ui.schedule import (
    render_assignment_engine_outcome_banner,
    render_schedule_workflow,
)


def render_home_page() -> None:
    render_page_header(
        'Auto Assign',
        'Automate shift task assignments using technician preferences and fairness-aware scoring.',
        kicker='Home · assignment engine',
    )
    st.markdown(
        '''
<div class="aa-hero">
  <div class="aa-kicker">At a glance</div>
  <div class="aa-muted" style="font-size:1.02rem;">
    Upload a schedule CSV, set task headcounts for a date and shift, optionally add manual pre-assignments, then
    generate a <strong>draft</strong> and <strong>Publish</strong> when it looks right. Technician profiles and the
    task list live in the sidebar. <strong>Assignment history</strong> shows past published days. For how placements are decided, see <strong>About this app</strong>.
  </div>
</div>
''',
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            '''
<div class="aa-card">
  <div class="aa-kicker">This page</div>
  <div class="aa-card-title">Assignment Engine</div>
  <span class="aa-muted">Daily workflow: upload → date → overrides → shift → headcounts → optional manual rows → generate draft → publish or discard draft.</span>
</div>
''',
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            '''
<div class="aa-card">
  <div class="aa-kicker">People</div>
  <div class="aa-card-title">Technician Profiles</div>
  <span class="aa-muted">Import or edit technicians so every schedule name maps to a <code>tech_id</code> and preferences exist for scoring.</span>
</div>
''',
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            '''
<div class="aa-card">
  <div class="aa-kicker">Tasks</div>
  <div class="aa-card-title">Task Catalog</div>
  <span class="aa-muted">Define assignable tasks and default counts before you run headcounts in the engine.</span>
</div>
''',
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            '''
<div class="aa-card">
  <div class="aa-kicker">Sidebar</div>
  <div class="aa-card-title">Assignment history</div>
  <span class="aa-muted">Read-only list of <strong>published</strong> (confirmed) assignments by date. Open it after you publish to audit or download CSVs—not for drafts.</span>
</div>
''',
            unsafe_allow_html=True,
        )

    st.divider()
    st.markdown('### Assignment Engine')
    st.caption(
        'Upload a schedule, select date and shift, set headcounts, then generate and confirm assignments.'
    )
    render_schedule_workflow()
    render_assignment_engine_outcome_banner()
