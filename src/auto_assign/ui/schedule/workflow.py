'''Multi-step schedule → draft → publish.

Orchestrator ``render_schedule_workflow`` parses CSV, builds ``_PostShiftBundle``
for the locked shift, and delegates to private ``_wf_*`` step functions.
``_HeadcountControls`` passes headcount validation state from step 5 to
generate/publish (step 7). Fairness lookback and greedy policy use fixed product
defaults (not operator-tunable in the UI). Session keys, discard, and outcome
banner live in sibling modules under ``schedule``.
'''

from __future__ import annotations

import io
import zlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import cast

import pandas as pd
import streamlit as st

from auto_assign.core.assignment import NoEligibleTechnicianError
from auto_assign.core.assignment.headcount_distribution import distribute_defaults_across_pool
from auto_assign.core import (
    assign_tasks,
    filter_schedule_rows_available_for_date_and_time_slot,
    get_all_schedule_dates,
    load_schedule,
    parse_schedule,
)
from auto_assign.core.assignment.manual_overrides import (
    IneligibleOverrideInfo,
    ResidualPlan,
    apply_day_availability_overrides,
    build_residual_plan_after_manual_assignments,
    is_tech_eligible_for_catalog_task,
)
from auto_assign.domain import Assignment, Tech
from auto_assign.db import (
    confirm_slice,
    confirm_draft_overrides_for_slice,
    count_confirmed_for_slice,
    load_confirmed_assignment_rows_for_slice,
    load_confirmed_assignments_for_scoring,
    load_draft_overrides_for_slice,
    load_draft_assignments_for_slice,
    load_tech_profiles_by_name,
    list_technicians,
    list_tasks,
    replace_draft_day_availability_overrides,
    replace_draft_manual_assignments_for_slice,
    replace_draft_slice,
    session_scope,
    technician_ids_missing_from_db,
)
from auto_assign.domain.enums import Staffing_Status, TimeSlot
from auto_assign.ingestion import TaskRequest

from auto_assign.ui.assignment_history import bump_assignment_history_ui_revision
from auto_assign.ui.components import render_context_chips, render_step_divider, render_step_panel
from auto_assign.ui.db_state import database_url_configured, tech_id_to_display_name
from auto_assign.ui.page import render_page_header
from auto_assign.ui.schedule.copy import render_first_time_setup_expander, render_schedule_file_requirements_card
from auto_assign.ui.schedule.discard import handle_discard_draft_click
from auto_assign.ui.schedule.helpers import (
    allocation_context,
    normalized_day_override_signature,
    slice_commit_key,
    task_count_signature,
    tech_id_for_row,
)
from auto_assign.ui.schedule.outcome_banner import render_assignment_engine_outcome_banner
from auto_assign.ui.schedule.state import (
    _SS_ASSIGN_FLASH,
    _SS_DAY_OVERRIDE_FLASH,
    _SS_LAST_UPLOAD_ID,
    _SS_OFFER_START_NEW_RUN,
    _SS_PUBLISH_CSV_SLICE,
    _SS_SCHED_NONCE,
)

# Fairness lookback for scoring + ``load_confirmed_assignments_for_scoring`` (must stay in sync).
# **Why 14 days:** balances recency (rotation reacts to recent confirmed work; avoids overweighting
# old staffing patterns) against having enough history for typical daily-ish labs. Longer windows
# (e.g. 30) help when assignment volume per tech is sparse; change here and in operator-facing copy if
# product standardizes differently.
_FAIRNESS_LOOKBACK_DAYS = 14


def _stable_greedy_seed_for_slice(slice_ctx: str) -> int:
    '''
    Stable RNG seed per upload + date + shift so identical inputs yield the same
    draft. Lookahead reduces ties but does not remove them; any remaining tie
    still uses ``random.Random`` with this seed.
    '''
    return zlib.crc32(slice_ctx.encode('utf-8')) & 0x7FFFFFFF


def _format_tech_id_label(tech_by_id: dict[str, Tech], tid: str) -> str:
    row = tech_by_id.get(tid)
    label = row.tech_name if row is not None else tid
    return f'{label} ({tid})'


@dataclass(frozen=True)
class _DayOverrideKeys:
    day_context: str
    call_off_key: str
    override_commit_key: str
    override_overwrite_confirm_key: str
    day_widget_reset_flag: str
    overtime_keys: dict[TimeSlot, str]


@dataclass
class _PostShiftBundle:
    upload_widget_id: str
    selected_date: date
    selected_time_slot: TimeSlot
    schedule_rows: list
    task_list: list
    profiles_map: dict
    techs_all: list
    tech_by_id: dict
    call_off_key: str
    call_off_ids: list[str]
    overtime_keys: dict[TimeSlot, str]
    overtime_ids_by_slot: dict[TimeSlot, list[str]]
    commit_key: str
    slice_ctx: str
    draft_key: str
    gen_sig_key: str
    manual_key: str
    manual_step_commit_key: str
    headcount_commit_key: str
    reset_defaults_flag: str
    manual_assignments: list[Assignment]
    effective_pool: list
    pool_size: int
    slot_label: str
    available_techs: list[str]
    overtime_ids: list[str]


@dataclass
class _HeadcountControls:
    can_generate: bool
    residual_plan: ResidualPlan
    task_requests: list[TaskRequest]


def _day_override_keys(upload_widget_id: str, selected_date: date) -> _DayOverrideKeys:
    day_context = f'{upload_widget_id}_{selected_date.isoformat()}'
    return _DayOverrideKeys(
        day_context=day_context,
        call_off_key=f'aa_call_off_ids_{day_context}',
        override_commit_key=f'aa_day_overrides_committed_{day_context}',
        override_overwrite_confirm_key=f'aa_confirm_day_overrides_overwrite_{day_context}',
        day_widget_reset_flag=f'_aa_reset_day_override_widgets_{day_context}',
        overtime_keys={
            s: f'aa_overtime_ids_{day_context}_{s.name.lower()}'
            for s in TimeSlot
        },
    )


def _wf_select_work_date(upload_widget_id: str, date_options: list[date]) -> date | None:
    day_commit_key = f'aa_day_committed_{upload_widget_id}'
    commit_key = slice_commit_key(upload_widget_id)
    committed_day_raw = st.session_state.get(day_commit_key)
    if committed_day_raw:
        selected_date = date.fromisoformat(committed_day_raw)
        with st.container(border=True):
            render_step_panel(
                f'Step 1: Selected date — {selected_date.isoformat()}',
                'Date is locked for this run.',
            )
            st.caption(
                'Changing the date clears your selected shift and any draft work tied to the previous date '
                'for this upload.'
            )
            if st.button('Change date', key=f'day_change_{upload_widget_id}'):
                st.session_state.pop(day_commit_key, None)
                st.session_state.pop(commit_key, None)
                st.rerun()
        return selected_date
    with st.container(border=True):
        render_step_panel(
            'Step 1: Select a date',
            'Choose the calendar day you are staffing from this CSV.',
        )
        st.caption('Only dates that appear in the uploaded schedule are listed.')
        pick_date = st.selectbox(
            'Date',
            options=date_options,
            key=f'schedule_date_{upload_widget_id}',
        )
        if st.button('Continue', type='primary', key=f'day_continue_{upload_widget_id}'):
            st.session_state[day_commit_key] = pick_date.isoformat()
            st.session_state.pop(commit_key, None)
            st.rerun()
        st.markdown(
            '<div class="aa-empty">Continue to set day-wide call-offs and overtime.</div>',
            unsafe_allow_html=True,
        )
    return None


