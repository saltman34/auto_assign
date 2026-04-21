'''Streamlit panel for loading / resetting the demo dataset.

Renders at the top of the Home page:

- If the DB has no technicians, a prominent card with a single "Load demo
  data" primary button.
- If the DB already has technicians, a collapsed expander with both "Load"
  and a two-step "Reset" button.

After a successful load, the future-schedule CSV is offered as a download so
the operator can drag it into the Schedule CSV uploader below.
'''
from __future__ import annotations

import io
from dataclasses import dataclass

import streamlit as st

from auto_assign.db import list_technicians, session_scope
from auto_assign.demo import reset_demo_data, seed_demo_data
from auto_assign.demo.seed import SeedResult
from auto_assign.ingestion.csv_schema import ScheduleRow

_SS_LAST_SEED = 'demo_data__last_seed_result_csv'
_SS_LAST_SEED_SUMMARY = 'demo_data__last_seed_summary'
_SS_RESET_ARMED = 'demo_data__reset_armed'


@dataclass(frozen=True)
class _SeedSummary:
    tasks: int
    technicians: int
    past_days: int
    confirmed_rows: int
    future_rows: int


def render_demo_data_panel() -> None:
    '''Top-of-Home panel. Safe to call on every rerun.'''
    tech_count = count_technicians()

    if tech_count == 0:
        _render_empty_state_card()
    else:
        _render_populated_expander(tech_count)

    _render_post_load_banner_if_present()


def count_technicians() -> int:
    '''Return the number of technicians currently in the database.

    Returns ``0`` when the database is unreachable or unconfigured. Exposed so
    other UI modules (e.g. Home) can decide layout based on whether the demo
    has been seeded, without re-implementing the probe.
    '''
    try:
        with session_scope() as session:
            return len(list_technicians(session))
    except Exception:
        return 0


def _render_empty_state_card() -> None:
    st.markdown(
        '''
<div class="aa-card aa-card--spotlight">
  <div class="aa-kicker">First time here?</div>
  <div class="aa-card-title">Load demo data</div>
  <span class="aa-muted">Populate the database with an 18-technician roster, a
    6-task catalog, and 14 days of published assignment history. After it loads
    you will get a 7-day schedule CSV to drop into the uploader below — one
    click and the scheduler has something to work with.</span>
</div>
''',
        unsafe_allow_html=True,
    )
    if st.button(
        'Load demo data',
        type='primary',
        key='demo_data_load_empty',
    ):
        _run_seed()
        st.rerun()


def _render_populated_expander(tech_count: int) -> None:
    with st.expander(f'Demo data & database tools (currently {tech_count} technicians)', expanded=False):
        st.caption(
            'Reseed to refresh demo history against today. **Reset database** wipes '
            'every task, technician, and assignment row — demo-seeded or not — back '
            'to an empty schema.'
        )
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button('Load demo data', key='demo_data_load_populated'):
                _run_seed()
                st.rerun()
        with col_b:
            if st.session_state.get(_SS_RESET_ARMED):
                st.warning(
                    'This will delete **every** task, technician, and '
                    'assignment row in the database. There is no undo.'
                )
                col_c, col_d = st.columns(2)
                with col_c:
                    if st.button(
                        'Yes, reset everything',
                        type='primary',
                        key='demo_data_reset_confirm',
                    ):
                        _run_reset()
                        st.session_state[_SS_RESET_ARMED] = False
                        st.rerun()
                with col_d:
                    if st.button('Cancel', key='demo_data_reset_cancel'):
                        st.session_state[_SS_RESET_ARMED] = False
                        st.rerun()
            else:
                if st.button('Reset database', key='demo_data_reset_arm'):
                    st.session_state[_SS_RESET_ARMED] = True
                    st.rerun()


def _render_post_load_banner_if_present() -> None:
    summary: _SeedSummary | None = st.session_state.get(_SS_LAST_SEED_SUMMARY)
    csv_bytes: bytes | None = st.session_state.get(_SS_LAST_SEED)
    if summary is None or csv_bytes is None:
        return

    st.success(
        f'Demo data loaded: {summary.tasks} tasks, {summary.technicians} technicians, '
        f'{summary.past_days} days of published history ({summary.confirmed_rows} assignments). '
        f'Download the {summary.future_rows}-row future schedule below, then upload it to the '
        '**Schedule CSV** field to generate a draft.'
    )
    st.download_button(
        label='Download demo schedule CSV',
        data=csv_bytes,
        file_name='demo_schedule.csv',
        mime='text/csv',
        key='demo_data_download_csv',
    )


def _run_seed() -> None:
    with session_scope() as session:
        result = seed_demo_data(session)
    st.session_state[_SS_LAST_SEED] = _future_rows_to_csv_bytes(result.future_schedule_rows)
    st.session_state[_SS_LAST_SEED_SUMMARY] = _SeedSummary(
        tasks=result.tasks_created,
        technicians=result.technicians_upserted,
        past_days=result.past_days_confirmed,
        confirmed_rows=result.confirmed_assignments_written,
        future_rows=len(result.future_schedule_rows),
    )


def _run_reset() -> None:
    with session_scope() as session:
        reset_demo_data(session)
    st.session_state.pop(_SS_LAST_SEED, None)
    st.session_state.pop(_SS_LAST_SEED_SUMMARY, None)


def _future_rows_to_csv_bytes(rows: list[ScheduleRow]) -> bytes:
    '''Serialize future schedule rows to the same CSV shape the uploader accepts.'''
    buf = io.StringIO()
    buf.write('tech_name,date,available_AM,available_MID,available_PM,staffing_status\n')
    for r in rows:
        buf.write(
            ','.join(
                [
                    _csv_escape(r.tech_name),
                    r.work_date.isoformat(),
                    '1' if r.available_AM else '0',
                    '1' if r.available_MID else '0',
                    '1' if r.available_PM else '0',
                    r.staffing_status.value,
                ]
            )
        )
        buf.write('\n')
    return buf.getvalue().encode('utf-8')


def _csv_escape(value: str) -> str:
    if ',' in value or '"' in value or '\n' in value:
        escaped = value.replace('"', '""')
        return f'"{escaped}"'
    return value
