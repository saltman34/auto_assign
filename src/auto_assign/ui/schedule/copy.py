'''Static copy / markdown blocks for the schedule workflow page.'''

from __future__ import annotations

import streamlit as st


def render_first_time_setup_expander() -> None:
    '''Expander aimed at first-time users who are *not* using the seeded demo.

    The Home page also offers a one-click "Load demo data" panel that populates
    Technician Profiles and the Task Catalog in the database. Users who take
    that path can skip this section entirely; they already have the data a
    schedule needs to reference. This expander exists for the other path —
    someone wiring the app up against their own lab's roster and tasks — so
    the title and body are explicit about that audience instead of pretending
    to be a generic "quick reference."
    '''
    with st.expander('Using your own data? First-time setup (skip for the demo)', expanded=False):
        st.markdown(
            'If you loaded demo data above, **skip this** — Technician Profiles '
            'and the Task Catalog are already populated.\n\n'
            '**Bringing your own lab\'s data?** Before you upload a schedule:\n\n'
            '- Load **Technician Profiles** from the sidebar so every `tech_name` '
            'in your CSV maps to a `tech_id` and preferences are available for scoring.\n'
            '- Load the **Task Catalog** from the sidebar with the tasks you assign '
            'and their default daily counts.\n\n'
            'Once both pages have rows, return here and upload your schedule CSV below.'
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
