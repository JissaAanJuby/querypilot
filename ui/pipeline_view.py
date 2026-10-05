"""Renders the question -> schema -> SQL -> validate -> execute -> correct pipeline
as a live, step-by-step status list."""
import streamlit as st

STEPS = [
    "Schema selected",
    "SQL generated",
    "SQL validated",
    "Query executed",
    "Result assessed",
    "Self-correction",
    "Final answer",
]


def render(result, prune_used: bool):
    """result: an AgentResult from agent.corrector.run_agent, or None pre-run."""
    if result is None:
        html = "".join(
            f'<div class="qp-step">○ {s}</div>' for s in STEPS
        )
        st.markdown(html, unsafe_allow_html=True)
        return

    attempts = result.attempts
    lines = []
    lines.append(f'<div class="qp-step qp-step-done">✓ Schema selected'
                  f'{" (pruned)" if prune_used else ""}</div>')

    if not attempts:
        lines.append('<div class="qp-step qp-step-error">✗ SQL generation failed — '
                      f'{result.error}</div>')
        st.markdown("".join(lines), unsafe_allow_html=True)
        return

    lines.append('<div class="qp-step qp-step-done">✓ SQL generated</div>')

    first = attempts[0]
    if first.status == "validation_failed":
        lines.append(f'<div class="qp-step qp-step-error">✗ Validation blocked: '
                      f'{first.reason}</div>')
    else:
        lines.append('<div class="qp-step qp-step-done">✓ SQL validated</div>')
        lines.append('<div class="qp-step qp-step-done">✓ Query executed</div>')

    if len(attempts) > 1:
        for a in attempts[:-1]:
            icon = "⚠" if a.status == "empty" else "↻"
            lines.append(f'<div class="qp-step qp-step-warn">{icon} Attempt {a.number}: '
                          f'{a.reason}</div>')
        lines.append(f'<div class="qp-step qp-step-active">↻ Self-correction: '
                      f'{len(attempts)} attempt(s) total</div>')
    else:
        lines.append('<div class="qp-step qp-step-done">✓ Self-correction: not needed '
                      '(first attempt succeeded)</div>')

    last = attempts[-1]
    if last.status == "ok":
        note = " (corrected)" if len(attempts) > 1 else ""
        lines.append(f'<div class="qp-step qp-step-done">✓ Final answer{note}</div>')
        if getattr(last, "plausibility_warning", ""):
            lines.append(f'<div class="qp-step qp-step-warn">⚠ {last.plausibility_warning}</div>')
    elif last.status == "empty":
        lines.append('<div class="qp-step qp-step-warn">⚠ Final: query ran but returned '
                      'zero rows</div>')
    else:
        lines.append(f'<div class="qp-step qp-step-error">✗ Final: {last.reason}</div>')

    st.markdown("".join(lines), unsafe_allow_html=True)