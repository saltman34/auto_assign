'''Technician profile page: CSV import, form entry, database preview, and deletes.'''

from __future__ import annotations

from io import BytesIO
from typing import Any

import pandas as pd
import streamlit as st

from auto_assign.core import load_tech_profile_csv, parse_tech_profiles
from auto_assign.core.task_management import validate_tech_preference_lists
from auto_assign.db import (
    apply_tech_import_plan,
    build_tech_import_plan,
    delete_all_technicians,
    delete_technician,
    find_tech_id_for_normalized_tech_name,
    list_technicians,
    list_tasks,
    load_tech_by_tech_id,
    merge_technician_from_tech,
    session_scope,
    summarize_plan,
)
from auto_assign.db.tech_import_plan import TechImportRowPlan
from auto_assign.domain.entities import Tech, tech_profile_equals
from auto_assign.domain.enums import DailyPreference
from auto_assign.domain.validators.primitives import normalize_string
from auto_assign.ui.db_state import database_url_configured
from auto_assign.ui.page import render_page_header

_SS_PLAN = '_aa_tech_csv_import_plan'
_SS_CSV_SIG = '_aa_tech_csv_sig'
_SS_CSV_UPLOADER_NONCE = '_aa_csv_uploader_nonce'
_SS_IMPORT_FLASH = '_aa_tech_import_flash'
_SS_FORM_PENDING = '_aa_tech_form_overwrite_pending'


def _tech_csv_signature(uploaded: Any) -> str:
    raw = uploaded.getvalue()
    fid = getattr(uploaded, 'file_id', None)
    return f'{fid or uploaded.name}:{len(raw)}'


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


def _render_profiles_tab(techs: list[Tech]) -> None:
    st.markdown('### Profiles')
    st.caption('Saved technician records used for scoring and for mapping schedule names to `tech_id`.')
    if not techs:
        st.markdown(
            '<div class="aa-empty">No technicians saved yet. Use <strong>Bulk Import</strong> or '
            '<strong>Add or Edit Profile</strong> to add profiles.</div>',
            unsafe_allow_html=True,
        )
    else:
        st.dataframe(_technicians_dataframe(techs), use_container_width=True, hide_index=True)


def _render_delete_tab(techs: list[Tech]) -> None:
    st.markdown('### Remove technicians')
    st.caption(
        'Deleting a technician removes their profile and any assignment rows that reference that '
        '`tech_id`. This cannot be undone.'
    )

    st.markdown('#### Delete one technician')
    options = [''] + [t.tech_id for t in techs]
    pick = st.selectbox(
        'Select technician (`tech_id`)',
        options=options,
        key='tech_delete_pick',
        help='Choose a technician to preview their profile before deleting.',
    )
    if pick:
        selected = next(t for t in techs if t.tech_id == pick)
        st.markdown('**Profile to be removed**')
        st.dataframe(_technicians_dataframe([selected]), use_container_width=True, hide_index=True)
        if st.button('Delete this technician', key='tech_delete_one', type='primary'):
            try:
                with session_scope() as session:
                    n_a, n_t = delete_technician(session, pick)
                st.success(
                    f'Removed technician `{pick}` '
                    f'({n_a} assignment row(s) deleted; technician row(s) removed: {n_t}).'
                )
                st.rerun()
            except Exception as e:
                st.error(f'Delete failed: {e}')
    elif techs:
        st.caption('Select a `tech_id` above to preview the profile and enable deletion.')
    else:
        st.info('No technicians to remove.')

    st.markdown('---')
    st.markdown('#### Delete all technicians')
    st.caption('Removes every profile and all assignment rows in the database.')
    confirm = st.text_input(
        'Type `DELETE ALL TECHNICIANS` to enable deletion.',
        key='tech_delete_all_confirm',
    )
    if st.button(
        'Delete every technician (and all assignments)',
        disabled=confirm != 'DELETE ALL TECHNICIANS' or not techs,
        key='tech_delete_all_btn',
    ):
        try:
            with session_scope() as session:
                n_a, n_t = delete_all_technicians(session)
            st.success(f'Removed {n_t} technician profile(s) and {n_a} assignment row(s).')
            st.session_state.pop(_SS_PLAN, None)
            st.session_state.pop(_SS_CSV_SIG, None)
            st.session_state.pop(_SS_FORM_PENDING, None)
            st.rerun()
        except Exception as e:
            st.error(f'Delete all failed: {e}')


