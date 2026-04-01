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
from auto_assign.domain.enums import TimeSlot
from auto_assign.task_config import tasks as tasks_config
from auto_assign.ingestion import TaskRequest
st.set_page_config(page_title="Auto Assign", page_icon=":robot:", layout="wide")

st.title("Auto Assign")

st.write("This is a simple app to assign technicians to work based on their availability and the work date.")

st.write(
    "Upload a schedule CSV with **tech_name**, **date** (YYYY-MM-DD), and "
    "**available_AM**, **available_MID**, **available_PM** (one boolean per shift). "
    "Cells can use 1/0, yes/no, or true/false. "
    "Legacy exports without underscores in those three header names are normalized on upload."
)

uploaded_file = st.file_uploader("Upload a schedule CSV file", type=["csv"])

if uploaded_file is not None:
    try:
        df = load_schedule(uploaded_file)
        schedule_rows = parse_schedule(df)

        available_dates = get_all_schedule_dates(schedule_rows)

        if not available_dates:
            st.error("No available dates found in the schedule.")
            st.stop()

        # Stable widget identity per upload so a new CSV does not reuse old select state.
        upload_widget_id = getattr(uploaded_file, "file_id", None) or uploaded_file.name

        date_options = sorted(available_dates)
        selected_date = st.selectbox(
            "Select a date",
            options=date_options,
            key=f"schedule_date_{upload_widget_id}",
        )
        selected_time_slot = st.selectbox(
            "Select a time slot (shift band)",
            options=list(TimeSlot),
            format_func=lambda slot: slot.value,
            key=f"schedule_time_slot_{upload_widget_id}",
            help="Only technicians marked available for this shift on the selected date are assignable.",
        )

        available_techs = get_available_techs(schedule_rows, selected_date, selected_time_slot)
        available_tech_pool = filter_schedule_rows_available_for_date_and_time_slot(
            schedule_rows, selected_date, selected_time_slot
        )

        slot_label = selected_time_slot.value
        st.markdown(f"### Available Techs for {selected_date} ({slot_label})")
        st.metric("Number of Available Techs", len(available_techs))
        
        if available_techs:
            with st.expander("Available Techs", expanded=False):
                st.markdown("\n".join(f"- {name}" for name in available_techs))
        else:
            st.info("No available techs for the selected date and time slot.")
            st.stop()
        
        
        st.markdown("### Task Allocation")
        task_list = create_tasks(tasks_config)

        # Streamlit keeps number_input state by key; without a key tied to date + slot, changing
        # the time slot leaves stale counts / wrong max_value. New context => new widget state.
        allocation_context = f"{upload_widget_id}_{selected_date.isoformat()}_{selected_time_slot.name}"

        task_requests = []
        total_requested = 0

        pool_size = len(available_techs)
        for task in task_list:
            count = st.number_input(
                label=f"{task.task_name} Count",
                value=min(task.default_count, pool_size),
                min_value=0,
                max_value=pool_size,
                step=1,
                key=f"task_count_{task.task_id}_{allocation_context}",
                help="Headcount for this task on the selected date and shift (must sum to available techs).",
            )

            task_requests.append(TaskRequest(task_id=task.task_id, task_name=task.task_name, task_count=count, task_date=selected_date, time_slot=selected_time_slot))

            total_requested += count

        remaining = len(available_techs) - total_requested

        st.metric("Remaining Techs", remaining)

        can_generate = remaining == 0

        if not can_generate:
            st.warning("Please allocate all available tech slots to tasks before generating assignments.")

        if st.button("Generate Assignments", disabled=not can_generate):
            try:
                assignments = assign_tasks(task_requests, available_tech_pool)
                st.success("Assignments generated successfully!")
                st.dataframe(assignments, use_container_width=True)
            except Exception as e:
                st.error(f"Could not generate assignments: {e}")

    except Exception as e:
        st.error(f"Could not process the schedule CSV file: {e}")



