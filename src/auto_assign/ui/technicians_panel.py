'''Technician profile import (CSV + form), database preview, and deletes.'''

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from auto_assign.core import (
    load_tech_profile_csv,
    parse_tech_profiles,
    task_names_from_form_field,
)
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
from sqlalchemy import select

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


def render_technicians_expander() -> None:
    with st.expander('Technician profiles (save to database)', expanded=False):
        st.caption(
            'Load validated **domain** technicians into Postgres via CSV upload or form. '
            'Requires `DATABASE_URL` or `POSTGRES_*` in `.env`. '
            'CSV columns: `tech_id`, `tech_name`, `daily_preference`, optional `favorites`, `dislikes` '
            '(semicolon-separated; must match task names in `task_config.py`, no duplicates or overlap, '
            'at most three per list). See `data/sample_tech_profiles.csv`. '
            'Use **Preview import** on CSV to resolve name conflicts and optional overwrites.'
        )
        if not database_url_configured():
            st.info(
                'Database URL is not configured. Set `DATABASE_URL` or `POSTGRES_USER`, '
                '`POSTGRES_PASSWORD`, and `POSTGRES_DB` in `.env`, then run `uv run alembic upgrade head`.'
            )
            return

        tab_db, tab_csv, tab_form = st.tabs(['Database', 'Upload CSV', 'Form'])

        with tab_db:
            st.markdown('**Saved technicians** (Postgres `technicians` table).')
            if st.button('Refresh list', key='tech_db_refresh'):
                pass
            try:
                with session_scope() as session:
                    techs = list_technicians(session)
            except Exception as e:
                st.error(f'Could not load technicians: {e}')
                techs = []

            if not techs:
                st.info('No technicians in the database yet.')
            else:
                st.dataframe(_technicians_dataframe(techs), use_container_width=True, hide_index=True)

            st.divider()
            st.markdown('**Delete one technician**')
            st.caption(
                'Removes this profile and **all assignment rows** (draft or confirmed) that reference '
                'their `tech_id` (required because of foreign-key rules).'
            )
            if techs:
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

            st.divider()
            st.markdown('**Delete all technicians**')
            confirm = st.text_input(
                'Type `DELETE ALL TECHNICIANS` to enable the button below.',
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
                    st.success(
                        f'Removed {n_t} technician profile(s) and {n_a} assignment row(s).'
                    )
                    if _SS_PLAN in st.session_state:
                        del st.session_state[_SS_PLAN]
                    if _SS_FORM_PENDING in st.session_state:
                        del st.session_state[_SS_FORM_PENDING]
                    st.rerun()
                except Exception as e:
                    st.error(f'Delete all failed: {e}')

        with tab_csv:
            tech_csv = st.file_uploader('Tech profile CSV', type=['csv'], key='tech_profile_csv')
            c1, c2 = st.columns(2)
            with c1:
                preview_btn = st.button(
                    'Preview import',
                    disabled=tech_csv is None,
                    key='tech_csv_preview',
                )
            with c2:
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
                c0, c1, c2, c3 = st.columns(4)
                with c0:
                    st.metric('New', counts['new'])
                with c1:
                    st.metric('Unchanged', counts['unchanged'])
                with c2:
                    st.metric('Updates (pending)', counts['update_pending'])
                with c3:
                    st.metric('Name blocked', counts['name_blocked'])
                st.dataframe(_plan_preview_dataframe(plans), use_container_width=True, hide_index=True)

                overwrite = st.checkbox(
                    'Overwrite saved profiles when `tech_id` matches but fields differ',
                    value=False,
                    key='tech_csv_overwrite',
                )
                skip_blocked = st.checkbox(
                    'Skip rows that are blocked by name conflict (import the rest)',
                    value=False,
                    key='tech_csv_skip_blocked',
                )

                if counts['name_blocked'] and not skip_blocked:
                    st.warning(
                        'Some rows are **name blocked**. Either fix the CSV (reuse the existing `tech_id` '
                        'for that person), or enable **Skip rows…** to import everything else.'
                    )

                if st.button('Apply import to database', key='tech_csv_apply'):
                    try:
                        with session_scope() as session:
                            written, skipped_u, warns = apply_tech_import_plan(
                                session,
                                plans,
                                overwrite_updates=overwrite,
                                skip_name_blocked=skip_blocked,
                            )
                        parts = [
                            f'{written} row(s) written',
                            f'{skipped_u} unchanged skipped',
                        ]
                        st.success(', '.join(parts) + '.')
                        for w in warns:
                            st.warning(w)
                        st.session_state.pop(_SS_PLAN, None)
                    except ValueError as e:
                        st.error(str(e))
                    except Exception as e:
                        st.error(f'Apply failed: {e}')

        with tab_form:
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
                            del st.session_state[_SS_FORM_PENDING]
                            st.success(f'Updated technician `{inc.tech_id}`.')
                            st.rerun()
                        except Exception as e:
                            st.error(f'Save failed: {e}')
                with b2:
                    if st.button('Cancel', key='tech_form_cancel_overwrite'):
                        del st.session_state[_SS_FORM_PENDING]
                        st.rerun()
            else:
                with st.form('single_tech_form'):
                    f_tech_id = st.text_input('tech_id', help='Stable id (primary key in DB).')
                    f_name = st.text_input(
                        'tech_name', help='Display name; matches schedule `tech_name`.'
                    )
                    f_pref = st.selectbox(
                        'daily_preference',
                        options=list(DailyPreference),
                        format_func=lambda e: f'{e.name} ({e.value})',
                    )
                    f_fav = st.text_input(
                        'favorites',
                        value='',
                        help='Semicolon-separated task names (optional).',
                    )
                    f_dis = st.text_input(
                        'dislikes',
                        value='',
                        help='Semicolon-separated task names (optional).',
                    )
                    submitted = st.form_submit_button('Save technician')
                if submitted:
                    if not f_tech_id.strip() or not f_name.strip():
                        st.error('`tech_id` and `tech_name` are required.')
                    else:
                        try:
                            fav_raw = task_names_from_form_field(f_fav)
                            dis_raw = task_names_from_form_field(f_dis)
                            fav_list, dis_list = validate_tech_preference_lists(fav_raw, dis_raw)
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
                                        st.info(
                                            f'Technician `{tech.tech_id}` is already saved with the same values.'
                                        )
                                    else:
                                        st.session_state[_SS_FORM_PENDING] = {
                                            'incoming': _tech_to_state(tech),
                                            'existing': _tech_to_state(existing_tech),
                                        }
                                        st.rerun()
                                else:
                                    stmt = select(Technician).where(
                                        Technician.tech_name == normalize_string(tech.tech_name)
                                    )
                                    other = session.scalars(stmt).first()
                                    if other is not None:
                                        st.error(
                                            f'The name `{tech.tech_name}` is already used by technician '
                                            f'`{other.tech_id}`. Use that `tech_id` to edit the profile, '
                                            'or pick a different display name.'
                                        )
                                    else:
                                        merge_technician_from_tech(session, tech)
                                        st.success(f'Added technician `{tech.tech_id}`.')
                        except Exception as e:
                            st.error(f'Could not save: {e}')
