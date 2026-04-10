'''Small shared Streamlit presentation helpers (theme classes live in ``page.render_theme``).'''

from __future__ import annotations

import streamlit as st


def render_step_panel(title: str, subtitle: str | None = None) -> None:
    sub = f'<div class="aa-step-sub">{subtitle}</div>' if subtitle else ''
    st.markdown(
        f'<div class="aa-step"><div class="aa-step-title">{title}</div>{sub}</div>',
        unsafe_allow_html=True,
    )


def render_step_divider() -> None:
    st.markdown('<div class="aa-step-divider"></div>', unsafe_allow_html=True)


def render_context_chips(pairs: list[tuple[str, str]]) -> None:
    chips = ''.join(f'<span class="aa-chip">{k}: {v}</span>' for k, v in pairs if v)
    if chips:
        st.markdown(chips, unsafe_allow_html=True)
