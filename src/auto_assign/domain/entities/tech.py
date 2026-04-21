from dataclasses import dataclass, field

from auto_assign.domain.enums import DailyPreference, TaskProficiencyLevel
from auto_assign.domain.validators.primitives import (
    normalize_string,
    normalize_tech_id,
    require_non_empty_string,
)


def _coerce_eligible_map(raw: dict[str, bool | object]) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for k, v in raw.items():
        ks = str(k).strip()
        if not ks:
            raise ValueError('eligible_by_task_id keys must be non-empty')
        if isinstance(v, bool):
            out[ks] = v
        elif isinstance(v, (int, float)) and int(v) in (0, 1):
            out[ks] = bool(int(v))
        else:
            raise ValueError(f'eligible_by_task_id[{k!r}] must be bool, got {type(v).__name__}')
    return out


def proficiency_dict_from_storage(raw: dict[str, object]) -> dict[str, TaskProficiencyLevel]:
    '''
    Build a proficiency map from JSON/DB (string values) for ``Tech`` construction.
    '''
    cleaned: dict[str, TaskProficiencyLevel | str | object] = {}
    for k, v in raw.items():
        ks = str(k).strip()
        if ks:
            cleaned[ks] = v
    return _coerce_proficiency_map(cleaned)


def _coerce_proficiency_map(
    raw: dict[str, TaskProficiencyLevel | str | object],
) -> dict[str, TaskProficiencyLevel]:
    out: dict[str, TaskProficiencyLevel] = {}
    for k, v in raw.items():
        ks = str(k).strip()
        if not ks:
            raise ValueError('proficiency_by_task_id keys must be non-empty')
        if isinstance(v, TaskProficiencyLevel):
            out[ks] = v
        elif isinstance(v, str):
            s = v.strip().lower().replace(' ', '_').replace('-', '_')
            found: TaskProficiencyLevel | None = None
            for e in TaskProficiencyLevel:
                if s == e.value or s == e.name.lower():
                    found = e
                    break
            if found is None:
                allowed = ', '.join(f'{e.name} ({e.value})' for e in TaskProficiencyLevel)
                raise ValueError(f'Invalid proficiency {v!r} for task {k!r}. Use one of: {allowed}')
            out[ks] = found
        else:
            raise ValueError(
                f'proficiency_by_task_id[{k!r}] must be TaskProficiencyLevel or str, got {type(v).__name__}'
            )
    return out


@dataclass
class Tech:
    '''
    Represents a technician.

    ``eligible_by_task_id``: catalog ``task_id`` -> False to hard-exclude from that task.
    Absent task keys are treated as eligible. ``proficiency_by_task_id``: catalog ``task_id``
    -> ordinal; absent keys use Independent with zero score delta in the assigner.
    '''

    tech_id: str
    tech_name: str
    daily_preference: DailyPreference
    favorites: list[str] = field(default_factory=list)
    dislikes: list[str] = field(default_factory=list)
    eligible_by_task_id: dict[str, bool] = field(default_factory=dict)
    proficiency_by_task_id: dict[str, TaskProficiencyLevel] = field(default_factory=dict)

    def __post_init__(self):
        '''
        Validate the tech.
        '''
        self.tech_id = normalize_tech_id(self.tech_id)
        self.tech_name = require_non_empty_string(self.tech_name)
        self.tech_name = normalize_string(self.tech_name)
        self.favorites = [normalize_string(favorite) for favorite in self.favorites]
        self.dislikes = [normalize_string(dislike) for dislike in self.dislikes]
        self.eligible_by_task_id = _coerce_eligible_map(dict(self.eligible_by_task_id))
        self.proficiency_by_task_id = _coerce_proficiency_map(dict(self.proficiency_by_task_id))


def tech_profile_equals(a: Tech, b: Tech) -> bool:
    '''
    True when two profiles match for persistence / import semantics.

    ``favorites`` and ``dislikes`` are compared order-insensitively (sorted).
    Maps are compared as sorted item tuples.
    '''
    elig_a = sorted(a.eligible_by_task_id.items())
    elig_b = sorted(b.eligible_by_task_id.items())
    prof_a = sorted((k, v.value) for k, v in a.proficiency_by_task_id.items())
    prof_b = sorted((k, v.value) for k, v in b.proficiency_by_task_id.items())
    return (
        a.tech_id == b.tech_id
        and a.tech_name == b.tech_name
        and a.daily_preference == b.daily_preference
        and sorted(a.favorites) == sorted(b.favorites)
        and sorted(a.dislikes) == sorted(b.dislikes)
        and elig_a == elig_b
        and prof_a == prof_b
    )
