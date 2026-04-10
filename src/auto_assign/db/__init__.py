'''SQLAlchemy persistence (ORM models and shared ``Base``).'''

from auto_assign.db.adapters import (
    assignment_from_record,
    assignments_from_confirmed_records,
    tech_from_technician,
    technician_from_tech,
)
from auto_assign.db.base import Base
from auto_assign.db.models import AssignmentOverride, AssignmentRecord, TaskCatalog, Technician
from auto_assign.db.assignment_repository import (
    confirm_slice,
    count_confirmed_for_slice,
    delete_draft_slice,
    list_distinct_work_dates_with_confirmed,
    load_confirmed_assignment_rows_for_date,
    load_confirmed_assignment_rows_for_slice,
    load_draft_assignments_for_slice,
    replace_draft_slice,
    technician_ids_missing_from_db,
)
from auto_assign.db.scheduling_repository import (
    load_confirmed_assignments_for_scoring,
    load_tech_profiles_by_name,
)
from auto_assign.db.tech_import_plan import (
    TechImportRowPlan,
    apply_tech_import_plan,
    build_tech_import_plan,
    dedupe_tech_rows_last_wins,
    summarize_plan,
)
from auto_assign.db.tech_repository import (
    count_assignments_for_technician,
    delete_all_technicians,
    delete_technician,
    find_tech_id_for_normalized_tech_name,
    list_technicians,
    load_tech_by_tech_id,
    merge_technician_from_tech,
    upsert_technicians,
)
from auto_assign.db.task_repository import (
    create_task,
    delete_task,
    list_tasks,
    set_task_default_count,
)
from auto_assign.db.override_repository import (
    clear_draft_overrides_for_slice,
    confirm_draft_overrides_for_slice,
    load_confirmed_override_rows_for_slice,
    load_draft_overrides_for_slice,
    replace_draft_day_availability_overrides,
    replace_draft_manual_assignments_for_slice,
)
from auto_assign.db.session import (
    get_database_url,
    get_engine,
    get_session_factory,
    reset_engine_cache,
    session_scope,
)

__all__ = [
    'AssignmentRecord',
    'AssignmentOverride',
    'TaskCatalog',
    'TechImportRowPlan',
    'apply_tech_import_plan',
    'build_tech_import_plan',
    'clear_draft_overrides_for_slice',
    'confirm_slice',
    'confirm_draft_overrides_for_slice',
    'count_assignments_for_technician',
    'count_confirmed_for_slice',
    'delete_draft_slice',
    'dedupe_tech_rows_last_wins',
    'delete_all_technicians',
    'delete_technician',
    'create_task',
    'list_distinct_work_dates_with_confirmed',
    'list_tasks',
    'load_confirmed_assignment_rows_for_date',
    'load_confirmed_assignment_rows_for_slice',
    'load_confirmed_override_rows_for_slice',
    'load_draft_assignments_for_slice',
    'load_draft_overrides_for_slice',
    'find_tech_id_for_normalized_tech_name',
    'list_technicians',
    'load_tech_by_tech_id',
    'replace_draft_slice',
    'replace_draft_day_availability_overrides',
    'replace_draft_manual_assignments_for_slice',
    'set_task_default_count',
    'summarize_plan',
    'technician_ids_missing_from_db',
    'assignment_from_record',
    'assignments_from_confirmed_records',
    'Base',
    'merge_technician_from_tech',
    'tech_from_technician',
    'technician_from_tech',
    'Technician',
    'delete_task',
    'upsert_technicians',
    'load_confirmed_assignments_for_scoring',
    'load_tech_profiles_by_name',
    'get_database_url',
    'get_engine',
    'get_session_factory',
    'reset_engine_cache',
    'session_scope',
]
