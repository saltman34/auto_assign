'''Task catalog page: list, add, update, and remove DB-backed tasks for assignment headcounts.'''

from __future__ import annotations

import pandas as pd
import streamlit as st

from auto_assign.db import (
    create_task,
    delete_task,
    list_tasks,
    session_scope,
    set_task_default_count,
)
from auto_assign.domain.entities import Task
from auto_assign.ui.components import render_step_panel
from auto_assign.ui.db_state import database_url_configured
from auto_assign.ui.page import render_page_header

# Sentinel for selectbox "no task chosen yet" (avoids exposing raw IDs in the picker).
_TASK_PICK_NONE = object()


def _tasks_display_dataframe(tasks: list[Task]) -> pd.DataFrame:
    """Columns use human-facing labels; internal task_id is omitted from the grid."""
    rows = [
        {'Task name': t.task_name, 'Default headcount': int(t.default_count)}
        for t in tasks
    ]
    return pd.DataFrame(rows)


def _catalog_table_config() -> dict:
    return {
        'Task name': st.column_config.TextColumn('Task name', width='large'),
        'Default headcount': st.column_config.NumberColumn(
            'Default headcount',
            min_value=0,
            step=1,
            format='%d',
        ),
    }


def _render_catalog_tab(tasks: list[Task]) -> None:
    st.markdown('### Catalog')
    st.caption(
        'Saved task names and default headcounts used by Assignment Engine and technician preferences.'
    )
    if not tasks:
        st.markdown(
            '<div class="aa-empty">No tasks saved yet. Use <strong>Add Task</strong> to create your own — '
            'or load demo data from the <strong>Home</strong> page for a sample 6-task catalog.</div>',
            unsafe_allow_html=True,
        )
    else:
        st.dataframe(
            _tasks_display_dataframe(tasks),
            use_container_width=True,
            hide_index=True,
            column_config=_catalog_table_config(),
        )


def _render_add_task_tab() -> None:
    st.markdown('### Add task')
    st.caption('Create a new task with an optional default headcount.')
    with st.form('task_catalog_add_form'):
        new_name = st.text_input('Task name', placeholder='e.g. Clinicals')
        new_default = st.number_input(
            'Default headcount',
            min_value=0,
            step=1,
            value=0,
            help='Starting slot count suggested before you tune counts for a specific day.',
        )
        add_submit = st.form_submit_button('Add task', type='primary')
    if add_submit:
        try:
            with session_scope() as session:
                row = create_task(session, new_name, default_count=int(new_default))
            st.success(f'Added “{row.task_name}” (default headcount {int(row.default_count)}).')
            st.rerun()
        except Exception as e:
            st.error(f'Could not add task: {e}')


