'''About page: engineering notes and operator guidance.'''

from __future__ import annotations

import html
from collections.abc import Callable

import streamlit as st

from auto_assign.ui.page import render_page_header

_ABOUT_TOPIC_PILLS_KEY = 'aa_about_topic_pills'

_ABOUT_STYLES = '''
<style>
.aa-about-intro {
  margin: 0;
  color: var(--aa-subtle);
  line-height: 1.55;
  max-width: 50rem;
  font-size: 1rem;
}
.aa-about-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-top: 0.65rem;
}
.aa-about-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 1rem;
  margin: 0.85rem 0 0.35rem 0;
}
.aa-about-card {
  background: linear-gradient(180deg, rgba(34,36,46,0.96) 0%, rgba(26,28,38,0.96) 100%);
  border: 1px solid var(--aa-border);
  border-radius: 12px;
  padding: 1rem 1.1rem;
}
.aa-about-card h4 {
  margin: 0 0 0.4rem 0;
  font-size: 0.98rem;
  letter-spacing: -0.01em;
  color: var(--aa-text);
}
.aa-about-card p {
  margin: 0;
  color: var(--aa-subtle);
  font-size: 0.9rem;
  line-height: 1.5;
}
.aa-about-rule {
  border: none;
  border-top: 1px solid var(--aa-border);
  margin: 1.35rem 0 1.1rem 0;
  opacity: 0.85;
}
.aa-about-section-title {
  font-family: var(--aa-font-display);
  font-size: 1.15rem;
  font-weight: 650;
  letter-spacing: -0.02em;
  color: var(--aa-text);
  margin: 0 0 0.4rem 0;
  line-height: 1.25;
  border: none;
  padding: 0;
}
.aa-about-lead {
  font-size: 0.96rem;
  color: var(--aa-subtle);
  line-height: 1.68;
  max-width: 46rem;
  margin: 0 0 0.85rem 0;
}
.aa-about-user-intro {
  margin-bottom: 1.25rem;
  padding: 1rem 1.15rem;
  border-radius: 12px;
  border: 1px solid var(--aa-border);
  border-left: 3px solid var(--aa-accent);
  background: rgba(38, 39, 48, 0.4);
}
.aa-about-user-intro .aa-about-band-lead {
  margin: 0.35rem 0 0.5rem 0;
  color: var(--aa-subtle);
  line-height: 1.55;
  font-size: 0.94rem;
  max-width: 46rem;
}
.aa-about-prose {
  font-size: 0.94rem;
  line-height: 1.65;
  color: var(--aa-subtle);
  max-width: 44rem;
}
.aa-about-prose p { margin: 0 0 0.65rem 0; }
.aa-about-prose p:last-child { margin-bottom: 0; }
.aa-about-prose ul, .aa-about-prose ol {
  margin: 0.35rem 0 0.65rem 0;
  padding-left: 1.2rem;
}
.aa-about-prose li { margin: 0.35rem 0; }
.aa-about-prose strong { color: var(--aa-text); }
.aa-about-prose .aa-about-table-wrap { margin-top: 0.5rem; }
.aa-about-chapter {
  margin-top: 1.5rem;
  padding: 1.35rem 1.4rem 1.45rem;
  border-radius: 14px;
  border: 1px solid rgba(58, 63, 75, 0.9);
  background: linear-gradient(168deg, rgba(36, 38, 48, 0.5) 0%, rgba(20, 22, 28, 0.35) 100%);
  box-shadow: 0 4px 26px rgba(0, 0, 0, 0.16);
}
.aa-about-chapter--first {
  margin-top: 0.15rem;
}
.aa-about-table-wrap {
  overflow-x: auto;
  margin: 0.35rem 0 0 0;
}
.aa-about-table-wrap table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}
.aa-about-table-wrap th,
.aa-about-table-wrap td {
  padding: 0.65rem 0.85rem;
  text-align: left;
  vertical-align: top;
  border-bottom: 1px solid var(--aa-border);
}
.aa-about-table-wrap th {
  font-weight: 600;
  color: var(--aa-text);
  font-size: 0.75rem;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}
.aa-about-table-wrap tr:last-child td { border-bottom: none; }
.aa-about-table-wrap td { color: var(--aa-subtle); line-height: 1.55; }
</style>
'''

