'''Schedule upload, task allocation, greedy generate, draft reload from DB, confirm.'''

from __future__ import annotations

import streamlit as st

from auto_assign.core import (
    assign_tasks,
    create_tasks,
    filter_schedule_rows_available_for_date_and_time_slot,
    get_all_schedule_dates,
    get_available_techs,
    load_schedule,
    parse_schedule,
)
from auto_assign.domain import Assignment
from auto_assign.db import (
    confirm_slice,
    count_confirmed_for_slice,
    load_confirmed_assignments_for_scoring,
    load_draft_assignments_for_slice,
    load_tech_profiles_by_name,
    replace_draft_slice,
    session_scope,
    technician_ids_missing_from_db,
)
from auto_assign.domain.enums import TimeSlot
from auto_assign.ingestion import TaskRequest
from auto_assign.task_config import tasks as tasks_config

from auto_assign.ui.db_state import database_url_configured, tech_id_to_display_name


def render_schedule_section() -> None:
    st.title('Allocation / Assignment')
    st.caption(
        'Upload a schedule and generate assignments. '
        'Only rows available for the selected shift and not marked `call_off` are assignable.'
    )
    uploaded_file = st.file_uploader('Upload a schedule CSV file', type=['csv'])

    if uploaded_file is None:
        return

    try:
        df = load_schedule(uploaded_file)
        schedule_rows = parse_schedule(df)

        available_dates = get_all_schedule_dates(schedule_rows)

        if not available_dates:
            st.error('No available dates found in the schedule.')
            return

        upload_widget_id = getattr(uploaded_file, 'file_id', None) or uploaded_file.name

        date_options = sorted(available_dates)
        selected_date = st.selectbox(
            'Select a date',
            options=date_options,
            key=f'schedule_date_{upload_widget_id}',
        )
        selected_time_slot = st.selectbox(
            'Select a time slot (shift band)',
            options=list(TimeSlot),
            format_func=lambda slot: slot.value,
            key=f'schedule_time_slot_{upload_widget_id}',
            help='Only technicians marked available for this shift on the selected date are assignable. '
            'Rows with `staffing_status=call_off` are excluded even if shift flags are true.',
        )

        available_techs = get_available_techs(schedule_rows, selected_date, selected_time_slot)
        available_tech_pool = filter_schedule_rows_available_for_date_and_time_slot(
            schedule_rows, selected_date, selected_time_slot
        )

        slot_label = selected_time_slot.value
        st.markdown(f'### Available Techs for {selected_date} ({slot_label})')
        st.metric('Number of Available Techs', len(available_techs))

        if available_techs:
            with st.expander('Available Techs', expanded=False):
                st.markdown('\n'.join(f'- {name}' for name in available_techs))
        else:
            st.info('No available techs for the selected date and time slot.')
            return

        st.markdown('### Task Allocation')
        task_list = create_tasks(tasks_config)

        allocation_context = f'{upload_widget_id}_{selected_date.isoformat()}_{selected_time_slot.name}'

        task_requests = []
        total_requested = 0

        pool_size = len(available_techs)
        for task in task_list:
            count = st.number_input(
                label=f'{task.task_name} Count',
                value=min(task.default_count, pool_size),
                min_value=0,
                max_value=pool_size,
                step=1,
                key=f'task_count_{task.task_id}_{allocation_context}',
                help='Headcount for this task on the selected date and shift (must sum to available techs).',
            )

            task_requests.append(
                TaskRequest(
                    task_id=task.task_id,
                    task_name=task.task_name,
                    task_count=count,
                    task_date=selected_date,
                    time_slot=selected_time_slot,
                )
            )

            total_requested += count

        remaining = len(available_techs) - total_requested

        st.metric('Remaining Techs', remaining)

        can_generate = remaining == 0

        if not can_generate:
            st.warning('Please allocate all available tech slots to tasks before generating assignments.')

        draft_key = f'draft_assignments_{allocation_context}'

        if database_url_configured():
            with session_scope() as session:
                db_draft = load_draft_assignments_for_slice(session, selected_date, selected_time_slot)
            if db_draft:
                st.session_state[draft_key] = list(db_draft)

        with st.expander('Scoring options', expanded=False):
            greedy_seed = st.number_input(
                'Greedy random seed (tie breaks)',
                min_value=0,
                value=42,
                step=1,
                key=f'greedy_seed_{allocation_context}',
            )
            unlimited_lookback = st.checkbox(
                'Use unlimited confirmed history for fairness (no date window)',
                value=False,
                key=f'unlimited_lookback_{allocation_context}',
                help='When off, only confirmed assignments within the lookback window affect scoring.',
            )
            if unlimited_lookback:
                lookback_for_run = None
                st.caption('Fairness and same-day terms use all confirmed rows returned by the loader.')
            else:
                lookback_for_run = st.number_input(
                    'Fairness lookback (days)',
                    min_value=1,
                    max_value=3650,
                    value=30,
                    step=1,
                    key=f'fairness_lookback_{allocation_context}',
                    help='Confirmed assignments older than this many days before the selected date are ignored for fairness terms.',
                )

        if st.button('Generate Assignments', disabled=not can_generate):
            try:
                profiles = None
                confirmed: tuple[Assignment, ...] = ()
                if database_url_configured():
                    with session_scope() as session:
                        profiles = load_tech_profiles_by_name(session)
                        confirmed = load_confirmed_assignments_for_scoring(
                            session, selected_date, lookback_days=lookback_for_run
                        )
                assignments = assign_tasks(
                    task_requests,
                    available_tech_pool,
                    random_seed=greedy_seed,
                    use_greedy_assignment=True,
                    tech_profiles_by_name=profiles,
                    confirmed_assignments=confirmed,
                    fairness_lookback_days=lookback_for_run,
                )
                if database_url_configured():
                    with session_scope() as session:
                        missing = technician_ids_missing_from_db(
                            session, (a.technician_id for a in assignments)
                        )
                    if missing:
                        st.error(
                            'Cannot save draft: the following **tech_id**(s) are not in the database: '
                            f'`{", ".join(missing)}`. Import matching technician profiles (schedule names must '
                            'map to a saved `tech_id`) before generating with persistence.'
                        )
                    else:
                        with session_scope() as session:
                            replace_draft_slice(session, selected_date, selected_time_slot, assignments)
                        st.session_state[draft_key] = assignments
                        st.success('Assignments generated successfully!')
                else:
                    st.session_state[draft_key] = assignments
                    st.success('Assignments generated successfully!')
            except Exception as e:
                st.error(f'Could not generate assignments: {e}')

        rows = st.session_state.get(draft_key)
        if not rows:
            return

        st.markdown('#### Current draft assignments')
        missing_fk: list[str] = []
        profiles_map: dict = {}
        n_confirmed = 0
        if database_url_configured():
            with session_scope() as session:
                missing_fk = technician_ids_missing_from_db(session, (a.technician_id for a in rows))
                profiles_map = load_tech_profiles_by_name(session)
                n_confirmed = count_confirmed_for_slice(session, selected_date, selected_time_slot)
        else:
            profiles_map = {}

        disp = [
            {
                'task': a.task_name,
                'technician': tech_id_to_display_name(a.technician_id, profiles_map),
                'tech_id': a.technician_id,
            }
            for a in rows
        ]
        st.dataframe(disp, use_container_width=True)

        if missing_fk:
            st.error(
                '**Cannot confirm:** every assigned **tech_id** must exist in the database. '
                f'Missing: `{", ".join(missing_fk)}`. Add technician profiles that match these ids '
                '(schedule names need a matching imported profile).'
            )

        if not database_url_configured():
            st.caption('Configure the database to save drafts and confirm schedules.')
            return

        overwrite_ok = True
        if n_confirmed > 0:
            st.warning(
                f'This date and slot already has **{n_confirmed}** confirmed assignment row(s). '
                'Confirming will **replace** that published slice (and clear any draft rows for it).'
            )
            overwrite_ok = st.checkbox(
                'I understand confirmed rows will be replaced.',
                key=f'confirm_overwrite_{allocation_context}',
            )

        confirm_disabled = (n_confirmed > 0 and not overwrite_ok) or bool(missing_fk)
        if st.button(
            'Confirm schedule',
            disabled=confirm_disabled,
            key=f'confirm_btn_{allocation_context}',
        ):
            if missing_fk:
                st.error('Fix unknown tech ids before confirming.')
            else:
                try:
                    with session_scope() as session:
                        confirm_slice(
                            session,
                            selected_date,
                            selected_time_slot,
                            rows,
                        )
                    st.success('Schedule confirmed.')
                except Exception as e:
                    st.error(f'Could not confirm: {e}')

    except Exception as e:
        st.error(f'Could not process the schedule CSV file: {e}')
