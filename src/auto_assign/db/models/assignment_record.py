'''
ORM model for persisted assignments (draft workspace + confirmed history).

Named ``AssignmentRecord`` to avoid clashing with domain ``Assignment``. Map to
domain with ``task_id`` (currently task display name for compatibility with
``Assignment.task_name``), ``technician_id``, ``date_assigned`` ← ``work_date``, and
``time_slot``.
'''
from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, Enum as SQLEnum, ForeignKey, Index, Integer, String, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from auto_assign.db.base import Base
from auto_assign.db.models.technician import Technician
from auto_assign.domain.enums import AssignmentStatus, TimeSlot


class AssignmentRecord(Base):
    __tablename__ = 'assignments'
    __table_args__ = (
        Index('ix_assignments_status_work_date', 'status', 'work_date'),
        Index('ix_assignments_tech_work_status', 'technician_id', 'work_date', 'status'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    technician_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey('technicians.tech_id', ondelete='RESTRICT'),
        nullable=False,
    )
    #: Stored normalized task display name (UI / favorites alignment).
    task_id: Mapped[str] = mapped_column(String(256), nullable=False)
    #: Optional catalog ``task_id`` for eligibility/proficiency scoring (null on legacy rows).
    catalog_task_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    #: Calendar date of the shift (domain ``Assignment.date_assigned``).
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    time_slot: Mapped[TimeSlot] = mapped_column(
        SQLEnum(
            TimeSlot,
            values_callable=lambda x: [e.value for e in x],
            native_enum=False,
            length=8,
        ),
        nullable=False,
    )
    status: Mapped[AssignmentStatus] = mapped_column(
        SQLEnum(
            AssignmentStatus,
            values_callable=lambda x: [e.value for e in x],
            native_enum=False,
            length=16,
        ),
        nullable=False,
    )
    #: Disambiguates multiple headcount slots for the same task on one (date, slot) slice.
    slot_index: Mapped[int] = mapped_column(Integer, nullable=False)
    #: True only for manual assignments where the operator explicitly placed an ineligible
    #: tech (training/shadowing case); greedy-produced rows are always False. Carried
    #: through draft → confirmed so the audit and UI badge survive round-trips.
    eligibility_overridden: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    technician: Mapped[Technician] = relationship(back_populates='assignments')