def _wf_load_tasks_and_profiles() -> tuple[list, dict, list] | None:
    if not database_url_configured():
        st.error(
            'Assignment Engine requires a database (tasks + profiles + overrides are DB-backed). '
            'Configure `DATABASE_URL` and run migrations.'
        )
        return None
    with session_scope() as session:
        task_list = list_tasks(session)
        profiles_map = load_tech_profiles_by_name(session)
        techs_all = list_technicians(session)
    if not task_list:
        st.info(
            'No tasks in the catalog yet. Add tasks on **Task Catalog** — or load demo data '
            'from the panel above to seed a sample catalog and roster in one click.'
        )
        return None
    return task_list, profiles_map, techs_all


def _wf_seed_day_override_session(keys: _DayOverrideKeys, selected_date: date) -> None:
    if (
        keys.call_off_key not in st.session_state
        or any(k not in st.session_state for k in keys.overtime_keys.values())
    ):
        with session_scope() as session:
            ov = load_draft_overrides_for_slice(session, selected_date, TimeSlot.AM)
        st.session_state.setdefault(keys.call_off_key, list(ov['call_off_tech_ids']))
        overtime_by_slot = ov.get('overtime_tech_ids_by_slot', {})
        for s in TimeSlot:
            st.session_state.setdefault(
                keys.overtime_keys[s],
                list(overtime_by_slot.get(s.name, [])),
            )


def _wf_render_step_2_day_overrides(
    *,
    schedule_rows: list,
    selected_date: date,
    techs_all: list,
    profiles_map: dict,
    do_keys: _DayOverrideKeys,
) -> bool:
    call_off_key = do_keys.call_off_key
    override_commit_key = do_keys.override_commit_key
    override_overwrite_confirm_key = do_keys.override_overwrite_confirm_key
    day_widget_reset_flag = do_keys.day_widget_reset_flag
    day_context = do_keys.day_context
    overtime_keys = do_keys.overtime_keys

    call_off_ids: list[str] = list(st.session_state.get(call_off_key, []))
    overtime_ids_by_slot: dict[TimeSlot, list[str]] = {
        s: list(st.session_state.get(overtime_keys[s], []))
        for s in TimeSlot
    }
    tech_by_id = {t.tech_id: t for t in techs_all}
    overrides_committed = bool(st.session_state.get(override_commit_key, False))
    if overrides_committed:
        with st.container(border=True):
            render_step_panel(
                f'Step 2: Day-wide overrides — {selected_date.isoformat()}',
                'Saved for this date across all shifts (AM / MID / PM).',
            )
            st.caption(
                'Call-offs remove someone for the whole day. Overtime adds someone for the shift you pick. '
                'Stored in the database—same values return in a new session or after re-uploading this CSV.'
            )
            saved_rows: list[dict[str, str]] = []
            for tid in sorted(call_off_ids):
                tech_label = tech_by_id[tid].tech_name if tid in tech_by_id else tid
                saved_rows.append({'type': 'Call-off (all shifts)', 'technician': tech_label, 'tech_id': tid})
            for s in TimeSlot:
                for tid in sorted(overtime_ids_by_slot[s]):
                    tech_label = tech_by_id[tid].tech_name if tid in tech_by_id else tid
                    saved_rows.append({'type': f'Overtime ({s.value})', 'technician': tech_label, 'tech_id': tid})
            if saved_rows:
                st.dataframe(pd.DataFrame(saved_rows), use_container_width=True, hide_index=True)
            else:
                st.caption('No day-wide overrides (schedule CSV rules only).')
            render_context_chips(
                [
                    ('Call-offs', str(len(call_off_ids))),
                    ('OT AM', str(len(overtime_ids_by_slot[TimeSlot.AM]))),
                    ('OT MID', str(len(overtime_ids_by_slot[TimeSlot.MID]))),
                    ('OT PM', str(len(overtime_ids_by_slot[TimeSlot.PM]))),
                ]
            )
            if st.button('Change', key=f'change_day_overrides_{day_context}'):
                st.session_state[override_commit_key] = False
                st.session_state.pop(override_overwrite_confirm_key, None)
                st.rerun()
        return True
    with session_scope() as session:
        stored_ov = load_draft_overrides_for_slice(session, selected_date, TimeSlot.AM)
    stored_call_off_ids = list(stored_ov['call_off_tech_ids'])
    stored_overtime_by_slot = {
        s: list(stored_ov.get('overtime_tech_ids_by_slot', {}).get(s.name, []))
        for s in TimeSlot
    }
    has_stored_day_overrides = bool(
        stored_call_off_ids or any(stored_overtime_by_slot[s] for s in TimeSlot)
    )
    with st.expander('Step 2: Day-wide overrides (all shifts)', expanded=True):
        st.caption(
            'Select call-offs for the full day, then add overtime per shift if someone works outside their '
            'usual CSV availability. **Clear** removes saved overrides for this date. **Continue** locks '
            'this step so you can pick a shift next.'
        )
        if st.session_state.pop(day_widget_reset_flag, False):
            st.session_state.pop(f'calloff_pick_{day_context}', None)
            for s in TimeSlot:
                st.session_state.pop(f'overtime_pick_{day_context}_{s.name.lower()}', None)

        day_scheduled_rows = [
            r
            for r in schedule_rows
            if r.work_date == selected_date
            and r.staffing_status != Staffing_Status.CALL_OFF
            and (r.available_AM or r.available_MID or r.available_PM)
        ]
        day_base_ids = sorted({tech_id_for_row(r, profiles_map) for r in day_scheduled_rows})
        all_overtime_ids = {tid for ids in overtime_ids_by_slot.values() for tid in ids}
        calloff_options = sorted(set(day_base_ids) | set(call_off_ids) | all_overtime_ids)
        call_off_pick = st.multiselect(
            'Mark call-off for selected date (applies to AM/MID/PM)',
            options=calloff_options,
            default=call_off_ids,
            key=f'calloff_pick_{day_context}',
            format_func=lambda tid, _tb=tech_by_id: _format_tech_id_label(_tb, tid),
        )
        overtime_options = sorted(t.tech_id for t in techs_all if t.tech_id not in day_base_ids)
        overtime_pick_by_slot: dict[TimeSlot, list[str]] = {}
        st.caption('Overtime is selected per shift (AM/MID/PM).')
        for s in TimeSlot:
            pick = st.multiselect(
                f'Overtime technicians for {s.value}',
                options=[tid for tid in overtime_options if tid not in call_off_pick],
                default=[tid for tid in overtime_ids_by_slot[s] if tid not in call_off_pick],
                key=f'overtime_pick_{day_context}_{s.name.lower()}',
                format_func=lambda tid: f'{tech_by_id[tid].tech_name} ({tid})',
            )
            overtime_pick_by_slot[s] = pick
        picked_sig = normalized_day_override_signature(call_off_pick, overtime_pick_by_slot)
        stored_sig = normalized_day_override_signature(stored_call_off_ids, stored_overtime_by_slot)
        has_day_override_changes = picked_sig != stored_sig
        if not has_day_override_changes:
            st.session_state.pop(override_overwrite_confirm_key, None)

        def _persist_day_overrides(*, lock_step: bool, flash_msg: str, toast_msg: str | None) -> None:
            with session_scope() as session:
                replace_draft_day_availability_overrides(
                    session,
                    selected_date,
                    call_off_tech_ids=call_off_pick,
                    overtime_tech_ids_by_slot=cast(
                        dict[TimeSlot, Iterable[str]], overtime_pick_by_slot
                    ),
                )
            st.session_state[call_off_key] = list(call_off_pick)
            for _slot in TimeSlot:
                st.session_state[overtime_keys[_slot]] = list(overtime_pick_by_slot[_slot])
            if lock_step:
                st.session_state[override_commit_key] = True
            st.session_state[_SS_DAY_OVERRIDE_FLASH] = flash_msg
            st.session_state.pop(override_overwrite_confirm_key, None)
            if toast_msg:
                st.toast(toast_msg, icon='✅')
            st.rerun()

        clear_col, continue_col = st.columns((1, 2))
        with clear_col:
            if st.button('Clear', key=f'clear_day_overrides_{day_context}'):
                try:
                    with session_scope() as session:
                                replace_draft_day_availability_overrides(
                                    session,
                                    selected_date,
                                    call_off_tech_ids=[],
                                    overtime_tech_ids_by_slot=cast(
                                        dict[TimeSlot, Iterable[str]],
                                        {s: [] for s in TimeSlot},
                                    ),
                                )
                    st.session_state[call_off_key] = []
                    for s in TimeSlot:
                        st.session_state[overtime_keys[s]] = []
                    st.session_state[day_widget_reset_flag] = True
                    st.session_state.pop(override_overwrite_confirm_key, None)
                    st.session_state[_SS_DAY_OVERRIDE_FLASH] = (
                        f'Day overrides cleared for {selected_date.isoformat()}.'
                    )
                    st.toast('Day overrides cleared.', icon='✅')
                    st.rerun()
                except Exception as e:
                    st.error(f'Could not clear day overrides: {e}')
        with continue_col:
            if st.button('Continue', key=f'continue_day_overrides_{day_context}'):
                if has_stored_day_overrides and has_day_override_changes:
                    st.session_state[override_overwrite_confirm_key] = True
                    st.rerun()
                try:
                    _persist_day_overrides(
                        lock_step=True,
                        flash_msg=f'Day overrides saved and locked for {selected_date.isoformat()}.',
                        toast_msg=None,
                    )
                except Exception as e:
                    st.error(f'Could not continue with day overrides: {e}')

        needs_overwrite_confirmation = bool(st.session_state.get(override_overwrite_confirm_key, False))
        if needs_overwrite_confirmation and has_stored_day_overrides and has_day_override_changes:
            st.warning(
                'You changed saved overrides for this date. '
                'Do you want to overwrite the currently stored call-off/overtime selections?'
            )
            y_col, n_col = st.columns((1, 1))
            with y_col:
                if st.button('Overwrite', key=f'confirm_overwrite_day_overrides_{day_context}'):
                    try:
                        _persist_day_overrides(
                            lock_step=True,
                            flash_msg=(
                                f'Day overrides overwritten and locked for {selected_date.isoformat()}.'
                            ),
                            toast_msg='Day overrides overwritten.',
                        )
                    except Exception as e:
                        st.error(f'Could not overwrite day overrides: {e}')
            with n_col:
                if st.button('Cancel', key=f'cancel_overwrite_day_overrides_{day_context}'):
                    st.session_state.pop(override_overwrite_confirm_key, None)
                    st.rerun()
    st.caption('Use **Continue** to lock Step 2, then pick a shift in Step 3.')
    return False


