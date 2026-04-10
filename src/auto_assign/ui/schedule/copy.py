'''Static copy / markdown blocks for the schedule workflow page.'''

from __future__ import annotations

import streamlit as st


def render_quick_reference_expander() -> None:
    with st.expander('Quick reference', expanded=False):
        st.markdown(
            '- **Before first use:** load **Technician Profiles** and **Task Catalog** from the sidebar.\n'
            '- **Upload** a schedule CSV, then use **Continue** at each step in order.\n'
            '- **Generate draft**, review, then **Publish** or **Discard**.\n'
            '- **Assignment history** lists published dates.'
        )


def render_schedule_file_requirements_card() -> None:
    st.markdown(
        '''
<div class="aa-card">
  <div class="aa-kicker">Schedule file</div>
  <div class="aa-muted" style="margin-bottom:0.5rem;">
    Your CSV is the source of truth for <em>who could</em> work each day and shift before you add call-offs or overtime in Step 2.
  </div>
  <strong>Required columns:</strong> <code>tech_name</code>, <code>date</code>, <code>available_AM</code>,
  <code>available_MID</code>, <code>available_PM</code>, <code>staffing_status</code>.<br/>
  <strong>Date format:</strong> <code>YYYY-MM-DD</code>. <strong>Shift flags:</strong>
  <code>1</code>/<code>0</code>, <code>yes</code>/<code>no</code>, or <code>true</code>/<code>false</code>.<br/>
  Rows with <code>staffing_status = call_off</code> are treated as not available for assignment.
</div>
''',
        unsafe_allow_html=True,
    )
