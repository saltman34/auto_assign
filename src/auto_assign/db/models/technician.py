'''
ORM model for persisted technician profiles (CSV / DB source for ``Tech`` / scoring).

Column names use snake_case; map to domain ``Tech`` when building ``tech_profiles_by_name``.
'''
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, Enum as SQLEnum, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from auto_assign.db.models.assignment_record import AssignmentRecord

from auto_assign.db.base import Base
from auto_assign.domain.enums import DailyPreference

# JSON array of strings; JSONB on PostgreSQL, portable JSON elsewhere (e.g. SQLite tests).
_json_str_list = JSON().with_variant(JSONB(), 'postgresql')
# JSON object maps (task_id -> value); JSONB on PostgreSQL.
_json_obj = JSON().with_variant(JSONB(), 'postgresql')


class Technician(Base):
    __tablename__ = 'technicians'
    __table_args__ = (UniqueConstraint('tech_name', name='uq_technicians_tech_name'),)

    #: Stable business identifier (primary key); matches CSV ``tech_id`` and assignment FKs.
    tech_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    #: Normalized display name; unique so ``tech_profiles_by_name`` has one row per name.
    tech_name: Mapped[str] = mapped_column(String(256), nullable=False)
    daily_preference: Mapped[DailyPreference] = mapped_column(
        SQLEnum(
            DailyPreference,
            values_callable=lambda x: [e.value for e in x],
            native_enum=False,
            length=32,
        ),
        nullable=False,
    )
    #: Normalized task names (same convention as domain ``Tech.favorites``).
    favorites: Mapped[list[str]] = mapped_column(_json_str_list, nullable=False, default=list)
    #: Normalized task names (same convention as domain ``Tech.dislikes``).
    dislikes: Mapped[list[str]] = mapped_column(_json_str_list, nullable=False, default=list)
    #: Catalog ``task_id`` -> explicit False to hard-exclude (absent keys = eligible).
    eligible_by_task_id: Mapped[dict[str, bool]] = mapped_column(
        _json_obj,
        nullable=False,
        server_default='{}',
    )
    #: Catalog ``task_id`` -> ``TaskProficiencyLevel`` value string (e.g. ``expert``).
    proficiency_by_task_id: Mapped[dict[str, str]] = mapped_column(
        _json_obj,
        nullable=False,
        server_default='{}',
    )

    assignments: Mapped[list['AssignmentRecord']] = relationship(back_populates='technician')