def _wf_render_step_3_select_shift(
    upload_widget_id: str,
    selected_date: date,
    commit_key: str,
) -> TimeSlot | None:
    committed_raw = st.session_state.get(commit_key)
    if committed_raw and committed_raw[0] == selected_date.isoformat():
        selected_time_slot = TimeSlot[committed_raw[1]]
        with st.container(border=True):
            render_step_panel(
                f'Step 3: Shift — {selected_time_slot.value}',
                'Locked for headcounts, pre-assignments, and publish for this date.',
            )
            st.caption(
                'Only technicians available on this shift (after Step 2 overrides) appear in Steps 4–6. '
                'Changing shift clears draft rows and manual assignments for the previous shift on this upload.'
            )
            if st.button('Change shift', key=f'slice_change_{upload_widget_id}'):
                old_ctx = allocation_context(upload_widget_id, selected_date, selected_time_slot)
                st.session_state.pop(f'draft_assignments_{old_ctx}', None)
                st.session_state.pop(f'aa_last_gen_sig_{old_ctx}', None)
                st.session_state.pop(f'aa_manual_assignments_{old_ctx}', None)
                st.session_state.pop(f'aa_manual_step_committed_{old_ctx}', None)
                st.session_state.pop(commit_key, None)
                st.rerun()
        return selected_time_slot
    with st.container(border=True):
        render_step_panel(
            'Step 3: Select shift',
            'AM, MID, or PM for the date you chose in Step 1.',
        )
        st.caption(
            'Technicians must be marked available for this band on the schedule row. '
            'CSV `call_off` rows stay excluded even if shift flags are true.'
        )
        pick_slot = st.selectbox(
            'Shift',
            options=list(TimeSlot),
            format_func=lambda slot: slot.value,
            key=f'schedule_time_slot_{upload_widget_id}',
            help='Only technicians marked available for this shift on the selected date are assignable. '
            'Rows with `staffing_status=call_off` are excluded even if shift flags are true.',
        )
        if st.button('Continue', type='primary', key=f'slice_continue_{upload_widget_id}'):
            st.session_state[commit_key] = (selected_date.isoformat(), pick_slot.name)
            st.rerun()
        st.markdown(
            '<div class="aa-empty">Continue to see who is available and set task counts.</div>',
            unsafe_allow_html=True,
        )
    return None


def _wf_render_step_4_available_pool(bundle: _PostShiftBundle) -> None:
    with st.container(border=True):
        render_step_panel(
            f'Step 4: Available technicians ({bundle.slot_label})',
            f'{bundle.selected_date.isoformat()} — who can be assigned after your CSV and Step 2 rules.',
        )
        st.caption(
            'Starts from the schedule row for this date and shift, then applies call-offs and overtime from Step 2. '
            'This count is the ceiling for task headcounts in Step 5. Draft rows for this date/shift reload from '
            'the database when you come back.'
        )
        render_context_chips(
            [
                ('Date', bundle.selected_date.isoformat()),
                ('Shift', bundle.slot_label),
                ('Call-offs (day)', str(len(bundle.call_off_ids))),
                ('OT this shift', str(len(bundle.overtime_ids))),
            ]
        )
        st.markdown(
            f'There are **{bundle.pool_size}** technicians currently available for assignment on this date and shift.'
        )
        if bundle.available_techs:
            with st.expander('Names list', expanded=False):
                st.markdown('\n'.join(f'- {name}' for name in bundle.available_techs))
        else:
            st.markdown(
                '<div class="aa-empty">No available technicians after applying day-wide overrides for this shift.</div>',
                unsafe_allow_html=True,
            )


