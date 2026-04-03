'''
Preflight planning for technician CSV import (conflicts, idempotency, name collisions).

``build_tech_import_plan`` classifies each incoming ``Tech`` against the current DB.
``apply_tech_import_plan`` performs merges according to operator choices.
'''
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from auto_assign.db.adapters import tech_from_technician
from auto_assign.db.models.technician import Technician
from auto_assign.db.tech_repository import merge_technician_from_tech
from auto_assign.domain.entities.tech import Tech, tech_profile_equals
from auto_assign.domain.validators.primitives import normalize_string

RowStatus = Literal['new', 'unchanged', 'update_pending', 'name_blocked']


@dataclass(frozen=True)
class TechImportRowPlan:
    incoming: Tech
    existing: Tech | None
    status: RowStatus
    #: When ``status == 'name_blocked'``, ``tech_id`` of the row that already owns ``tech_name``.
    name_owner_tech_id: str | None = None


def dedupe_tech_rows_last_wins(techs: Sequence[Tech]) -> list[Tech]:
    '''
    If the same ``tech_id`` appears multiple times, keep the **last** row (spreadsheet order).
    Output order follows first occurrence index of each id after deduplication.
    '''
    by_id: dict[str, Tech] = {}
    last_pos: dict[str, int] = {}
    for i, t in enumerate(techs):
        by_id[t.tech_id] = t
        last_pos[t.tech_id] = i
    ordered = sorted(by_id.keys(), key=lambda tid: last_pos[tid])
    return [by_id[tid] for tid in ordered]


def _load_db_indexes(session: Session) -> tuple[dict[str, Tech], dict[str, Tech]]:
    rows = session.scalars(select(Technician).order_by(Technician.tech_id)).all()
    by_id: dict[str, Tech] = {}
    by_name: dict[str, Tech] = {}
    for r in rows:
        t = tech_from_technician(r)
        by_id[t.tech_id] = t
        by_name[normalize_string(t.tech_name)] = t
    return by_id, by_name


def build_tech_import_plan(session: Session, techs: Sequence[Tech]) -> list[TechImportRowPlan]:
    '''
    Compare parsed CSV rows to the database.

    - **new:** ``tech_id`` not in DB and ``tech_name`` not taken (or taken only by same id after insert path — N/A for new).
    - **unchanged:** ``tech_id`` exists and ``tech_profile_equals``.
    - **update_pending:** ``tech_id`` exists and fields differ.
    - **name_blocked:** ``tech_id`` is new but ``tech_name`` is already used by another ``tech_id``.
    '''
    deduped = dedupe_tech_rows_last_wins(techs)
    by_id, by_name = _load_db_indexes(session)
    plans: list[TechImportRowPlan] = []

    for t in deduped:
        existing = by_id.get(t.tech_id)
        if existing is not None:
            if tech_profile_equals(existing, t):
                plans.append(TechImportRowPlan(t, existing, 'unchanged'))
            else:
                plans.append(TechImportRowPlan(t, existing, 'update_pending'))
            continue

        owner = by_name.get(normalize_string(t.tech_name))
        if owner is not None and owner.tech_id != t.tech_id:
            plans.append(
                TechImportRowPlan(
                    t,
                    None,
                    'name_blocked',
                    name_owner_tech_id=owner.tech_id,
                )
            )
        else:
            plans.append(TechImportRowPlan(t, None, 'new'))

    return plans


def summarize_plan(plans: Sequence[TechImportRowPlan]) -> dict[str, int]:
    out = {'new': 0, 'unchanged': 0, 'update_pending': 0, 'name_blocked': 0}
    for p in plans:
        out[p.status] += 1
    return out


def apply_tech_import_plan(
    session: Session,
    plans: Sequence[TechImportRowPlan],
    *,
    overwrite_updates: bool,
    skip_name_blocked: bool,
) -> tuple[int, int, list[str]]:
    '''
    Apply a plan built with ``build_tech_import_plan``.

    Returns:
        ``(written_count, skipped_unchanged, warnings)``.

    Raises:
        ValueError: If ``name_blocked`` rows are present and ``skip_name_blocked`` is False.
    '''
    blocked = [p for p in plans if p.status == 'name_blocked']
    if blocked and not skip_name_blocked:
        lines = [
            f'`{b.incoming.tech_id}` ({b.incoming.tech_name!r}) — name already used by `{b.name_owner_tech_id}`'
            for b in blocked
        ]
        raise ValueError(
            'Cannot import: technician name(s) already belong to a different `tech_id`. '
            'Reuse the existing `tech_id` in your CSV, or remove/rename the row(s). '
            'Details:\n'
            + '\n'.join(lines)
        )

    warnings: list[str] = []
    written = 0
    skipped_unchanged = 0

    for p in plans:
        if p.status == 'unchanged':
            skipped_unchanged += 1
            continue
        if p.status == 'name_blocked':
            warnings.append(
                f'Skipped `{p.incoming.tech_id}`: name `{p.incoming.tech_name}` '
                f'already belongs to `{p.name_owner_tech_id}`.'
            )
            continue
        if p.status == 'update_pending' and not overwrite_updates:
            warnings.append(
                f'Skipped update for `{p.incoming.tech_id}`: profile differs from database '
                '(enable overwrite to apply).'
            )
            continue
        merge_technician_from_tech(session, p.incoming)
        written += 1

    return written, skipped_unchanged, warnings
