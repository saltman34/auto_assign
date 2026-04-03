'''
Validate technician favorites / dislists against the task catalog in ``task_config``.

Used by CSV parsing and Streamlit form before constructing ``Tech``.
'''
from __future__ import annotations

from collections.abc import Sequence

from auto_assign.domain.validators.primitives import normalize_string
from auto_assign.task_config import tasks


def normalized_canonical_task_names() -> frozenset[str]:
    '''Task display names from ``task_config``, each passed through ``normalize_string``.'''
    return frozenset(normalize_string(t['task_name']) for t in tasks)


def validate_tech_preference_lists(
    favorites_raw: Sequence[str],
    dislikes_raw: Sequence[str],
    *,
    max_each: int = 3,
) -> tuple[list[str], list[str]]:
    '''
    Normalize, deduplicate, and validate favorites and dislikes.

    Rules:
        - Empty segments are skipped; internal runs of whitespace are collapsed, then each entry is
          ``normalize_string``-ed.
        - No duplicate task names within ``favorites`` or within ``dislikes`` (after normalization).
        - A task cannot appear in both lists.
        - Every name must match a task in ``task_config`` (after normalization).
        - At most ``max_each`` entries per list (default 3).

    Returns:
        ``(favorites, dislikes)`` as normalized lists suitable for ``Tech``.

    Raises:
        ValueError: On any rule violation, with an operator-oriented message.
    '''
    canon = normalized_canonical_task_names()

    def _normalize_dedupe_list(raw: Sequence[str], *, label: str) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for x in raw:
            s = str(x).strip()
            if not s:
                continue
            n = normalize_string(' '.join(s.split()))
            if n in seen:
                raise ValueError(f'Duplicate {label} task (after normalization): {n!r}')
            seen.add(n)
            out.append(n)
        return out

    fav = _normalize_dedupe_list(favorites_raw, label='favorite')
    dis = _normalize_dedupe_list(dislikes_raw, label='dislike')

    if len(fav) > max_each:
        raise ValueError(f'At most {max_each} favorites allowed, got {len(fav)}')
    if len(dis) > max_each:
        raise ValueError(f'At most {max_each} dislikes allowed, got {len(dis)}')

    overlap = set(fav) & set(dis)
    if overlap:
        o = ', '.join(sorted(overlap))
        raise ValueError(f'Task(s) cannot be both a favorite and a dislike: {o}')

    unknown_f = [n for n in fav if n not in canon]
    unknown_d = [n for n in dis if n not in canon]
    if unknown_f or unknown_d:
        allowed = ', '.join(sorted(canon))
        parts = []
        if unknown_f:
            parts.append(f'unknown favorites {unknown_f!r}')
        if unknown_d:
            parts.append(f'unknown dislikes {unknown_d!r}')
        raise ValueError(
            f"Invalid task name(s) ({'; '.join(parts)}). "
            f'Use names from the task catalog: {allowed}'
        )

    return fav, dis
