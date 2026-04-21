from dataclasses import dataclass
from datetime import date
from auto_assign.domain.validators.primitives import (
    require_non_empty_string,
    require_date,
    normalize_string,
    normalize_tech_id,
)
from auto_assign.domain.enums import TimeSlot

@dataclass
class Assignment:
    '''
    Assignment of one technician to one task on a date within a shift band (AM/MID/PM).

    ``technician_id`` is ``tech_id`` (stable id, trim-only; not display name).

    ``catalog_task_id`` is the task catalog primary key when known (eligibility / proficiency
    maps). When ``None``, scoring falls back to ``task_name`` for those lookups (legacy tests).

    ``eligibility_overridden`` is True only when an operator explicitly placed this technician
    on the task via a manual assignment despite ``Tech.eligible_by_task_id[catalog_task_id]``
    being ``False``. Greedy-produced rows always leave it ``False``; manual rows default False
    and flip to True only through the Step 6 two-stage confirmation flow. This flag is a
    pinning signal (the local-swap post-pass must not relocate overridden techs) and an audit
    trail that persists into confirmed history.
    '''
    task_name: str
    technician_id: str
    date_assigned: date
    time_slot: TimeSlot
    catalog_task_id: str | None = None
    eligibility_overridden: bool = False

    def __post_init__(self):
        '''
        Validate the assignment.
        '''
        self.task_name = require_non_empty_string(self.task_name)
        self.technician_id = require_non_empty_string(self.technician_id)
        self.date_assigned = require_date(self.date_assigned)
        self.task_name = normalize_string(self.task_name)
        self.technician_id = normalize_tech_id(self.technician_id)
        if self.catalog_task_id is not None:
            cid = str(self.catalog_task_id).strip()
            self.catalog_task_id = cid if cid else None
        if not isinstance(self.time_slot, TimeSlot):
            raise ValueError(f"time_slot must be a TimeSlot enum, got {type(self.time_slot).__name__}")
        self.eligibility_overridden = bool(self.eligibility_overridden)

    def effective_catalog_task_id(self) -> str:
        '''Catalog key for eligibility/proficiency maps (falls back to ``task_name``).'''
        if self.catalog_task_id is not None and self.catalog_task_id.strip():
            return self.catalog_task_id
        return self.task_name
