'''
Task catalog for the app (IDs, display names, default headcounts).

Assignment scoring coefficients are **not** here—they live in
``auto_assign.core.assignment.scoring_weights_config`` so task definitions and
greedy tuning evolve independently.

Favorites and dislikes on technician profiles must use these display names
(after the same normalization as ``normalize_string`` in the domain).
'''

tasks = [
    {'task_id': '1', 'task_name': 'Clinicals', 'default_count': 0},
    {'task_id': '2', 'task_name': 'Recuts', 'default_count': 0},
    {'task_id': '3', 'task_name': 'Scrolls', 'default_count': 0},
    {'task_id': '4', 'task_name': 'Embedding', 'default_count': 0},
    {'task_id': '5', 'task_name': 'Exhaust Checks', 'default_count': 0},
    {'task_id': '6', 'task_name': 'Grossing', 'default_count': 0},
]
