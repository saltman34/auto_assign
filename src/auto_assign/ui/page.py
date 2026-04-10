'''Global Streamlit page chrome and home page copy.'''

from __future__ import annotations

import html as html_lib

import streamlit as st


def configure_page() -> None:
    st.set_page_config(page_title='Auto Assign', page_icon=':robot:', layout='wide')


def render_page_header(title: str, subtitle: str, *, kicker: str | None = None) -> None:
    k = (
        f'<div class="aa-kicker">{html_lib.escape(kicker)}</div>'
        if kicker
        else ''
    )
    st.markdown(
        f'''<div class="aa-page-head">
  {k}
  <h1 class="aa-page-title">{html_lib.escape(title)}</h1>
  <p class="aa-page-lead">{html_lib.escape(subtitle)}</p>
</div>''',
        unsafe_allow_html=True,
    )


def render_theme() -> None:
    st.markdown(
        '''
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
  --aa-bg: #0E1117;
  --aa-panel: #262730;
  --aa-text: #FAFAFA;
  --aa-subtle: #C9CDD3;
  --aa-border: #3A3F4B;
  --aa-primary: #34d399;
  --aa-accent: #10b981;
  --aa-font-display: "DM Sans", system-ui, -apple-system, sans-serif;
  --aa-font-mono: "JetBrains Mono", ui-monospace, monospace;
}

html, body, [class*="css"] {
  color: var(--aa-text);
}

[data-testid="stAppViewContainer"],
[data-testid="stAppViewContainer"] .stMarkdown,
[data-testid="stAppViewContainer"] p,
[data-testid="stAppViewContainer"] label {
  font-family: var(--aa-font-display);
}

[data-testid="stAppViewContainer"] code,
[data-testid="stAppViewContainer"] pre,
.aa-mono {
  font-family: var(--aa-font-mono);
  font-size: 0.88em;
}

[data-testid="stAppViewContainer"] {
  background: var(--aa-bg);
}

[data-testid="stSidebar"] {
  background: var(--aa-panel);
  border-right: 1px solid var(--aa-border);
}

[data-testid="stSidebar"] * {
  color: #e2e8f0 !important;
}

[data-testid="stSidebar"] .stRadio label {
  font-weight: 500;
  letter-spacing: 0.01em;
}

.aa-sidebar-brand {
  padding-bottom: 0.85rem;
  margin-bottom: 0.65rem;
  border-bottom: 1px solid var(--aa-border);
}

.aa-sidebar-brand-title {
  font-family: var(--aa-font-display);
  font-size: 1.28rem;
  font-weight: 700;
  letter-spacing: -0.03em;
  line-height: 1.2;
  margin: 0;
  color: #fff !important;
}

.aa-sidebar-brand-tagline {
  font-size: 0.8125rem;
  color: var(--aa-subtle) !important;
  margin: 0.35rem 0 0 0;
  font-weight: 400;
}

.aa-sidebar-meta {
  margin-top: 0.65rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  align-items: center;
}

.aa-page-head {
  margin-bottom: 1.15rem;
}

.aa-page-title {
  font-family: var(--aa-font-display);
  font-size: 2rem;
  font-weight: 700;
  letter-spacing: -0.035em;
  line-height: 1.12;
  margin: 0 0 0.4rem 0;
  color: var(--aa-text);
  border: none;
  padding: 0;
}

.aa-page-lead {
  font-size: 1.0625rem;
  color: var(--aa-subtle);
  margin: 0;
  font-weight: 400;
  max-width: 44rem;
  line-height: 1.5;
}

.aa-hero {
  background: linear-gradient(135deg, rgba(16,185,129,0.14) 0%, rgba(52,211,153,0.08) 50%, rgba(38,39,48,0.6) 100%);
  border: 1px solid var(--aa-border);
  border-left: 3px solid var(--aa-accent);
  border-radius: 14px;
  padding: 1.15rem 1.25rem;
  margin-bottom: 1rem;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.22);
}

.aa-card {
  background: linear-gradient(180deg, rgba(38,39,48,0.98) 0%, rgba(30,31,40,0.95) 100%);
  border: 1px solid var(--aa-border);
  border-left: 3px solid var(--aa-accent);
  border-radius: 12px;
  padding: 1rem 1.1rem;
  margin-bottom: 0.75rem;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.2);
}

.aa-step {
  background: linear-gradient(180deg, rgba(34,36,46,0.96) 0%, rgba(26,28,38,0.96) 100%);
  border: 1px solid var(--aa-border);
  border-radius: 12px;
  padding: 0.8rem 0.95rem;
  margin: 0.35rem 0 0.7rem 0;
}

.aa-step-title {
  font-size: 1.02rem;
  font-weight: 650;
  letter-spacing: -0.01em;
  margin: 0;
}

.aa-step-sub {
  color: var(--aa-subtle);
  margin-top: 0.25rem;
  line-height: 1.4;
  font-size: 0.92rem;
}

.aa-chip {
  display: inline-block;
  padding: 0.2rem 0.52rem;
  margin: 0.2rem 0.35rem 0.1rem 0;
  border-radius: 999px;
  font-size: 0.74rem;
  border: 1px solid var(--aa-border);
  background: rgba(52, 211, 153, 0.08);
  color: var(--aa-text);
}

.aa-step-divider {
  border-top: 1px solid var(--aa-border);
  margin: 0.9rem 0 1rem 0;
  opacity: 0.9;
}

.aa-card-title {
  font-weight: 600;
  font-size: 1.05rem;
  letter-spacing: -0.02em;
  margin: 0 0 0.35rem 0;
  color: var(--aa-text);
}

.aa-kicker {
  letter-spacing: 0.1em;
  font-size: 0.6875rem;
  font-weight: 700;
  text-transform: uppercase;
  color: var(--aa-primary);
  margin-bottom: 0.4rem;
}

.aa-muted {
  color: var(--aa-subtle);
  line-height: 1.45;
}

.aa-pill {
  display: inline-block;
  padding: 0.22rem 0.6rem;
  border-radius: 999px;
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  border: 1px solid var(--aa-border);
  background: rgba(52, 211, 153, 0.12);
  color: var(--aa-primary) !important;
}

.aa-pill--ok {
  background: rgba(52, 211, 153, 0.15);
  border-color: rgba(52, 211, 153, 0.35);
  color: var(--aa-primary) !important;
}

.aa-pill--warn {
  background: rgba(251, 191, 36, 0.12);
  border-color: rgba(251, 191, 36, 0.35);
  color: #fbbf24 !important;
}

.aa-pill--neutral {
  background: rgba(148, 163, 184, 0.12);
  border-color: var(--aa-border);
  color: var(--aa-subtle) !important;
}

.aa-empty {
  border: 1px dashed var(--aa-border);
  border-radius: 12px;
  padding: 1.25rem 1.1rem;
  text-align: center;
  color: var(--aa-subtle);
  background: rgba(14, 17, 23, 0.5);
  margin: 0.5rem 0;
}

[data-testid="stMetric"] {
  background: rgba(22, 28, 38, 0.95);
  border: 1px solid rgba(52, 211, 153, 0.2);
  border-radius: 12px;
  padding: 0.45rem 0.55rem;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.15);
}

[data-testid="stDataFrame"] {
  border: 1px solid var(--aa-border);
  border-radius: 12px;
  overflow: hidden;
}

[data-testid="baseButton-primary"] {
  font-weight: 600 !important;
  box-shadow: 0 2px 14px rgba(16, 185, 129, 0.28) !important;
}
</style>
''',
        unsafe_allow_html=True,
    )