_TOPIC_NOTES: dict[str, str] = {
    'Architecture': '''
**Layers**

- **`ui/`** — Streamlit pages: uploads, forms, and calls into core and repositories. No SQL embedded in UI code.
- **`core/`** — Schedule parsing, validation, greedy assignment, scoring weights, and manual override composition.
- **`domain/`** — Shared enums, entities, and validators consumed by core and persistence adapters.
- **`db/`** — SQLAlchemy models, session handling, and repository-style functions for assignments, technicians, tasks, and overrides.

**Rationale**

Separation keeps the assignment logic testable without a browser and limits blast radius when the schema or the UI changes.
    '''.strip(),
    'Data model': '''
**Primary entities**

- **Technicians** — Stable `tech_id`, display name, and task preferences; schedule CSV names resolve here before scoring.
- **Task catalog** — Canonical task names and default headcounts for the planning UI.
- **Assignments** — Rows keyed by work date, time slot, and slot index; **`draft`** for iteration, **`confirmed`** after publish.
- **Overrides** — Day-level availability (e.g. call-off, overtime) and slice-level manual pre-assignments, with draft/confirmed alignment to the assignment workflow.

**Persistence fit**

The workload is relational (history, slice reloads, fairness lookbacks). PostgreSQL supports indexed queries on date, status, and technician without denormalizing the scheduling story.
    '''.strip(),
    'Greedy assignment': '''
**Procedure**

1. Apply **manual pre-assignments** (fixed technician–task pairs) for the slice.
2. Build the **residual** task plan (remaining slots per task).
3. **Greedily** assign each open slot: among eligible technicians, pick the highest **compatibility score** (preferences and **confirmed** history within a **14-day** lookback), then continue until slots are filled or no candidate remains.

**Scoring inputs**

Weights combine liked/disliked tasks and recent **confirmed** assignments. The Streamlit UI does not expose scoring knobs; policy is fixed in code for consistency.

**Design trade-off**

A full constraint or ILP solver could seek a global optimum but adds operational cost, slower iteration, and opaque failure modes. The current stack favors **speed**, **auditability**, and a **single** operator-visible behavior.
    '''.strip(),
    'Reliability': '''
**Workflow**

- **Draft** rows support repeated **Generate draft** cycles without touching official history.
- **Publish** promotes the current date+shift slice to **confirmed** rows; **Assignment history** and fairness lookback read **confirmed** data only.

**Integrity**

- Republishing the same date+shift replaces that slice only, after explicit confirmation.
- Overrides follow the same draft/confirm pattern so audit trails stay aligned with published assignments.

**Engineering**

- **Alembic** migrations version schema changes for reproducible environments.
- **pytest** covers repositories, CSV ingestion, and manual override helpers so persistence and parsing stay stable as the UI evolves.
    '''.strip(),
}

_USER_CSV_TABLE_HTML = '''
<div class="aa-about-table-wrap">
  <table>
    <thead><tr><th>Column</th><th>Purpose</th></tr></thead>
    <tbody>
      <tr><td><code class="aa-mono">tech_name</code></td><td>Must match a name on <strong>Technician Profiles</strong> so the app knows who it is.</td></tr>
      <tr><td><code class="aa-mono">date</code></td><td>Work date as <code class="aa-mono">YYYY-MM-DD</code>. Only these dates show up in Step 1.</td></tr>
      <tr><td><code class="aa-mono">available_AM</code>, <code class="aa-mono">available_MID</code>, <code class="aa-mono">available_PM</code></td><td>Whether they could work that shift: <code class="aa-mono">1</code>/<code class="aa-mono">0</code>, yes/no, or true/false.</td></tr>
      <tr><td><code class="aa-mono">staffing_status</code></td><td>Example: <code class="aa-mono">call_off</code> in the file marks them out from the roster; you can still adjust people in Step 2.</td></tr>
    </tbody>
  </table>
</div>
'''.strip()

_USER_ENGINE_STEPS_HTML = '''
<ol>
  <li><strong>Date</strong> — Pick a date from your upload, then <strong>Continue</strong>. <strong>Change date</strong> switches days and clears draft work for the previous date (for this upload).</li>
  <li><strong>Call-offs and overtime</strong> — Optional. Call-off removes someone for the whole day; overtime adds someone per shift. <strong>Continue</strong> saves; use <strong>Change</strong> or <strong>Clear</strong> to fix mistakes.</li>
  <li><strong>Shift</strong> — AM, MID, or PM, then <strong>Continue</strong>. Changing shift later clears the draft and manual rows for the shift you leave.</li>
  <li><strong>Who’s available</strong> — Confirms the pool for this slice. You can’t assign more tasks than there are people in the pool.</li>
  <li><strong>Task counts</strong> — How many of each task you need. <strong>Remaining slots</strong> should end at zero. If you change counts after a draft, click <strong>Generate draft</strong> again. (How picks are made is covered in the auto-placement question below.)</li>
  <li><strong>Manual assignments (optional)</strong> — Lock specific people to tasks if you need to. Use <strong>Add</strong> for each row; dropdowns alone don’t count. You can skip this step.</li>
  <li><strong>Draft and publish</strong> — <strong>Generate draft</strong> to preview. Then <strong>Publish</strong> to save officially or <strong>Discard draft</strong> to drop the preview. After publishing, follow the on-screen next steps for export or a new run.</li>
</ol>
'''.strip()

