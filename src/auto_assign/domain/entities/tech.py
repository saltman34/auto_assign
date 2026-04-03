from dataclasses import dataclass
from auto_assign.domain.validators.primitives import (
    normalize_string,
    normalize_tech_id,
    require_non_empty_string,
)
from auto_assign.domain.enums import DailyPreference

@dataclass
class Tech:
    '''
    Represents a technician.
    '''
    tech_id: str
    tech_name: str
    daily_preference: DailyPreference
    favorites: list[str]
    dislikes: list[str]


    def __post_init__(self):
        '''
        Validate the tech.
        '''
        self.tech_id = normalize_tech_id(self.tech_id)
        self.tech_name = require_non_empty_string(self.tech_name)
        self.tech_name = normalize_string(self.tech_name)
        self.favorites = [normalize_string(favorite) for favorite in self.favorites]
        self.dislikes = [normalize_string(dislike) for dislike in self.dislikes]


def tech_profile_equals(a: Tech, b: Tech) -> bool:
    '''
    True when two profiles match for persistence / import semantics.

    ``favorites`` and ``dislikes`` are compared order-insensitively (sorted).
    '''
    return (
        a.tech_id == b.tech_id
        and a.tech_name == b.tech_name
        and a.daily_preference == b.daily_preference
        and sorted(a.favorites) == sorted(b.favorites)
        and sorted(a.dislikes) == sorted(b.dislikes)
    )
