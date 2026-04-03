'''Technician profile page: CSV import, form entry, database preview, and deletes.'''

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st
from sqlalchemy import select

from auto_assign.core import load_tech_profile_csv, parse_tech_profiles
from auto_assign.core.task_management import validate_tech_preference_lists
from auto_assign.db import (
    apply_tech_import_plan,
    build_tech_import_plan,
    delete_all_technicians,
    delete_technician,
    list_technicians,
    merge_technician_from_tech,
    session_scope,
    summarize_plan,
    tech_from_technician,
)
from auto_assign.db.models.technician import Technician
from auto_assign.db.tech_import_plan import TechImportRowPlan
from auto_assign.domain.entities import Tech, tech_profile_equals
from auto_assign.domain.enums import DailyPreference
from auto_assign.domain.validators.primitives import normalize_string
from auto_assign.task_config import tasks as task_catalog
from auto_assign.ui.db_state import database_url_configured

_SS_PLAN = '_aa_tech_csv_import_plan'
_SS_FORM_PENDING = '_aa_tech_form_overwrite_pending'


def _tech_to_state(t: Tech) -> dict[str, Any]:
    return {
        'tech_id': t.tech_id,
        'tech_name': t.tech_name,
        'daily_preference': t.daily_preference.value,
        'favorites': list(t.favorites),
        'dislikes': list(t.dislikes),
    }


def _tech_from_state(d: dict[str, Any]) -> Tech:
    return Tech(
        tech_id=d['tech_id'],
        tech_name=d['tech_name'],
        daily_preference=DailyPreference(d['daily_preference']),
        favorites=list(d['favorites']),
        dislikes=list(d['dislikes']),
    )


def _plan_rows_state(plans: list[TechImportRowPlan]) -> list[dict[str, Any]]:
    return [
        {
            'incoming': _tech_to_state(p.incoming),
            'existing': _tech_to_state(p.existing) if p.existing else None,
            'status': p.status,
            'name_owner_tech_id': p.name_owner_tech_id,
        }
        for p in plans
    ]


def _plans_from_state(rows: list[dict[str, Any]]) -> list[TechImportRowPlan]:
    out: list[TechImportRowPlan] = []
    for r in rows:
        ex = r.get('existing')
        out.append(
            TechImportRowPlan(
                incoming=_tech_from_state(r['incoming']),
                existing=_tech_from_state(ex) if ex else None,
                status=r['status'],
                name_owner_tech_id=r.get('name_owner_tech_id'),
            )
        )
    return out


def _technicians_dataframe(techs: list[Tech]) -> pd.DataFrame:
    rows = []
    for t in techs:
        rows.append(
            {
                'tech_id': t.tech_id,
                'tech_name': t.tech_name,
                'daily_preference': t.daily_preference.value,
                'favorites': '; '.join(t.favorites),
                'dislikes': '; '.join(t.dislikes),
            }
        )
    return pd.DataFrame(rows)


def _plan_preview_dataframe(plans: list[TechImportRowPlan]) -> pd.DataFrame:
    rows = []
    for p in plans:
        note = ''
        if p.status == 'name_blocked':
            note = f'Name already used by `{p.name_owner_tech_id}`'
        elif p.status == 'update_pending':
            note = 'Differs from saved profile'
        elif p.status == 'unchanged':
            note = 'No changes'
        elif p.status == 'new':
            note = 'Will be inserted'
        rows.append(
            {
                'tech_id': p.incoming.tech_id,
                'tech_name': p.incoming.tech_name,
                'status': p.status,
                'note': note,
            }
        )
    return pd.DataFrame(rows)