_USER_TROUBLE_HTML = '''
<ul>
  <li><strong>Stops after I pick a date</strong> — Database isn’t connected. Set Postgres in your environment and run <code class="aa-mono">alembic upgrade head</code>; the sidebar should show <strong>Database ready</strong>.</li>
  <li><strong>Can’t move past the date step</strong> — Add at least one task under <strong>Task Catalog</strong>.</li>
  <li><strong>Remaining slots won’t go to zero</strong> — Step 5 totals must exactly match how many technicians are in the pool for that shift.</li>
  <li><strong>Draft won’t save / unknown technician</strong> — Every name in the CSV needs a matching profile under <strong>Technician Profiles</strong>.</li>
  <li><strong>Draft looks wrong after I changed something</strong> — Run <strong>Generate draft</strong> again after you change headcounts, the pool, or manual rows.</li>
  <li><strong>Nobody in the pool (Step 4)</strong> — Check the CSV for that date and shift, and Step 2 call-offs.</li>
</ul>
'''.strip()

_AUTO_PLACEMENT_DETAIL_HTML = '''
<ul>
  <li><strong>Published work is what counts</strong> — Only assignments you’ve <strong>published</strong> affect how the app balances load. Drafts are previews.</li>
  <li><strong>Recent history matters</strong> — The app looks at roughly the last two weeks of <strong>published</strong> work to spread tasks more fairly. You can’t change those rules from the screen.</li>
  <li><strong>Same inputs, same draft</strong> — Re-running with the same file, date, shift, and settings gives the same suggestion, so behavior stays predictable.</li>
  <li><strong>What you can change</strong> — Who is available, how many of each task you need, and optional manual locks—then generate the draft again.</li>
</ul>
<p style="margin-top:0.75rem;">Technical write-ups live under the <strong>Engineering Notes</strong> tab on this page.</p>
'''.strip()


def _faq_before() -> None:
    st.markdown(
        '''<div class="aa-about-prose">
<p>Work through these once (or whenever your environment changes) before you rely on <strong>Home</strong> for a real run:</p>
<ul>
  <li><strong>Database</strong> — The sidebar should say <strong>Database ready</strong>. If it doesn’t, connect Postgres (see your team’s deployment notes), then run <code class="aa-mono">alembic upgrade head</code>. Tasks, profiles, and overrides all need the database.</li>
  <li><strong>Technician profiles</strong> — Every <code class="aa-mono">tech_name</code> in your schedule file must match someone saved under <strong>Technician Profiles</strong>.</li>
  <li><strong>Task catalog</strong> — Add at least one task. Step 5 builds counts from this list.</li>
  <li><strong>Schedule file</strong> — Shape and columns are described in the next question.</li>
</ul>
</div>''',
        unsafe_allow_html=True,
    )


def _faq_schedule() -> None:
    st.markdown(
        f'''<div class="aa-about-prose">
<p>The file you upload is the starting picture of who <em>could</em> work. Step 2 lets you add call-offs and overtime on top.</p>
<p><strong>Include:</strong> <code class="aa-mono">tech_name</code>, <code class="aa-mono">date</code>, one availability column per shift (for example <code class="aa-mono">available_AM</code>), and <code class="aa-mono">staffing_status</code>. Use <code class="aa-mono">YYYY-MM-DD</code> for dates. Shift cells can be 1/0, yes/no, or true/false.</p>
{_USER_CSV_TABLE_HTML}
</div>''',
        unsafe_allow_html=True,
    )


def _faq_engine() -> None:
    st.markdown(
        f'''<div class="aa-about-prose">
<p>On <strong>Home</strong>, go in order and press <strong>Continue</strong> when you’re happy with each step. There is also a <strong>Quick reference</strong> expander on that page while you work.</p>
{_USER_ENGINE_STEPS_HTML}
</div>''',
        unsafe_allow_html=True,
    )


