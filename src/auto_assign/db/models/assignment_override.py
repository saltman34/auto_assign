'''
ORM model for manual override events used by Assignment Engine.
'''
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum as SQLEnum, ForeignKey, Index, Integer, String, false, func
from sqlalchemy.orm import Mapped, mapped_column

from auto_assign.db.base import Base
from auto_assign.domain.enums import AssignmentStatus, OverrideKind, OverrideScope, TimeSlot


class AssignmentOverride(Base):
    __tablename__ = 'assignment_overrides'
    __table_args__ = (
        Index('ix_assignment_overrides_status_work_date', 'status', 'work_date'),
        Index('ix_assignment_overrides_slice_lookup', 'work_date', 'time_slot', 'status'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    time_slot: Mapped[TimeSlot | None] = mapped_column(
        SQLEnum(
            TimeSlot,
            values_callable=lambda x: [e.value for e in x],
            native_enum=False,
            length=8,
        ),
        nullable=True,
    )
    scope: Mapped[OverrideScope] = mapped_column(
        SQLEnum(
            OverrideScope,
            values_callable=lambda x: [e.value for e in x],
            native_enum=False,
            length=16,
        ),
        nullable=False,
    )
    kind: Mapped[OverrideKind] = mapped_column(
        SQLEnum(
            OverrideKind,
            values_callable=lambda x: [e.value for e in x],
            native_enum=False,
            length=32,
        ),
        nullable=False,
    )
    technician_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey('technicians.tech_id', ondelete='RESTRICT'),
        nullable=False,
    )
    # Required only for kind == MANUAL_ASSIGNMENT.
    task_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[AssignmentStatus] = mapped_column(
        SQLEnum(
            AssignmentStatus,
            values_callable=lambda x: [e.value for e in x],
            native_enum=False,
            length=16,
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    #: True when a MANUAL_ASSIGNMENT override places a tech the catalog explicitly flags
    #: as ineligible (training/shadowing case). Always False for CALL_OFF / OVERTIME.
    eligibility_overridden: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
