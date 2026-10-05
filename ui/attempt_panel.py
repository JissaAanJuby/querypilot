"""Expandable per-attempt viewer for the self-correction loop."""
import streamlit as st

from ui.theme import pill


def render(result):
    if not result or not result.attempts:
        return

    st.markdown("#### Self-Correction Attempts")
    for a in result.attempts:
        if a.status == "ok":
            kind, label = "ok", "Succeeded"
        elif a.status == "empty":
            kind, label = "warn", "Empty result"
        elif a.status == "validation_failed":
            kind, label = "error", "Blocked by validator"
        else:
            kind, label = "error", "Execution failed"

        header = f"Attempt {a.number} — {label}"
        if a.number > 1 and a.status == "ok":
            header += " (correction worked)"

        with st.expander(header, expanded=(a.number == len(result.attempts))):
            st.markdown(pill(label, kind), unsafe_allow_html=True)
            st.code(a.sql, language="sql")
            if a.status != "ok":
                st.caption(f"Reason: {a.reason}")
            if getattr(a, "plausibility_warning", ""):
                st.warning(a.plausibility_warning)
            st.caption(f"{a.latency_s:.2f}s")