def _faq_draft() -> None:
    st.markdown(
        '''<div class="aa-about-prose">
<p>Each run is for one <strong>date</strong> and <strong>shift</strong> at a time. A <strong>draft</strong> is a preview you can regenerate or throw away; <strong>published</strong> rows are what the business record and history use.</p>
<ul>
  <li><strong>Draft</strong> — Created by <strong>Generate draft</strong>. Download or <strong>Discard draft</strong> anytime. Drafts do not appear in <strong>Assignment history</strong>.</li>
  <li><strong>Published</strong> — When you <strong>Publish</strong>, that slice is saved as the official assignment. It shows up in history and is used when the app balances future work.</li>
  <li><strong>Doing it again for the same day and shift</strong> — Change inputs if you need to, generate a new draft, then <strong>Publish</strong> again and confirm. Other dates are left as they were.</li>
</ul>
</div>''',
        unsafe_allow_html=True,
    )


def _faq_auto_placement() -> None:
    st.markdown(
        f'''<div class="aa-about-prose">
<p>The app scores who fits which task using rules built into the product—you won’t see sliders or toggles for that on <strong>Home</strong>. After you change who is available, task counts, or manual locks, always run <strong>Generate draft</strong> again.</p>
{_AUTO_PLACEMENT_DETAIL_HTML}
</div>''',
        unsafe_allow_html=True,
    )


def _faq_trouble() -> None:
    st.markdown(
        f'<div class="aa-about-prose">{_USER_TROUBLE_HTML}</div>',
        unsafe_allow_html=True,
    )


def _faq_nav() -> None:
    st.markdown(
        '''<div class="aa-about-prose">
<p>Use the sidebar to move between these areas:</p>
<div class="aa-about-table-wrap">
  <table>
    <thead>
      <tr>
        <th>Page</th>
        <th>Use it to…</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><strong>Home</strong></td>
        <td>Upload a schedule, walk the steps, generate a draft, publish or discard.</td>
      </tr>
      <tr>
        <td><strong>Technician Profiles</strong></td>
        <td>Maintain people, IDs, and task preferences so the CSV and scoring line up.</td>
      </tr>
      <tr>
        <td><strong>Task Catalog</strong></td>
        <td>Define tasks and default counts for Step 5.</td>
      </tr>
      <tr>
        <td><strong>Assignment history</strong></td>
        <td>Review and export <strong>published</strong> work only (not drafts).</td>
      </tr>
      <tr>
        <td><strong>About this app</strong></td>
        <td>Read this help (For users) or stack notes (Engineering Notes).</td>
      </tr>
    </tbody>
  </table>
</div>
</div>''',
        unsafe_allow_html=True,
    )


_USER_OPERATOR_FAQ: tuple[tuple[str, Callable[[], None]], ...] = (
    ('What do I need before I run the assignment engine?', _faq_before),
    ('What columns and formats does my schedule CSV need?', _faq_schedule),
    ('How does the seven-step flow on Home work?', _faq_engine),
    ('What is the difference between a draft and a published assignment?', _faq_draft),
    ('How does auto-placement decide who gets which task?', _faq_auto_placement),
    ('Something went wrong — what should I check?', _faq_trouble),
    ('What is each sidebar page for?', _faq_nav),
)


def _render_user_operator_faq() -> None:
    for question, body in _USER_OPERATOR_FAQ:
        with st.expander(f'**{question}**', expanded=False):
            body()


