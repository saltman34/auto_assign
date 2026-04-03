'''SQLAlchemy persistence (ORM models and shared ``Base``).'''

from auto_assign.db.adapters import (
    assignment_from_record,
    assignments_from_confirmed_records,
    tech_from_technician,
    technician_from_tech,
)
from auto_assign.db.base import Base
from auto_assign.db.models import AssignmentRecord, Technician
from auto_assign.db.assignment_repository import (
    confirm_slice,
    count_confirmed_for_slice,
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
    list_technicians,
    merge_technician_from_tech,
    upsert_technicians,
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
    'TechImportRowPlan',
    'apply_tech_import_plan',
    'build_tech_import_plan',
    'confirm_slice',
    'count_assignments_for_technician',
    'count_confirmed_for_slice',
    'dedupe_tech_rows_last_wins',
    'delete_all_technicians',
    'delete_technician',
    'load_draft_assignments_for_slice',
    'list_technicians',
    'replace_draft_slice',
    'summarize_plan',
    'technician_ids_missing_from_db',
    'assignment_from_record',
    'assignments_from_confirmed_records',
    'Base',
    'merge_technician_from_tech',
    'tech_from_technician',
    'technician_from_tech',
    'Technician',
    'upsert_technicians',
    'load_confirmed_assignments_for_scoring',
    'load_tech_profiles_by_name',
    'get_database_url',
    'get_engine',
    'get_session_factory',
    'reset_engine_cache',
    'session_scope',
]
