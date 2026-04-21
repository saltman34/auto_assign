'''
Local search post-pass: pairwise swaps that improve total compatibility score.

Runs after greedy or exact assignment; optional strict-dislike guardrails avoid
swaps that would newly assign a disliked task when that tech already holds a non-disliked one.
'''
from __future__ import annotations

from collections.abc import Mapping

from auto_assign.domain import Assignment

from .compatibility_scoring import compatibility_score, is_eligible_for_task, task_is_disliked
from .scoring_types import AssignmentScoringContext, ScoringWeights, TechScoringProfile


def local_swap_improvement(
    assignments: list[Assignment],
    *,
    profiles_by_tech_id: Mapping[str, TechScoringProfile],
    scoring_context: AssignmentScoringContext,
    weights: ScoringWeights,
    strict_dislike_avoidance: bool,
    pinned_tech_ids: frozenset[str] = frozenset(),
) -> list[Assignment]:
    '''
    Hill-climb by swapping task names between pairs of assignments until no
    improving swap exists (local optimum for this 2-opt neighborhood).

    ``pinned_tech_ids`` are never moved off their task — any pair involving a
    pinned technician is skipped. Used for manual eligibility overrides, where
    the operator explicitly placed a tech on a task and the swap post-pass must
    not relocate them even if another technician would score higher there.
    '''
    out = list(assignments)
    changed = True
    while changed:
        changed = False
        for i in range(len(out)):
            for j in range(i + 1, len(out)):
                ai = out[i]
                aj = out[j]
                if ai.technician_id in pinned_tech_ids or aj.technician_id in pinned_tech_ids:
                    continue
                pi = profiles_by_tech_id.get(ai.technician_id)
                pj = profiles_by_tech_id.get(aj.technician_id)
                if pi is None or pj is None:
                    continue

                tid_i_for_aj = aj.effective_catalog_task_id()
                tid_j_for_ai = ai.effective_catalog_task_id()
                if not is_eligible_for_task(pi, tid_i_for_aj) or not is_eligible_for_task(pj, tid_j_for_ai):
                    continue

                if strict_dislike_avoidance:
                    if task_is_disliked(pi, aj.task_name) and not task_is_disliked(pi, ai.task_name):
                        continue
                    if task_is_disliked(pj, ai.task_name) and not task_is_disliked(pj, aj.task_name):
                        continue

                current = compatibility_score(
                    pi,
                    ai.effective_catalog_task_id(),
                    ai.task_name,
                    scoring_context,
                    weights,
                ) + compatibility_score(
                    pj,
                    aj.effective_catalog_task_id(),
                    aj.task_name,
                    scoring_context,
                    weights,
                )
                swapped = compatibility_score(
                    pi,
                    tid_i_for_aj,
                    aj.task_name,
                    scoring_context,
                    weights,
                ) + compatibility_score(
                    pj,
                    tid_j_for_ai,
                    ai.task_name,
                    scoring_context,
                    weights,
                )
                if swapped > current:
                    out[i] = Assignment(
                        task_name=aj.task_name,
                        catalog_task_id=aj.catalog_task_id,
                        technician_id=ai.technician_id,
                        date_assigned=ai.date_assigned,
                        time_slot=ai.time_slot,
                    )
                    out[j] = Assignment(
                        task_name=ai.task_name,
                        catalog_task_id=ai.catalog_task_id,
                        technician_id=aj.technician_id,
                        date_assigned=aj.date_assigned,
                        time_slot=aj.time_slot,
                    )
                    changed = True
                    break
            if changed:
                break
    return out
