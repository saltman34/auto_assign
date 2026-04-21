'''Home page — the Assignment Engine, with demo onboarding above the fold.

The Home page *is* the daily tool. The product name "Auto Assign" already
lives in the sidebar brand block, so the page header here names this specific
workflow ("Assignment Engine") rather than restating the brand. That also
removes the redundant mid-page "Assignment Engine" section divider that
previously sat directly under an identically-titled page header.
'''
from __future__ import annotations

from auto_assign.ui.demo_data_panel import render_demo_data_panel
from auto_assign.ui.page import render_page_header
from auto_assign.ui.schedule import (
    render_assignment_engine_outcome_banner,
    render_schedule_workflow,
)


def render_home_page() -> None:
    render_page_header(
        'Assignment Engine',
        'Upload a schedule, set task headcounts, then generate and publish assignments for a date and shift.',
        kicker='Daily workflow',
    )
    # Demo-data onboarding above the workflow so a fresh database lands on the
    # primary call-to-action; the panel collapses to a quiet expander once the
    # database has technicians.
    render_demo_data_panel()
    render_schedule_workflow()
    render_assignment_engine_outcome_banner()