def _wf_render_step_5_headcounts(bundle: _PostShiftBundle) -> _HeadcountControls:
    b = bundle
    manual_assignments = list(st.session_state.get(b.manual_key, []))
    slice_ctx = b.slice_ctx
    pool_size = b.pool_size

    if database_url_configured():
        with session_scope() as session:
            db_draft = load_draft_assignments_for_slice(session, b.selected_date, b.selected_time_slot)
        if db_draft:
            st.session_state[b.draft_key] = list(db_draft)

    keys_by_task: list[tuple[str, str]] = [
        (t.task_id, f'task_count_{t.task_id}_{slice_ctx}') for t in b.task_list
    ]
    # Persistent backup of the task counts, decoupled from the number_input widget
    # keys. Streamlit garbage-collects widget-key session state after the widget
    # stops rendering (e.g. once Step 5 is locked), so we need to preserve the
    # committed counts outside the widget namespace or they silently reset to
    # defaults on later reruns and disable Generate draft in Step 7.
    counts_backup_key = f'aa_task_counts_backup_{slice_ctx}'

    reset_requested = bool(st.session_state.pop(b.reset_defaults_flag, False))
    if not reset_requested:
        backup = st.session_state.get(counts_backup_key) or {}
        for tid, wk in keys_by_task:
            if wk not in st.session_state and tid in backup:
                st.session_state[wk] = int(backup[tid])

    first_render = any(wk not in st.session_state for _, wk in keys_by_task)
    current_total = sum(int(st.session_state.get(wk, 0)) for _, wk in keys_by_task)
    overshoot = current_total > pool_size

    scaled_from_defaults = False
    forced_rebalance = False
    if reset_requested or first_render:
        distributed = distribute_defaults_across_pool(
            [(t.task_id, int(t.default_count)) for t in b.task_list],
            pool_size,
        )
        total_default = sum(int(t.default_count) for t in b.task_list)
        scaled_from_defaults = total_default > pool_size
        for tid, wk in keys_by_task:
            st.session_state[wk] = int(distributed.get(tid, 0))
        if reset_requested:
            forced_rebalance = True
    elif overshoot:
        distributed = distribute_defaults_across_pool(
            [(tid, int(st.session_state.get(wk, 0))) for tid, wk in keys_by_task],
            pool_size,
        )
        for tid, wk in keys_by_task:
            st.session_state[wk] = int(distributed.get(tid, 0))
        forced_rebalance = True

    if forced_rebalance and st.session_state.get(b.headcount_commit_key):
        st.session_state[b.headcount_commit_key] = False
        st.session_state[b.manual_step_commit_key] = False

    task_requests: list[TaskRequest] = [
        TaskRequest(
            task_id=task.task_id,
            task_name=task.task_name,
            task_count=int(st.session_state.get(keys_by_task[idx][1], 0)),
            task_date=b.selected_date,
            time_slot=b.selected_time_slot,
        )
        for idx, task in enumerate(b.task_list)
    ]
    st.session_state[counts_backup_key] = {
        tid: int(st.session_state.get(wk, 0)) for tid, wk in keys_by_task
    }
    residual_plan = build_residual_plan_after_manual_assignments(
        task_requests=task_requests,
        effective_pool=b.effective_pool,
        manual_assignments=manual_assignments,
        tech_profiles_by_name=b.profiles_map,
    )
    assigned_total = sum(tr.task_count for tr in task_requests)
    can_generate = assigned_total == pool_size and not residual_plan.errors

    committed = bool(st.session_state.get(b.headcount_commit_key, False))

    if committed:
        task_requests = _wf_render_step_5_locked(
            bundle=b,
            task_requests=task_requests,
        )
    else:
        task_requests = _wf_render_step_5_editable(
            bundle=b,
            keys_by_task=keys_by_task,
            residual_plan=residual_plan,
            can_generate=can_generate,
            scaled_from_defaults=scaled_from_defaults,
            overshoot=overshoot and not (reset_requested or first_render),
        )

    return _HeadcountControls(
        can_generate=can_generate,
        residual_plan=residual_plan,
        task_requests=task_requests,
    )


def _wf_render_step_5_editable(
    *,
    bundle: _PostShiftBundle,
    keys_by_task: list[tuple[str, str]],
    residual_plan: ResidualPlan,
    can_generate: bool,
    scaled_from_defaults: bool,
    overshoot: bool,
) -> list[TaskRequest]:
    b = bundle
    slice_ctx = b.slice_ctx
    pool_size = b.pool_size
    with st.container(border=True):
        render_step_panel(
            'Step 5: Task headcounts',
            f'Task counts must sum to **{pool_size}** (one row per available technician).',
        )
        st.caption(
            'Adjust counts until **Remaining slots** is zero, then **Continue** to lock them in.'
        )

        if scaled_from_defaults:
            st.caption(
                f'Catalog defaults sum to more than **{pool_size}** available technicians, so the starting '
                'counts were scaled down to fit. Adjust any row below and the other maxes update.'
            )
        elif overshoot:
            st.caption(
                'Previous counts exceeded the current pool (likely because of a new call-off or a shift change). '
                'They were rebalanced to fit — review the rows below before continuing.'
            )

        task_requests: list[TaskRequest] = []
        for idx, task in enumerate(b.task_list):
            wkey = keys_by_task[idx][1]

            other_sum = 0
            for j, (_, ok) in enumerate(keys_by_task):
                if j == idx:
                    continue
                other_sum += int(st.session_state.get(ok, 0))

            max_for_task = max(0, pool_size - other_sum)

            cur = min(max(int(st.session_state[wkey]), 0), max_for_task)
            if cur != int(st.session_state[wkey]):
                st.session_state[wkey] = cur

            count = st.number_input(
                label=f'{task.task_name} count',
                min_value=0,
                max_value=max_for_task,
                step=1,
                key=wkey,
                help=(
                    'Headcount for this task. The max is limited so the total across tasks never '
                    f'exceeds **{pool_size}** available technicians (currently up to **{max_for_task}** '
                    'for this task given the other rows).'
                ),
            )

            task_requests.append(
                TaskRequest(
                    task_id=task.task_id,
                    task_name=task.task_name,
                    task_count=count,
                    task_date=b.selected_date,
                    time_slot=b.selected_time_slot,
                )
            )

        assigned_total = sum(tr.task_count for tr in task_requests)
        remaining = pool_size - assigned_total
        m_col, reset_col = st.columns((3, 1))
        with m_col:
            st.metric('Remaining slots', remaining)
        with reset_col:
            st.write('')
            if st.button(
                'Reset defaults',
                key=f'task_reset_defaults_{slice_ctx}',
                help='Reset each task count to its catalog default (scaled down proportionally when the pool is tight).',
            ):
                st.session_state[b.reset_defaults_flag] = True
                st.session_state[b.headcount_commit_key] = False
                st.session_state[b.manual_step_commit_key] = False
                st.rerun()
        recomputed_can_generate = assigned_total == pool_size and not residual_plan.errors

        rows = st.session_state.get(b.draft_key)
        if (
            rows
            and b.gen_sig_key in st.session_state
            and st.session_state.get(b.gen_sig_key) != task_count_signature(task_requests)
        ):
            st.warning(
                'Task headcounts changed since this draft was generated. Run **Generate draft** again '
                'to refresh the draft.'
            )

        if not recomputed_can_generate:
            if assigned_total != pool_size:
                st.warning('Allocate every available technician to a task (Remaining slots = 0) before continuing.')
            for err in residual_plan.errors:
                if assigned_total != pool_size and err.startswith('Residual mismatch:'):
                    continue
                st.warning(err)

        st.caption(
            'For how auto-placement works—preferences, **published** history, and fairness—open '
            '**About this app** in the sidebar and read **How auto-placement works**. '
            'Regenerate the draft after you change headcounts or who is in the pool.'
        )

        if st.button(
            'Continue',
            type='primary',
            key=f'headcount_continue_{slice_ctx}',
            disabled=not (can_generate and recomputed_can_generate),
            help='Lock these counts and move to manual assignments.',
        ):
            st.session_state[b.headcount_commit_key] = True
            st.rerun()
        if not (can_generate and recomputed_can_generate):
            st.caption('**Continue** unlocks once Remaining slots = 0 and there are no warnings above.')

    return task_requests