def _render_update_tasks_tab(tasks: list[Task]) -> None:
    st.markdown('### Update tasks')
    st.caption(
        'Pick a task, then use **Edit default** or **Delete from catalog** — each action stays on its own tab so the flow stays clear.'
    )
    if not tasks:
        st.info(
            'No tasks available yet. Add one from the **Add Task** tab — or load demo data '
            'from **Home** for a sample catalog.'
        )
        return

    pick_options: list[object] = [_TASK_PICK_NONE, *tasks]

    def _format_task_pick(x: object) -> str:
        if x is _TASK_PICK_NONE:
            return '— Choose a task —'
        assert isinstance(x, Task)
        n = int(x.default_count)
        suffix = f' ({n} default)' if n else ''
        return f'{x.task_name}{suffix}'

    with st.container(border=True):
        render_step_panel('Step 1 · Select a task', 'The same task is used for both actions in Step 2.')
        pick = st.selectbox(
            'Task',
            options=pick_options,
            format_func=_format_task_pick,
            key='task_catalog_pick',
            help='Names are shown as stored. Default headcount appears in parentheses when it is not zero.',
        )
        if pick is _TASK_PICK_NONE:
            st.caption('Choose a task to continue — the panel below will unlock.')
            return

    assert isinstance(pick, Task)
    selected = pick

    with st.container(border=True):
        render_step_panel(
            'Step 2 · Review and change',
            'Confirm this is the task you want, then open **Edit default** or **Delete from catalog**.',
        )
        st.dataframe(
            _tasks_display_dataframe([selected]),
            use_container_width=True,
            hide_index=True,
            column_config=_catalog_table_config(),
        )
        with st.expander('Internal ID — what is this?', expanded=False):
            st.markdown(
                'The **internal ID** is a fixed value the database stores for this task. It is **not** the same '
                'as the task name: the name is what you and technicians see in the app and in CSVs; the internal ID '
                'is the key assignments and technician preferences use behind the scenes so those records stay '
                'pointing at the right task.\n\n'
                'You usually **do not** need it for day-to-day work. It is here if you are debugging with someone '
                'technical, matching rows in the database, or talking to support.'
            )
            st.caption('Stored value:')
            st.code(selected.task_id, language=None)

        st.markdown('<div class="aa-step-divider"></div>', unsafe_allow_html=True)

        tab_adjust, tab_remove = st.tabs(['Edit default', 'Delete from catalog'])

        with tab_adjust:
            st.markdown(
                '**Default headcount** is how many slots the Assignment Engine suggests for this task '
                'before you set real counts for a specific date on **Home**. Changing it here does not '
                'rewrite past schedules.'
            )
            update_default = st.number_input(
                'Default headcount',
                min_value=0,
                step=1,
                value=int(selected.default_count),
                key=f'task_catalog_update_default_{selected.task_id}',
                help='Saved as this task’s default in the catalog; per-day counts are chosen when you run assignments.',
            )
            if st.button('Save default', key='task_catalog_update_btn', type='primary'):
                try:
                    with session_scope() as session:
                        set_task_default_count(session, selected.task_id, int(update_default))
                    st.success(f'Updated default for `{selected.task_name}` to {int(update_default)}.')
                    st.rerun()
                except Exception as e:
                    st.error(f'Could not update task: {e}')

        with tab_remove:
            st.caption(
                'Deleting a task cannot be undone. If the button stays disabled or you see an error, '
                'this task is still referenced by assignments or technician preferences — clear those first.'
            )
            confirm_name = st.text_input(
                f'Type the task name exactly (`{selected.task_name}`) to enable delete',
                key=f'task_catalog_delete_confirm_{selected.task_id}',
            )
            delete_disabled = confirm_name.strip() != selected.task_name
            if st.button(
                'Delete from catalog',
                key='task_catalog_delete_btn',
                type='secondary',
                disabled=delete_disabled,
                help='The name you type must match the task name character for character.',
            ):
                try:
                    with session_scope() as session:
                        n = delete_task(session, selected.task_id)
                    if n == 0:
                        st.info('Task was already deleted from the catalog.')
                    else:
                        st.success(f'Deleted `{selected.task_name}` from the catalog.')
                    st.rerun()
                except Exception as e:
                    st.error(f'Could not delete task: {e}')


def render_task_catalog_page() -> None:
    render_page_header(
        'Task Catalog',
        'Task names and default headcounts — reference data the Assignment Engine and preferences use.',
        kicker='Reference data',
    )
    with st.expander('When to use this page', expanded=False):
        st.markdown(
            '- **Before running the Assignment Engine** so task names and default slots match what you expect.\n'
            '- **Before importing technician profiles** — favorites and dislikes must reference tasks that exist here.\n'
            '- **When your task mix changes** (rename by adding a new task and retiring the old one after clearing references).\n'
            '- Per-day headcounts are set during the run on **Home**; defaults here only seed the workflow.'
        )
    st.markdown(
        '''
<div class="aa-card">
  <div class="aa-kicker">Task Catalog Data Model</div>
  Tasks are stable labels with an optional default headcount. The default headcount is the
  starting slot count the Assignment Engine suggests per shift. When catalog defaults sum to more
  than the available pool on a given day, Step 5 scales each task down proportionally so no task
  gets unfairly zeroed out.
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
            tasks = list_tasks(session)
    except Exception as e:
        st.error(f'Could not load tasks: {e}')
        return

    tabs = st.tabs(['Catalog', 'Add Task', 'Update tasks'])
    with tabs[0]:
        _render_catalog_tab(tasks)
    with tabs[1]:
        _render_add_task_tab()
    with tabs[2]:
        _render_update_tasks_tab(tasks)