def _render_csv_tab(task_names: list[str]) -> None:
    flash = st.session_state.pop(_SS_IMPORT_FLASH, None)
    if flash:
        st.success(flash['message'])
        for w in flash.get('warnings', ()):
            st.warning(w)

    st.markdown('### Bulk import')
    st.caption(
        'Upload a CSV to preview the import. Adjust options, then confirm. After a successful import, '
        'the file clears so you can upload another CSV; the preview only reflects the file currently '
        'selected.'
    )
    if not task_names:
        st.info('Add at least one task in Task Catalog before importing technician preferences.')
        return
    uploader_nonce = int(st.session_state.get(_SS_CSV_UPLOADER_NONCE, 0))
    tech_csv = st.file_uploader(
        'Technician profile CSV',
        type=['csv'],
        key=f'tech_profile_csv_{uploader_nonce}',
    )

    if tech_csv is None:
        st.session_state.pop(_SS_PLAN, None)
        st.session_state.pop(_SS_CSV_SIG, None)
        st.markdown(
            '<div class="aa-empty">Choose a CSV file to load a preview of what will be imported.</div>',
            unsafe_allow_html=True,
        )
        return

    sig = _tech_csv_signature(tech_csv)
    if st.session_state.get(_SS_CSV_SIG) != sig:
        try:
            raw = tech_csv.getvalue()
            df = load_tech_profile_csv(BytesIO(raw))
            parsed = parse_tech_profiles(df, allowed_task_names=task_names)
            with session_scope() as session:
                plans = build_tech_import_plan(session, parsed)
            st.session_state[_SS_PLAN] = _plan_rows_state(plans)
            st.session_state[_SS_CSV_SIG] = sig
        except Exception as e:
            st.session_state.pop(_SS_PLAN, None)
            st.error(f'Could not read this CSV: {e}')
            return

    overwrite = st.checkbox(
        'Overwrite existing profiles when `tech_id` matches but fields differ',
        value=False,
        key='tech_csv_overwrite',
    )
    skip_blocked = st.checkbox(
        'Skip rows blocked by name conflict (import the rest)',
        value=False,
        key='tech_csv_skip_blocked',
    )

    if _SS_PLAN not in st.session_state:
        return

    plans = _plans_from_state(st.session_state[_SS_PLAN])
    counts = summarize_plan(plans)
    st.markdown('#### Import preview')
    st.caption(
        f'{len(plans)} row(s) after de-duplicating `tech_id` (last row wins per id). '
        'Review statuses before confirming.'
    )
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

    blocked_without_skip = counts['name_blocked'] > 0 and not skip_blocked
    if blocked_without_skip:
        st.warning(
            'Some rows are name-blocked. Fix `tech_id` / names in the CSV, or enable '
            '**Skip rows blocked by name conflict** before confirming.'
        )

    confirm_disabled = blocked_without_skip
    if st.button(
        'Confirm import to database',
        disabled=confirm_disabled,
        key='tech_csv_confirm',
        type='primary',
    ):
        try:
            raw = tech_csv.getvalue()
            df = load_tech_profile_csv(BytesIO(raw))
            parsed = parse_tech_profiles(df, allowed_task_names=task_names)
            with session_scope() as session:
                plans_apply = build_tech_import_plan(session, parsed)
                _written, _skipped_u, warns = apply_tech_import_plan(
                    session,
                    plans_apply,
                    overwrite_updates=overwrite,
                    skip_name_blocked=skip_blocked,
                )
            st.session_state[_SS_IMPORT_FLASH] = {
                'message': (
                    'Import confirmed — your previewed changes are saved to the database.\n\n'
                    'Next: open **Profiles** to verify, or **Home** to run the Assignment Engine.'
                ),
                'warnings': tuple(warns),
            }
            st.session_state.pop(_SS_PLAN, None)
            st.session_state.pop(_SS_CSV_SIG, None)
            st.session_state[_SS_CSV_UPLOADER_NONCE] = uploader_nonce + 1
            st.rerun()
        except ValueError as e:
            st.error(str(e))
        except Exception as e:
            st.error(f'Import failed: {e}')