def _render_database_tab(techs: list[Tech]) -> None:
    st.markdown('### Technician Database')
    if not techs:
        st.info('No technicians in the database yet.')
    else:
        st.dataframe(_technicians_dataframe(techs), use_container_width=True, hide_index=True)

    st.markdown('---')
    st.markdown('### Delete tools')
    st.caption('Delete actions also remove assignment rows tied to the removed tech id(s).')

    show_delete_one = st.checkbox('Enable: delete one technician', key='tech_show_delete_one')
    if show_delete_one:
        options = [''] + [t.tech_id for t in techs]
        pick = st.selectbox('tech_id to remove', options=options, key='tech_delete_pick')
        if pick and st.button('Delete selected technician', key='tech_delete_one'):
            try:
                with session_scope() as session:
                    n_a, n_t = delete_technician(session, pick)
                st.success(
                    f'Removed technician `{pick}` '
                    f'({n_a} assignment row(s) deleted, technician row(s) removed: {n_t}).'
                )
                st.rerun()
            except Exception as e:
                st.error(f'Delete failed: {e}')

    show_delete_all = st.checkbox('Enable: delete all technicians', key='tech_show_delete_all')
    if show_delete_all:
        confirm = st.text_input(
            'Type `DELETE ALL TECHNICIANS` to enable deletion.',
            key='tech_delete_all_confirm',
        )
        if st.button(
            'Delete every technician (and all assignments)',
            disabled=confirm != 'DELETE ALL TECHNICIANS',
            key='tech_delete_all_btn',
        ):
            try:
                with session_scope() as session:
                    n_a, n_t = delete_all_technicians(session)
                st.success(f'Removed {n_t} technician profile(s) and {n_a} assignment row(s).')
                st.session_state.pop(_SS_PLAN, None)
                st.session_state.pop(_SS_FORM_PENDING, None)
                st.rerun()
            except Exception as e:
                st.error(f'Delete all failed: {e}')


