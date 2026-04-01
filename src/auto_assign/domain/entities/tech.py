from dataclasses import dataclass
from auto_assign.domain.validators.primitives import normalize_string, require_non_empty_string, require_boolean
from auto_assign.domain.enums import DailyPreference, Staffing_Status

@dataclass
class Tech:
    '''
    Represents a technician.
    '''
    tech_id: str
    tech_name: str
    tech_availableAM: bool
    tech_availableMID: bool
    tech_availablePM: bool
    staff_status: Staffing_Status
    tech_daily_preference: DailyPreference
    tech_favorites: list[str]
    tech_dislikes: list[str]


    def __post_init__(self):
        '''
        Validate the tech.
        '''
        self.tech_id = require_non_empty_string(self.tech_id)
        self.tech_name = require_non_empty_string(self.tech_name)
        self.tech_name = normalize_string(self.tech_name)
        self.tech_availableAM = require_boolean(self.tech_availableAM)
        self.tech_availableMID = require_boolean(self.tech_availableMID)
        self.tech_availablePM = require_boolean(self.tech_availablePM)
        self.tech_favorites = [normalize_string(favorite) for favorite in self.tech_favorites]
        self.tech_dislikes = [normalize_string(dislike) for dislike in self.tech_dislikes]