def _render_form_tab(task_names: list[str]) -> None:
    st.markdown('### Add or Update Profile')
    st.caption('Use this form for one-at-a-time profile updates with overwrite confirmation safeguards.')
    if not task_names:
        st.info('Add at least one task in Task Catalog before editing favorites/dislikes.')
        return

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
            if st.button(
                'Overwrite database with form values',
                key='tech_form_do_overwrite',
                type='primary',
            ):
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
        submitted = st.form_submit_button('Save technician', type='primary')

    if not submitted:
        return

    if not f_tech_id.strip() or not f_name.strip():
        st.error('`tech_id` and `tech_name` are required.')
        return

    try:
        fav_list, dis_list = validate_tech_preference_lists(
            f_fav,
            f_dis,
            allowed_task_names=task_names,
        )
        tech = Tech(
            tech_id=f_tech_id.strip(),
            tech_name=f_name.strip(),
            daily_preference=f_pref,
            favorites=fav_list,
            dislikes=dis_list,
        )
        with session_scope() as session:
            existing_tech = load_tech_by_tech_id(session, tech.tech_id)
            if existing_tech is not None:
                if tech_profile_equals(existing_tech, tech):
                    st.info(f'Technician `{tech.tech_id}` is already saved with the same values.')
                else:
                    st.session_state[_SS_FORM_PENDING] = {
                        'incoming': _tech_to_state(tech),
                        'existing': _tech_to_state(existing_tech),
                    }
                    st.rerun()
            else:
                other_id = find_tech_id_for_normalized_tech_name(
                    session, normalize_string(tech.tech_name)
                )
                if other_id is not None:
                    st.error(
                        f'The name `{tech.tech_name}` is already used by technician `{other_id}`. '
                        'Use that `tech_id` to edit the profile, or choose a different display name.'
                    )
                else:
                    merge_technician_from_tech(session, tech)
                    st.success(f'Added technician `{tech.tech_id}`.')
    except Exception as e:
        st.error(f'Could not save: {e}')


def render_technician_profiles_page() -> None:
    render_page_header(
        'Technician Profiles',
        'Identity, daily preference, favorites, and dislikes — the inputs your scoring engine reads.',
        kicker='Registry & import',
    )
    with st.expander('When to use this page', expanded=False):
        st.markdown(
            '- **Before running the Assignment Engine** if technicians are missing or profiles are outdated.\n'
            '- **When schedule names change** so `tech_name` still matches what appears in schedule CSVs.\n'
            '- **When preferences change** (favorites, dislikes, daily preference) so scoring reflects current rules.\n'
            '- Day-level availability and call-offs stay in **schedule uploads on Home** — not here.'
        )
    st.markdown(
        '''
<div class="aa-card">
  <div class="aa-kicker">Profile Data Model</div>
  Profiles are intentionally stable and role-oriented. Day-level availability and staffing status
  belong to schedule uploads on the Home page.
</div>
''',
        unsafe_allow_html=True,
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
            task_catalog = list_tasks(session)
    except Exception as e:
        st.error(f'Could not load technicians/tasks: {e}')
        techs = []
        task_catalog = []

    task_names = [t.task_name for t in task_catalog]

    tabs = st.tabs(['Profiles', 'Bulk Import', 'Add or Edit Profile', 'Remove technicians'])
    with tabs[0]:
        _render_profiles_tab(techs)
    with tabs[1]:
        _render_csv_tab(task_names)
    with tabs[2]:
        _render_form_tab(task_names)
    with tabs[3]:
        _render_delete_tab(techs)