def _wf_render_step_5_locked(
    *,
    bundle: _PostShiftBundle,
    task_requests: list[TaskRequest],
) -> list[TaskRequest]:
    b = bundle
    slice_ctx = b.slice_ctx
    with st.container(border=True):
        render_step_panel(
            'Step 5: Task headcounts — locked',
            'Counts are locked for this run. Use **Change** to edit them (this also re-opens Step 6).',
        )
        summary_rows = [
            {'Task': tr.task_name, 'Count': int(tr.task_count)}
            for tr in task_requests
            if int(tr.task_count) > 0
        ]
        if summary_rows:
            st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)
        else:
            st.caption('No tasks have headcount assigned for this shift.')
        total = sum(tr.task_count for tr in task_requests)
        st.metric('Total slots', total)
        if st.button('Change', key=f'headcount_change_{slice_ctx}'):
            st.session_state[b.headcount_commit_key] = False
            st.session_state[b.manual_step_commit_key] = False
            st.rerun()
    return task_requests


def _manual_display_rows(
    manual_assignments: Sequence[Assignment],
    *,
    profiles_map: dict,
    tech_by_id: dict[str, Tech],
) -> list[dict[str, str]]:
    '''
    Build the display rows for the Step 6 / Step 7 manual-assignment tables, adding
    an explicit "eligibility" column so operators can see at a glance which rows
    bypassed the catalog gate via an explicit override.
    '''
    rows: list[dict[str, str]] = []
    for a in manual_assignments:
        tech = tech_by_id.get(a.technician_id)
        currently_ineligible = (
            tech is not None and not is_tech_eligible_for_catalog_task(tech, a.catalog_task_id)
        )
        if a.eligibility_overridden or currently_ineligible:
            elig_label = 'Overridden (ineligible)'
        else:
            elig_label = 'OK'
        rows.append(
            {
                'task': a.task_name,
                'technician': tech_id_to_display_name(a.technician_id, profiles_map),
                'tech_id': a.technician_id,
                'eligibility': elig_label,
            }
        )
    return rows


