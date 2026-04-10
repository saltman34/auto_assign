'''Pure helpers for schedule upload → assignment workflow (no Streamlit).'''

from __future__ import annotations

from auto_assign.domain.entities import Tech
from auto_assign.domain.enums import TimeSlot
from auto_assign.domain.validators.primitives import normalize_string, normalize_tech_id
from auto_assign.ingestion import TaskRequest
from auto_assign.ingestion.csv_schema import ScheduleRow


def slice_commit_key(upload_widget_id: str) -> str:
    return f'aa_slice_committed_{upload_widget_id}'


def allocation_context(upload_widget_id: str, work_date, time_slot: TimeSlot) -> str:
    return f'{upload_widget_id}_{work_date.isoformat()}_{time_slot.name}'


def task_count_signature(requests: list[TaskRequest]) -> tuple[tuple[str, int], ...]:
    return tuple(sorted((r.task_id, r.task_count) for r in requests))


def normalized_day_override_signature(
    call_off_tech_ids: list[str], overtime_tech_ids_by_slot: dict[TimeSlot, list[str]]
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    return (
        tuple(sorted(set(call_off_tech_ids))),
        tuple(sorted(set(overtime_tech_ids_by_slot[TimeSlot.AM]))),
        tuple(sorted(set(overtime_tech_ids_by_slot[TimeSlot.MID]))),
        tuple(sorted(set(overtime_tech_ids_by_slot[TimeSlot.PM]))),
    )


def tech_id_for_row(row: ScheduleRow, profiles_by_name: dict[str, Tech]) -> str:
    t = profiles_by_name.get(normalize_string(row.tech_name))
    if t is not None:
        return t.tech_id
    return normalize_tech_id(row.tech_name)