def render_about_page() -> None:
    st.markdown(_ABOUT_STYLES, unsafe_allow_html=True)

    render_page_header(
        'About this app',
        'A concise guide for day-to-day operators, plus engineering notes on the stack and design.',
        kicker='Reference',
    )

    st.markdown(
        '''
<div class="aa-hero">
  <div class="aa-kicker">Overview</div>
  <p class="aa-about-intro">
    <strong>Auto Assign</strong> turns a schedule CSV, task headcounts, and technician preferences into
    shift-level task assignments. Use the tabs below for <strong>operator steps</strong> or <strong>engineering notes</strong>.
  </p>
  <div class="aa-about-chip-row">
    <span class="aa-chip">Streamlit · SQLAlchemy · PostgreSQL</span>
    <span class="aa-chip">Greedy scoring · manual overrides</span>
    <span class="aa-chip">Draft → publish checkpoint</span>
  </div>
</div>
''',
        unsafe_allow_html=True,
    )
    st.markdown('<hr class="aa-about-rule" />', unsafe_allow_html=True)
    user_tab, engineering_tab = st.tabs(['For users', 'Engineering Notes'])

    with user_tab:
        st.markdown(
            '''
<div class="aa-about-user-intro">
  <div class="aa-kicker">For users</div>
  <p class="aa-about-band-lead">
    This tab is <strong>practical help</strong> in a Q & A format for users running the tool day to day.
    For architecture, data model, and deeper assignment policy, switch to <strong>Engineering Notes</strong>.
  </p>
</div>
''',
            unsafe_allow_html=True,
        )
        _render_user_operator_faq()
        with st.expander('**What is stored in this app?**', expanded=False):
            st.markdown(
                '''
- **Technicians** — Identity and preferences.
- **Task catalog** — Task labels and defaults.
- **Assignments** — Draft workspace and confirmed history per slice.
- **Overrides** — Day availability and slice-level manual rows; aligned with draft/publish.

Fairness and history scoring use **confirmed** assignments only.
                '''.strip()
            )

    with engineering_tab:
        st.markdown(
            '''
<div class="aa-about-chapter aa-about-chapter--first">
  <h3 class="aa-about-section-title">Backend stack</h3>
  <p class="aa-about-lead" style="margin-bottom:0.75rem;">
    Same card treatment as the rest of the app: stack choices and why they fit this problem.
  </p>
  <div class="aa-card">
    <div class="aa-kicker">Stack</div>
    <div class="aa-card-title">Backend choices and rationale</div>
    <div class="aa-about-table-wrap">
      <table>
        <thead>
          <tr>
            <th>Choice</th>
            <th>Rationale</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><strong>Streamlit</strong></td>
            <td>Fast internal UI with minimal front-end surface area; keeps focus on domain logic.</td>
          </tr>
          <tr>
            <td><strong>PostgreSQL</strong></td>
            <td>Relational storage for dated slices, history, and indexed fairness lookbacks.</td>
          </tr>
          <tr>
            <td><strong>SQLAlchemy + repositories</strong></td>
            <td>Explicit persistence boundary; database access stays testable and centralized.</td>
          </tr>
          <tr>
            <td><strong>Alembic</strong></td>
            <td>Versioned migrations for reproducible schema and clear evolution in source control.</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</div>
''',
            unsafe_allow_html=True,
        )

        st.markdown(
            '''
<div class="aa-about-chapter">
  <h3 class="aa-about-section-title">Design overview</h3>
  <p class="aa-about-lead" style="margin-bottom:0.75rem;">
    Four themes the codebase is organized around.
  </p>
  <div class="aa-about-grid">
    <div class="aa-about-card">
      <h4>Architecture</h4>
      <p>UI orchestrates workflow; core holds assignment logic; db persists via repositories; domain shares types and validation.</p>
    </div>
    <div class="aa-about-card">
      <h4>Data model</h4>
      <p>Technicians, task catalog, assignments, and overrides map to relational tables and slice-oriented queries.</p>
    </div>
    <div class="aa-about-card">
      <h4>Greedy assignment</h4>
      <p>Manual locks first, then greedy fill from a weighted compatibility score.</p>
    </div>
    <div class="aa-about-card">
      <h4>Reliability</h4>
      <p>Draft vs confirmed, confirmed-only scoring inputs, migrations, targeted tests.</p>
    </div>
  </div>
</div>
''',
            unsafe_allow_html=True,
        )

        st.markdown(
            '''
<div class="aa-about-chapter">
  <h3 class="aa-about-section-title">Extended engineering notes</h3>
  <p class="aa-about-lead" style="margin-bottom:0.35rem;">
    Pick a topic; the bordered panel below updates. Same pattern as tuning the engine from Step 5—high level first, detail on demand.
  </p>
</div>
''',
            unsafe_allow_html=True,
        )
        topic_options = ['Architecture', 'Data model', 'Greedy assignment', 'Reliability']
        selected = st.pills(
            'Topic',
            options=topic_options,
            selection_mode='single',
            default='Greedy assignment',
            key=_ABOUT_TOPIC_PILLS_KEY,
            label_visibility='collapsed',
            width='stretch',
        )
        active = selected if isinstance(selected, str) and selected in _TOPIC_NOTES else 'Greedy assignment'

        with st.container(border=True):
            st.markdown(
                f'''
<div class="aa-kicker">Notes</div>
<div class="aa-card-title" style="margin:0 0 0.5rem 0;">{html.escape(active)}</div>
''',
                unsafe_allow_html=True,
            )
            st.markdown(_TOPIC_NOTES[active])
