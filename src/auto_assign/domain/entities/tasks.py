from dataclasses import dataclass
from auto_assign.domain.validators.primitives import normalize_string, require_non_empty_string, require_positive_integer

@dataclass
class Task:
    '''
    Represents a task to be assigned to a technician.
    '''
    task_id: str
    task_name: str
    default_count: int = 0

    
    def __post_init__(self):
        '''
        Validate the task.
        '''
        self.task_id = require_non_empty_string(self.task_id)
        self.task_name = require_non_empty_string(self.task_name)
        self.task_name = normalize_string(self.task_name)
        self.default_count = require_positive_integer(self.default_count)