def _wf_render_step_6_manual(bundle: _PostShiftBundle) -> bool:
    b = bundle
    manual_assignments = list(st.session_state.get(b.manual_key, []))
    manual_step_committed = bool(st.session_state.get(b.manual_step_commit_key, False))
    slice_ctx = b.slice_ctx
    pending_override_key = f'aa_manual_pending_override_{slice_ctx}'
    if manual_step_committed:
        with st.container(border=True):
            render_step_panel(
                f'Step 6: Manual assignments — {b.selected_time_slot.value}',
                'Locked. Automatic placement will not change these rows.',
            )
            st.caption(
                'Each technician can appear only once. Rows save to the draft as you edit. '
                'Use **Change** to add, remove, or clear before generating.'
            )
            if manual_assignments:
                display_rows = _manual_display_rows(
                    manual_assignments,
                    profiles_map=b.profiles_map,
                    tech_by_id=b.tech_by_id,
                )
                man_df = pd.DataFrame(display_rows)
                st.dataframe(man_df, use_container_width=True, hide_index=True)
                n_overridden = sum(1 for a in manual_assignments if a.eligibility_overridden)
                if n_overridden:
                    st.warning(
                        f'**{n_overridden}** manual row(s) bypass catalog eligibility. '
                        'These technicians are not certified for the assigned task — the operator '
                        'confirmed this explicitly (e.g. training / shadowing). The override is '
                        'persisted for audit.'
                    )
            else:
                st.caption('No manual assignments — everyone will be placed from task counts.')
            if st.button('Change', key=f'manual_change_{slice_ctx}'):
                st.session_state[b.manual_step_commit_key] = False
                st.session_state.pop(pending_override_key, None)
                st.rerun()
        return True
    with st.container(border=True):
        render_step_panel(
            f'Step 6: Manual assignments ({b.selected_time_slot.value})',
            'Optional: fix specific people to tasks before automatic placement.',
        )
        st.caption(
            'Choose a task and technician, then **Add**. The dropdown defaults are not an assignment until you add.'
        )
        effective_ids = sorted({tech_id_for_row(r, b.profiles_map) for r in b.effective_pool})
        used_manual_ids = {a.technician_id for a in manual_assignments}
        manual_task = st.selectbox(
            'Task',
            options=b.task_list,
            format_func=lambda t: t.task_name,
            key=f'manual_task_pick_{slice_ctx}',
        )
        manual_tech_options = [tid for tid in effective_ids if tid not in used_manual_ids]
        manual_tech = None
        if manual_tech_options:
            manual_tech = st.selectbox(
                'Technician',
                options=manual_tech_options,
                key=f'manual_tech_pick_{slice_ctx}',
                format_func=lambda tid, _tb=b.tech_by_id: _format_tech_id_label(_tb, tid),
            )
        else:
            st.caption('All available technicians for this shift are already in the list below.')

        pending_override = st.session_state.get(pending_override_key)

        def _commit_manual_assignment(*, overridden: bool) -> None:
            assert manual_task is not None and manual_tech is not None
            manual_assignments.append(
                Assignment(
                    task_name=manual_task.task_name,
                    catalog_task_id=manual_task.task_id,
                    technician_id=manual_tech,
                    date_assigned=b.selected_date,
                    time_slot=b.selected_time_slot,
                    eligibility_overridden=overridden,
                )
            )
            with session_scope() as session:
                replace_draft_manual_assignments_for_slice(
                    session, b.selected_date, b.selected_time_slot, manual_assignments
                )
            st.session_state[b.manual_key] = list(manual_assignments)
            st.session_state.pop(pending_override_key, None)
            toast_msg = (
                'Manual override saved (eligibility bypassed).'
                if overridden
                else 'Manual assignment saved.'
            )
            st.toast(toast_msg, icon='✅')
            st.rerun()

        if st.button(
            'Add',
            key=f'manual_add_{slice_ctx}',
            disabled=(
                (not manual_tech_options)
                or (manual_tech is None)
                or pending_override is not None
            ),
        ):
            if manual_task is not None and manual_tech is not None:
                tech = b.tech_by_id.get(manual_tech)
                eligible = tech is None or is_tech_eligible_for_catalog_task(
                    tech, manual_task.task_id
                )
                if eligible:
                    try:
                        _commit_manual_assignment(overridden=False)
                    except Exception as e:
                        st.error(f'Could not add manual assignment: {e}')
                else:
                    st.session_state[pending_override_key] = {
                        'task_id': manual_task.task_id,
                        'task_name': manual_task.task_name,
                        'tech_id': manual_tech,
                    }
                    st.rerun()

        if pending_override is not None:
            pending_tech = b.tech_by_id.get(pending_override['tech_id'])
            pending_tech_label = (
                pending_tech.tech_name if pending_tech is not None else pending_override['tech_id']
            )
            st.warning(
                f'**{pending_tech_label}** is not certified for **{pending_override["task_name"]}** '
                '(the catalog marks them as ineligible). '
                'Assign anyway only if this is a training / shadowing placement — the override will '
                'be recorded in the audit log.'
            )
            ov_col, cancel_col = st.columns((1, 1))
            with ov_col:
                if st.button(
                    'Override eligibility and add',
                    key=f'manual_override_confirm_{slice_ctx}',
                    type='primary',
                ):
                    try:
                        _commit_manual_assignment(overridden=True)
                    except Exception as e:
                        st.error(f'Could not add manual assignment: {e}')
            with cancel_col:
                if st.button('Cancel', key=f'manual_override_cancel_{slice_ctx}'):
                    st.session_state.pop(pending_override_key, None)
                    st.rerun()

        if manual_assignments:
            display_rows = _manual_display_rows(
                manual_assignments,
                profiles_map=b.profiles_map,
                tech_by_id=b.tech_by_id,
            )
            man_df = pd.DataFrame(display_rows)
            st.dataframe(man_df, use_container_width=True, hide_index=True)
            remove_idx = st.selectbox(
                'Remove assignment row',
                options=list(range(len(manual_assignments))),
                format_func=lambda i: f'{manual_assignments[i].task_name} — {manual_assignments[i].technician_id}',
                key=f'manual_remove_pick_{slice_ctx}',
            )
            r1, r2 = st.columns((1, 1))
            with r1:
                if st.button('Remove', key=f'manual_remove_btn_{slice_ctx}'):
                    try:
                        manual_assignments.pop(remove_idx)
                        with session_scope() as session:
                            replace_draft_manual_assignments_for_slice(
                                session, b.selected_date, b.selected_time_slot, manual_assignments
                            )
                        st.session_state[b.manual_key] = list(manual_assignments)
                        st.session_state.pop(pending_override_key, None)
                        st.toast('Manual assignment removed.', icon='✅')
                        st.rerun()
                    except Exception as e:
                        st.error(f'Could not remove manual assignment: {e}')
            with r2:
                if st.button('Clear all', key=f'manual_clear_btn_{slice_ctx}'):
                    try:
                        with session_scope() as session:
                            replace_draft_manual_assignments_for_slice(
                                session, b.selected_date, b.selected_time_slot, []
                            )
                        st.session_state[b.manual_key] = []
                        st.session_state.pop(pending_override_key, None)
                        st.toast('Manual assignments cleared.', icon='✅')
                        st.rerun()
                    except Exception as e:
                        st.error(f'Could not clear manual assignments: {e}')
            if st.button(
                'Continue with manual assignments',
                type='primary',
                key=f'manual_continue_with_{slice_ctx}',
                disabled=pending_override is not None,
                help=(
                    'Resolve the pending eligibility override before continuing.'
                    if pending_override is not None
                    else None
                ),
            ):
                st.session_state[b.manual_step_commit_key] = True
                st.rerun()

        if not manual_assignments:
            st.caption(
                'Skip this step? Use **Continue without manual assignments**—the task and technician '
                'dropdowns above are only defaults until you press **Add**.'
            )
        if st.button(
            'Continue without manual assignments',
            type='primary' if not manual_assignments else 'secondary',
            disabled=bool(manual_assignments),
            key=f'manual_continue_without_{slice_ctx}',
            help='Use when the table above is empty. If you added rows, use **Continue with manual assignments**.',
        ):
            st.session_state[b.manual_step_commit_key] = True
            st.rerun()
    st.caption('Finish Step 6 to unlock draft generation below.')
    return False


