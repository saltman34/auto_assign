# Proficiency rubric (managers)

Rubric for rating one combined proficiency per technician and catalog task — judging speed and quality together — along with how eligibility differs from proficiency.

## Eligibility vs proficiency

| Concept | Meaning |
|--------|---------|
| **Eligibility** | Hard gate: if a technician is **not eligible** for a task, the assigner will **never** place them on that task. Use for certifications, training completion, policy, or “not yet cleared solo.” |
| **Proficiency** | Soft signal among **eligible** technicians: higher levels add a small **score bonus** in the greedy engine so stronger people are preferred when ties and trade-offs arise. |

Absent eligibility entries default to **eligible**. Absent proficiency entries default to **Independent** with **no** proficiency bonus (same as “no rating yet”).

## Ordinal levels (speed + quality)

When speed and quality disagree, rate at the **lower** level (quality caps the label).

### Novice

- **Speed:** Slower than team norm; needs frequent check-ins or pairing.
- **Quality:** Work often needs correction, rework, or second review before it is trusted.

### Independent

- **Speed:** Meets team expectations with normal supervision.
- **Quality:** Output meets standard; occasional questions are fine.

### Strong

- **Speed:** Faster than typical; rarely blocks on unknowns.
- **Quality:** Consistently clean work; little rework.

### Expert

- **Speed:** Among the fastest; can unblock others.
- **Quality:** Sets the bar; handles edge cases or coaches others on this task.

## Implementation note

In the database, proficiency is stored per **catalog `task_id`** (see `tasks` table), not only by display name, so renaming a task label does not silently break ratings.
