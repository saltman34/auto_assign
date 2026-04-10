'''
Default bonuses and penalties for greedy compatibility scoring.

**Why a separate module from the DB-backed task catalog:** task definitions (IDs, labels,
default headcounts) changes for product reasons; scoring coefficients change
when tuning assignment quality. Keeping them apart avoids a single bloated
config and clarifies import boundaries.

Override per call with a custom ``ScoringWeights`` instance; formulas live in
``compatibility_scoring``.
'''
from __future__ import annotations

from .scoring_types import ScoringWeights

# Single place to tune relative point values (abstract units; adjust as a set).
DEFAULT_SCORING_WEIGHTS = ScoringWeights(
    favorite_bonus=2.0,
    dislike_base_penalty=3.0,
    disliked_task_repeat_penalty=2.0,
    max_repeat_penalty_multiplier=5,
    fairness_disliked_load_penalty=1.0,
    consistency_bonus=3.0,
    variation_bonus=3.0,
)