def _render_csv_tab() -> None:
    st.markdown('### Upload Technician CSV')
    tech_csv = st.file_uploader('Tech profile CSV', type=['csv'], key='tech_profile_csv')

    overwrite = st.checkbox(
        'Overwrite saved profiles when `tech_id` matches but fields differ',
        value=False,
        key='tech_csv_overwrite',
    )
    skip_blocked = st.checkbox(
        'Skip rows blocked by name conflict (import the rest)',
        value=False,
        key='tech_csv_skip_blocked',
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        preview_btn = st.button('Preview (optional)', disabled=tech_csv is None, key='tech_csv_preview')
    with c2:
        submit_btn = st.button('Submit CSV to database', disabled=tech_csv is None, key='tech_csv_submit')
    with c3:
        if st.button('Clear preview', key='tech_csv_clear_preview'):
            st.session_state.pop(_SS_PLAN, None)

    if preview_btn and tech_csv is not None:
        try:
            df = load_tech_profile_csv(tech_csv)
            parsed = parse_tech_profiles(df)
            with session_scope() as session:
                plans = build_tech_import_plan(session, parsed)
            st.session_state[_SS_PLAN] = _plan_rows_state(plans)
            st.success(f'Preview ready for {len(plans)} row(s) after de-duplicating `tech_id`.')
        except Exception as e:
            st.error(f'Preview failed: {e}')

    if _SS_PLAN in st.session_state:
        plans = _plans_from_state(st.session_state[_SS_PLAN])
        counts = summarize_plan(plans)
        c0, c1m, c2m, c3m = st.columns(4)
        with c0:
            st.metric('New', counts['new'])
        with c1m:
            st.metric('Unchanged', counts['unchanged'])
        with c2m:
            st.metric('Updates (pending)', counts['update_pending'])
        with c3m:
            st.metric('Name blocked', counts['name_blocked'])
        st.dataframe(_plan_preview_dataframe(plans), use_container_width=True, hide_index=True)

        if counts['name_blocked'] and not skip_blocked:
            st.warning(
                'Some rows are name-blocked. Reuse existing `tech_id` values in CSV, or enable '
                '`Skip rows blocked by name conflict`.'
            )

    if submit_btn:
        try:
            # Submit always works even without preview.
            df = load_tech_profile_csv(tech_csv)
            parsed = parse_tech_profiles(df)
            with session_scope() as session:
                plans = build_tech_import_plan(session, parsed)
                written, skipped_u, warns = apply_tech_import_plan(
                    session,
                    plans,
                    overwrite_updates=overwrite,
                    skip_name_blocked=skip_blocked,
                )
            st.success(f'{written} row(s) written, {skipped_u} unchanged skipped.')
            for w in warns:
                st.warning(w)
            st.session_state[_SS_PLAN] = _plan_rows_state(plans)
        except ValueError as e:
            st.error(str(e))
        except Exception as e:
            st.error(f'Submit failed: {e}')


def _render_form_tab() -> None:
    st.markdown('### Add or Update Technician')
    task_names = [str(t['task_name']) for t in task_catalog]

    if _SS_FORM_PENDING in st.session_state:
        pending = st.session_state[_SS_FORM_PENDING]
        inc = _tech_from_state(pending['incoming'])
        ex = _tech_from_state(pending['existing'])
        st.warning(
            f'Technician `{inc.tech_id}` already exists with different field values. '
            'Review below, then confirm overwrite or cancel.'
        )
        st.dataframe(
            pd.DataFrame(
                [
                    {**{'source': 'In database'}, **_tech_to_state(ex)},
                    {**{'source': 'Your form'}, **_tech_to_state(inc)},
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
        b1, b2 = st.columns(2)
        with b1:
            if st.button('Overwrite database with form values', key='tech_form_do_overwrite'):
                try:
                    with session_scope() as session:
                        merge_technician_from_tech(session, inc)
                    st.session_state.pop(_SS_FORM_PENDING, None)
                    st.success(f'Updated technician `{inc.tech_id}`.')
                    st.rerun()
                except Exception as e:
                    st.error(f'Save failed: {e}')
        with b2:
            if st.button('Cancel', key='tech_form_cancel_overwrite'):
                st.session_state.pop(_SS_FORM_PENDING, None)
                st.rerun()
        return

    with st.form('single_tech_form'):
        f_tech_id = st.text_input(
            'tech_id',
            placeholder='t-01',
            help='Stable unique id for this technician (primary key). Example: t-01',
        )
        f_name = st.text_input(
            'tech_name',
            placeholder='Jane Doe',
            help='Enter in the format: First Last. This should match schedule `tech_name` values.',
        )
        f_pref = st.selectbox(
            'daily_preference',
            options=list(DailyPreference),
            format_func=lambda e: f'{e.name} ({e.value})',
            help='Consistency: prefers repeating tasks across shifts. Variation: prefers task variety.',
        )
        f_fav = st.multiselect(
            'favorites',
            options=task_names,
            help='Select up to 3 favorite tasks.',
        )
        f_dis = st.multiselect(
            'dislikes',
            options=task_names,
            help='Select up to 3 disliked tasks. Cannot overlap favorites.',
        )
        submitted = st.form_submit_button('Save technician')

    if not submitted:
        return

    if not f_tech_id.strip() or not f_name.strip():
        st.error('`tech_id` and `tech_name` are required.')
        return

    try:
        fav_list, dis_list = validate_tech_preference_lists(f_fav, f_dis)
        tech = Tech(
            tech_id=f_tech_id.strip(),
            tech_name=f_name.strip(),
            daily_preference=f_pref,
            favorites=fav_list,
            dislikes=dis_list,
        )
        with session_scope() as session:
            row = session.get(Technician, tech.tech_id)
            if row is not None:
                existing_tech = tech_from_technician(row)
                if tech_profile_equals(existing_tech, tech):
                    st.info(f'Technician `{tech.tech_id}` is already saved with the same values.')
                else:
                    st.session_state[_SS_FORM_PENDING] = {
                        'incoming': _tech_to_state(tech),
                        'existing': _tech_to_state(existing_tech),
                    }
                    st.rerun()
            else:
                stmt = select(Technician).where(Technician.tech_name == normalize_string(tech.tech_name))
                other = session.scalars(stmt).first()
                if other is not None:
                    st.error(
                        f'The name `{tech.tech_name}` is already used by technician `{other.tech_id}`. '
                        'Use that `tech_id` to edit the profile, or choose a different display name.'
                    )
                else:
                    merge_technician_from_tech(session, tech)
                    st.success(f'Added technician `{tech.tech_id}`.')
    except Exception as e:
        st.error(f'Could not save: {e}')


def render_technician_profiles_page() -> None:
    st.title('Technician Profiles')
    st.caption(
        'Manage technician profiles in Postgres. CSV submit is direct (preview is optional). '
        'Profile columns: `tech_id`, `tech_name`, `daily_preference`, optional `favorites`, `dislikes`.'
    )
    if not database_url_configured():
        st.info(
            'Database URL is not configured. Set `DATABASE_URL` or `POSTGRES_USER`, '
            '`POSTGRES_PASSWORD`, and `POSTGRES_DB` in `.env`, then run `uv run alembic upgrade head`.'
        )
        return

    try:
        with session_scope() as session:
            techs = list_technicians(session)
    except Exception as e:
        st.error(f'Could not load technicians: {e}')
        techs = []

    tabs = st.tabs(['Database', 'Upload CSV', 'Form'])
    with tabs[0]:
        _render_database_tab(techs)
    with tabs[1]:
        _render_csv_tab()
    with tabs[2]:
        _render_form_tab()


# Backward compatibility for any older import path.
render_technicians_expander = render_technician_profiles_page