def _wf_render_step_7_generate_publish(bundle: _PostShiftBundle, hc: _HeadcountControls) -> None:
    b = bundle
    manual_assignments = list(st.session_state.get(b.manual_key, []))
    slice_ctx = b.slice_ctx
    with st.container(border=True):
        render_step_panel(
            'Step 7: Generate draft',
            'Build the suggested assignment for this shift (after any manual rows in Step 6).',
        )
        st.caption(
            'Generate a draft, review it, then publish when ready.'
        )
        with st.expander('Learn more', expanded=False):
            st.markdown(
                '- A **draft** is a preview only and can be discarded safely.\n'
                '- **Publish** saves the official schedule for this date and shift.\n'
                '- Re-publishing the same date/shift replaces the existing published slice '
                '(with a confirmation step).'
            )
        if st.button('Generate draft', disabled=not hc.can_generate, type='primary'):
            try:
                if hc.residual_plan.errors:
                    raise ValueError('; '.join(hc.residual_plan.errors))
                profiles = None
                confirmed: tuple[Assignment, ...] = ()
                if database_url_configured():
                    with session_scope() as session:
                        profiles = load_tech_profiles_by_name(session)
                        confirmed = load_confirmed_assignments_for_scoring(
                            session, b.selected_date, lookback_days=_FAIRNESS_LOOKBACK_DAYS
                        )
                greedy_assignments = assign_tasks(
                    hc.residual_plan.residual_requests,
                    hc.residual_plan.residual_pool,
                    random_seed=_stable_greedy_seed_for_slice(b.slice_ctx),
                    use_greedy_assignment=True,
                    tech_profiles_by_name=profiles,
                    confirmed_assignments=confirmed,
                    greedy_optimization=None,
                    fairness_lookback_days=_FAIRNESS_LOOKBACK_DAYS,
                )
                assignments = list(manual_assignments) + list(greedy_assignments)
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
                            replace_draft_slice(session, b.selected_date, b.selected_time_slot, assignments)
                            replace_draft_manual_assignments_for_slice(
                                session, b.selected_date, b.selected_time_slot, manual_assignments
                            )
                            replace_draft_day_availability_overrides(
                                session,
                                b.selected_date,
                                call_off_tech_ids=b.call_off_ids,
                                overtime_tech_ids_by_slot=cast(
                                    dict[TimeSlot, Iterable[str]], b.overtime_ids_by_slot
                                ),
                            )
                        st.session_state[b.draft_key] = assignments
                        st.session_state[b.gen_sig_key] = task_count_signature(hc.task_requests)
                else:
                    st.session_state[b.draft_key] = assignments
                    st.session_state[b.gen_sig_key] = task_count_signature(hc.task_requests)
                st.success('Draft generated — scroll down in this box to review, then publish or discard draft.')
            except NoEligibleTechnicianError as e:
                st.error(
                    f'No **eligible** technician for task **{e.task_name}** (catalog id `{e.catalog_task_id}`). '
                    'Adjust per-task eligibility on **Technician Profiles** or change headcounts / pool.'
                )
            except Exception as e:
                st.error(f'Could not generate assignments: {e}')

        rows = st.session_state.get(b.draft_key)
        if rows:
            st.markdown(
                f'#### Draft Assignment ({b.selected_date.isoformat()} · {b.selected_time_slot.value})',
            )
            st.caption(
                'Still a **draft** until you publish. Download a CSV if you want to share this preview internally.'
            )

            missing_fk: list[str] = []
            profiles_map_disp: dict = {}
            n_confirmed = 0
            if database_url_configured():
                with session_scope() as session:
                    missing_fk = technician_ids_missing_from_db(session, (a.technician_id for a in rows))
                    profiles_map_disp = load_tech_profiles_by_name(session)
                    n_confirmed = count_confirmed_for_slice(session, b.selected_date, b.selected_time_slot)
            else:
                profiles_map_disp = {}

            disp = [
                {
                    'task': a.task_name,
                    'technician': tech_id_to_display_name(a.technician_id, profiles_map_disp),
                    'tech_id': a.technician_id,
                    'eligibility': (
                        'Overridden (ineligible)' if a.eligibility_overridden else 'OK'
                    ),
                }
                for a in rows
            ]
            n_overridden_draft = sum(1 for a in rows if a.eligibility_overridden)
            if n_overridden_draft:
                st.warning(
                    f'This draft includes **{n_overridden_draft}** manual override row(s) that '
                    'bypass catalog eligibility (training / shadowing). The override flag is saved '
                    'with the published slice for audit.'
                )
            _csv_buf = io.StringIO()
            pd.DataFrame(disp).to_csv(_csv_buf, index=False)
            _draft_spacer_col, _draft_dl_col = st.columns((3, 1))
            with _draft_dl_col:
                st.download_button(
                    label='Download CSV',
                    data=_csv_buf.getvalue().encode('utf-8'),
                    file_name=f'draft_assignments_{b.selected_date}_{b.selected_time_slot.name}.csv',
                    mime='text/csv',
                    key=f'download_assignments_{slice_ctx}',
                    help='This draft only. After publish, use **Published — next steps** or **Assignment history**.',
                )
            st.dataframe(disp, use_container_width=True)

            if missing_fk:
                st.error(
                    '**Cannot confirm:** every assigned **tech_id** must exist in the database. '
                    f'Missing: `{", ".join(missing_fk)}`. Add technician profiles that match these ids '
                    '(schedule names need a matching imported profile).'
                )

            if not database_url_configured():
                st.caption('Configure the database to save drafts and confirm schedules.')
                if st.button(
                    'Discard draft',
                    key=f'discard_draft_{slice_ctx}_nodb',
                    type='secondary',
                    help='Clear this draft from the session. No database is configured.',
                ):
                    handle_discard_draft_click(
                        b.draft_key,
                        b.gen_sig_key,
                        b.selected_date,
                        b.selected_time_slot,
                        session_keys_to_clear=(
                            b.call_off_key,
                            *tuple(b.overtime_keys.values()),
                            b.manual_key,
                            b.manual_step_commit_key,
                        ),
                    )
            else:
                overwrite_ok = True
                if n_confirmed > 0:
                    st.warning(
                        f'This date and shift already has **{n_confirmed}** published row(s). '
                        '**Publish** will **replace** that official slice. '
                        'Assignment history shows the latest published version for this date/shift.'
                    )
                    published_preview: list[dict] = []
                    try:
                        with session_scope() as session:
                            published_preview = load_confirmed_assignment_rows_for_slice(
                                session, b.selected_date, b.selected_time_slot
                            )
                    except Exception as e:
                        st.caption(f'Could not load the current published slice for preview: {e}')
                    if published_preview:
                        with st.expander('Current published assignments (will be replaced)', expanded=False):
                            prev_df = pd.DataFrame(published_preview)
                            st.dataframe(
                                pd.DataFrame(
                                    {
                                        'task': prev_df['task'],
                                        'technician': prev_df['tech_name'],
                                        'tech_id': prev_df['tech_id'],
                                        'shift': prev_df['time_slot'],
                                    }
                                ),
                                use_container_width=True,
                            )
                            prev_buf = io.StringIO()
                            prev_df.to_csv(prev_buf, index=False)
                            st.download_button(
                                label='Download current published slice (CSV)',
                                data=prev_buf.getvalue().encode('utf-8'),
                                file_name=(
                                    f'current_published_{b.selected_date}_{b.selected_time_slot.name}_before_replace.csv'
                                ),
                                mime='text/csv',
                                key=f'pre_replace_published_csv_{slice_ctx}',
                            )
                            st.caption(
                                'After you publish, use **Published — next steps** or **Assignment history**.'
                            )
                    overwrite_ok = st.checkbox(
                        'Replace existing published rows for this shift',
                        key=f'confirm_overwrite_{slice_ctx}',
                    )

                confirm_disabled = (n_confirmed > 0 and not overwrite_ok) or bool(missing_fk)
                st.markdown('##### Review & publish')
                st.caption(
                    '**Discard draft** removes this working copy only (published schedules are unchanged). '
                    '**Publish** saves this table as the official assignment.'
                )
                discard_col, publish_col = st.columns(2, gap='small')
                with discard_col:
                    if st.button(
                        'Discard draft',
                        key=f'discard_draft_{slice_ctx}',
                        type='secondary',
                        help='Remove this draft from the database. Does not change published rows.',
                    ):
                        handle_discard_draft_click(
                            b.draft_key,
                            b.gen_sig_key,
                            b.selected_date,
                            b.selected_time_slot,
                            session_keys_to_clear=(
                                b.call_off_key,
                                *tuple(b.overtime_keys.values()),
                                b.manual_key,
                                b.manual_step_commit_key,
                            ),
                        )
                with publish_col:
                    if st.button(
                        'Publish',
                        disabled=confirm_disabled,
                        key=f'confirm_btn_{slice_ctx}',
                        type='primary',
                    ):
                        if missing_fk:
                            st.error('Fix unknown tech ids before confirming.')
                        else:
                            try:
                                promoted_overrides = 0
                                with session_scope() as session:
                                    confirm_slice(
                                        session,
                                        b.selected_date,
                                        b.selected_time_slot,
                                        rows,
                                    )
                                    promoted_overrides = confirm_draft_overrides_for_slice(
                                        session, b.selected_date, b.selected_time_slot
                                    )
                                st.session_state[_SS_ASSIGN_FLASH] = {
                                    'message': (
                                        '**Schedule published.** The published slice is saved in the database. '
                                        f'Manual override audit rows captured: **{promoted_overrides}**. '
                                        'Day-wide staffing overrides remain editable for this date until you clear them. '
                                        'Use **Published — next steps** below for a CSV, **Dismiss**, or **Start a new run**.'
                                    ),
                                    'warnings': (),
                                }
                                st.session_state[_SS_PUBLISH_CSV_SLICE] = {
                                    'date': b.selected_date.isoformat(),
                                    'slot': b.selected_time_slot.name,
                                }
                                st.session_state.pop(_SS_OFFER_START_NEW_RUN, None)
                                st.session_state.pop(b.draft_key, None)
                                st.session_state.pop(b.gen_sig_key, None)
                                st.session_state.pop(b.manual_key, None)
                                bump_assignment_history_ui_revision()
                                st.toast('Schedule published — slice saved.', icon='✅')
                                st.rerun()
                            except Exception as e:
                                st.error(f'Could not confirm: {e}')


