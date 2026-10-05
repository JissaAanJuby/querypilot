"""Design tokens and CSS injection for a non-default Streamlit look."""
import streamlit as st

CSS = """
<style>
:root {
  --qp-bg: #0e1117;
  --qp-card: #161b22;
  --qp-border: #262c36;
  --qp-accent: #10b981;
  --qp-accent-dim: #0f3d2e;
  --qp-warn: #f59e0b;
  --qp-error: #ef4444;
  --qp-text: #e6edf3;
  --qp-text-dim: #8b949e;
  --qp-mono: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
}

.qp-card {
  background: var(--qp-card);
  border: 1px solid var(--qp-border);
  border-radius: 10px;
  padding: 1rem 1.25rem;
  margin-bottom: 0.75rem;
}

.qp-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.25rem 0.7rem;
  border-radius: 999px;
  font-size: 0.8rem;
  font-weight: 600;
  margin-right: 0.4rem;
}
.qp-pill-ok     { background: var(--qp-accent-dim); color: var(--qp-accent); }
.qp-pill-warn   { background: #3a2a0f; color: var(--qp-warn); }
.qp-pill-error  { background: #3a1414; color: var(--qp-error); }
.qp-pill-pending{ background: #1c2128; color: var(--qp-text-dim); }

.qp-step {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.5rem 0;
  font-size: 0.92rem;
  color: var(--qp-text-dim);
  border-left: 2px solid var(--qp-border);
  padding-left: 0.9rem;
  margin-left: 0.4rem;
}
.qp-step-active { color: var(--qp-text); border-left-color: var(--qp-accent); }
.qp-step-done   { color: var(--qp-accent); border-left-color: var(--qp-accent); }
.qp-step-warn   { color: var(--qp-warn); border-left-color: var(--qp-warn); }
.qp-step-error  { color: var(--qp-error); border-left-color: var(--qp-error); }

.qp-title { font-size: 1.6rem; font-weight: 700; margin-bottom: 0; }
.qp-subtitle { color: var(--qp-text-dim); font-size: 0.95rem; margin-top: 0; }

.qp-mono { font-family: var(--qp-mono); font-size: 0.85rem; }

div[data-testid="stMetric"] {
  background: var(--qp-card);
  border: 1px solid var(--qp-border);
  border-radius: 10px;
  padding: 0.8rem 1rem;
}
</style>
"""


def inject():
    st.markdown(CSS, unsafe_allow_html=True)


def pill(label: str, kind: str = "pending") -> str:
    return f'<span class="qp-pill qp-pill-{kind}">{label}</span>'


def card_open():
    st.markdown('<div class="qp-card">', unsafe_allow_html=True)


def card_close():
    st.markdown("</div>", unsafe_allow_html=True)