def render_schedule_workflow() -> None:
    render_first_time_setup_expander()
    render_schedule_file_requirements_card()
    uploader_nonce = int(st.session_state.get(_SS_SCHED_NONCE, 0))
    uploaded_file = st.file_uploader(
        'Schedule CSV',
        type=['csv'],
        key=f'schedule_csv_{uploader_nonce}',
        help='Export from your roster tool or use the same template each day. Max size depends on your browser.',
    )

    if uploaded_file is None:
        st.markdown(
            '<div class="aa-empty">Choose a <strong>.csv</strong> file above. After it loads, you will pick a date '
            'and work through the steps in order.</div>',
            unsafe_allow_html=True,
        )
        return

    try:
        df = load_schedule(uploaded_file)
        schedule_rows = parse_schedule(df)

        available_dates = get_all_schedule_dates(schedule_rows)

        if not available_dates:
            st.error('No available dates found in the schedule.')
            return

        upload_widget_id = getattr(uploaded_file, 'file_id', None) or uploaded_file.name
        st.session_state[_SS_LAST_UPLOAD_ID] = upload_widget_id

        date_options = sorted(available_dates)
        selected_date = _wf_select_work_date(upload_widget_id, date_options)
        if selected_date is None:
            return
        render_step_divider()

        loaded = _wf_load_tasks_and_profiles()
        if loaded is None:
            return
        task_list, profiles_map, techs_all = loaded

        do_keys = _day_override_keys(upload_widget_id, selected_date)
        _wf_seed_day_override_session(do_keys, selected_date)
        commit_key = slice_commit_key(upload_widget_id)
        if not _wf_render_step_2_day_overrides(
            schedule_rows=schedule_rows,
            selected_date=selected_date,
            techs_all=techs_all,
            profiles_map=profiles_map,
            do_keys=do_keys,
        ):
            return
        call_off_key = do_keys.call_off_key
        overtime_keys = do_keys.overtime_keys
        call_off_ids: list[str] = list(st.session_state.get(call_off_key, []))
        overtime_ids_by_slot: dict[TimeSlot, list[str]] = {
            s: list(st.session_state.get(overtime_keys[s], []))
            for s in TimeSlot
        }
        tech_by_id = {t.tech_id: t for t in techs_all}
        render_step_divider()
        selected_time_slot = _wf_render_step_3_select_shift(upload_widget_id, selected_date, commit_key)
        if selected_time_slot is None:
            return
        render_step_divider()

        slice_ctx = allocation_context(upload_widget_id, selected_date, selected_time_slot)
        draft_key = f'draft_assignments_{slice_ctx}'
        gen_sig_key = f'aa_last_gen_sig_{slice_ctx}'
        manual_key = f'aa_manual_assignments_{slice_ctx}'
        manual_step_commit_key = f'aa_manual_step_committed_{slice_ctx}'
        headcount_commit_key = f'aa_headcount_committed_{slice_ctx}'
        _reset_defaults_flag = f'_aa_pending_reset_task_counts_{slice_ctx}'
        if manual_key not in st.session_state:
            with session_scope() as session:
                ov = load_draft_overrides_for_slice(session, selected_date, selected_time_slot)
            st.session_state.setdefault(manual_key, list(ov['manual_assignments']))
        manual_assignments: list[Assignment] = list(st.session_state.get(manual_key, []))

        base_available_tech_pool = filter_schedule_rows_available_for_date_and_time_slot(
            schedule_rows, selected_date, selected_time_slot
        )
        overtime_ids: list[str] = list(overtime_ids_by_slot[selected_time_slot])
        overtime_techs = [tech_by_id[tid] for tid in overtime_ids if tid in tech_by_id]
        effective_pool = apply_day_availability_overrides(
            base_pool=base_available_tech_pool,
            selected_date=selected_date,
            tech_profiles_by_name=profiles_map,
            call_off_tech_ids=call_off_ids,
            overtime_techs=overtime_techs,
        )
        available_techs = [row.tech_name for row in effective_pool]
        slot_label = selected_time_slot.value
        pool_size = len(effective_pool)

        bundle = _PostShiftBundle(
            upload_widget_id=upload_widget_id,
            selected_date=selected_date,
            selected_time_slot=selected_time_slot,
            schedule_rows=schedule_rows,
            task_list=task_list,
            profiles_map=profiles_map,
            techs_all=techs_all,
            tech_by_id=tech_by_id,
            call_off_key=call_off_key,
            call_off_ids=call_off_ids,
            overtime_keys=overtime_keys,
            overtime_ids_by_slot=overtime_ids_by_slot,
            commit_key=commit_key,
            slice_ctx=slice_ctx,
            draft_key=draft_key,
            gen_sig_key=gen_sig_key,
            manual_key=manual_key,
            manual_step_commit_key=manual_step_commit_key,
            headcount_commit_key=headcount_commit_key,
            reset_defaults_flag=_reset_defaults_flag,
            manual_assignments=manual_assignments,
            effective_pool=effective_pool,
            pool_size=pool_size,
            slot_label=slot_label,
            available_techs=available_techs,
            overtime_ids=overtime_ids,
        )
        _wf_render_step_4_available_pool(bundle)
        render_step_divider()
        hc = _wf_render_step_5_headcounts(bundle)
        if not st.session_state.get(bundle.headcount_commit_key, False):
            return
        render_step_divider()
        if not _wf_render_step_6_manual(bundle):
            return
        render_step_divider()
        _wf_render_step_7_generate_publish(bundle, hc)

        if not st.session_state.get(bundle.draft_key):
            return

    except Exception as e:
        st.error(f'Could not process the schedule CSV file: {e}')


def render_schedule_section() -> None:
    render_page_header(
        'Assignment Engine',
        'Upload a schedule CSV, complete each step in order, generate a draft, then publish or discard.',
        kicker='Shift allocation',
    )
    render_schedule_workflow()
    render_assignment_engine_outcome_banner()
