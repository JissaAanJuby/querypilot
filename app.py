"""QueryPilot: Streamlit UI."""
import os
import re

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

from agent.corrector import run_agent
from agent.generator import GeminiClient, LLMError
from agent.schema import extract_schema

load_dotenv()
DB_PATH = "data/chinook.db"

st.set_page_config(page_title="QueryPilot", page_icon="🧭", layout="wide")


@st.cache_data
def load_schema(path: str) -> dict:
    return extract_schema(path)


@st.cache_resource
def get_client(model: str) -> GeminiClient:
    return GeminiClient(model=model)


def _is_date_col(series: pd.Series) -> bool:
    name = str(series.name).lower()
    if any(k in name for k in ("date", "year", "month")):
        return True
    if series.dtype == object:
        s = series.dropna().astype(str)
        return len(s) > 0 and bool(s.str.match(r"^\d{4}-\d{2}(-\d{2})?").all())
    return False


def choose_chart(df: pd.DataFrame):
    """Deterministic chart choice from column types (no LLM involved)."""
    if df is None or df.empty:
        return None
    if df.shape == (1, 1) and pd.api.types.is_numeric_dtype(df.iloc[:, 0]):
        return {"kind": "metric", "label": str(df.columns[0]), "value": df.iloc[0, 0]}

    date_col = next((c for c in df.columns if _is_date_col(df[c])), None)
    numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and c != date_col]
    if not numeric:
        return None

    if date_col is not None:
        fig = px.line(df.sort_values(date_col), x=date_col, y=numeric, markers=True)
        return {"kind": "figure", "fig": fig}

    data = df.head(30)
    others = [c for c in df.columns if c not in numeric]
    if others:                       # category + numeric(s)
        fig = px.bar(data, x=others[0], y=numeric)
    elif len(numeric) >= 2:          # two numeric columns
        fig = px.bar(data, x=numeric[0], y=numeric[1:])
    else:
        return None
    return {"kind": "figure", "fig": fig}


def explain(result) -> str:
    if not result.success:
        return "QueryPilot could not produce a working query within the retry limit."
    rows, cols = result.df.shape
    text = f"Returned {rows} row(s) and {cols} column(s)"
    if len(result.attempts) > 1:
        text += f" after {len(result.attempts)} attempts (the agent corrected its own query)"
    text += ". Note: a query that runs successfully is not guaranteed to be semantically correct, so review the SQL."
    return text


# ----------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Settings")
    st.markdown(f"**Database:** `{DB_PATH}` (read-only)")
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    st.markdown(f"**Model:** `{model}`")
    max_retries = st.slider("Max retries", 0, 5, 3)
    max_rows = st.number_input("Max rows", min_value=10, max_value=1000, value=100, step=10)
    self_correct = st.checkbox("Self-correction", value=True)
    prune = st.checkbox("Schema pruning (first attempt)", value=False)

# -------------------------------------------------------------------- main
st.title("🧭 QueryPilot")
st.caption("Ask your database anything. Failed SQL is diagnosed and retried automatically.")

question = st.text_input(
    "Your question", placeholder="Which artist generated the most revenue?"
)
run = st.button("Run Query", type="primary")

if run and question.strip():
    try:
        client = get_client(model)
    except LLMError as e:
        st.error(str(e))
        st.stop()

    schema = load_schema(DB_PATH)
    with st.spinner("Thinking..."):
        result = run_agent(
            question.strip(), client, DB_PATH, schema,
            max_retries=max_retries, max_rows=int(max_rows),
            self_correct=self_correct, prune=prune,
        )

    st.subheader("Generated SQL")
    shown_sql = result.final_sql or (result.attempts[-1].sql if result.attempts else "")
    st.code(shown_sql or "-- no SQL produced", language="sql")

    st.subheader("Execution")
    c1, c2, c3, c4 = st.columns(4)
    status = "Success" if result.answered else ("Empty result" if result.success else "Failed")
    c1.metric("Status", status)
    c2.metric("Attempts", len(result.attempts))
    c3.metric("Latency", f"{result.total_latency_s:.2f}s")
    c4.metric("Rows", 0 if result.df is None else len(result.df))

    if result.error:
        st.error(result.error)
    if result.empty:
        st.warning("The query ran but returned no rows. The question may need rephrasing.")
    if result.truncated:
        st.warning(f"Result was capped at {int(max_rows)} rows and may be incomplete.")

    if result.df is not None and not result.df.empty:
        st.subheader("Results")
        st.dataframe(result.df, use_container_width=True)

        st.subheader("Visualization")
        chart = choose_chart(result.df)
        if chart is None:
            st.info("No automatic chart for this result shape.")
        elif chart["kind"] == "metric":
            st.metric(chart["label"], chart["value"])
        else:
            st.plotly_chart(chart["fig"], use_container_width=True)

    st.subheader("Explanation")
    st.write(explain(result))

    st.subheader("Agent Activity")
    for a in result.attempts:
        if a.status == "ok":
            note = " (corrected the previous error)" if a.number > 1 else ""
            st.success(f"Attempt {a.number}: Success{note}")
        else:
            st.error(f"Attempt {a.number}: Failed. Reason: {a.reason}")
        with st.expander(f"SQL for attempt {a.number}"):
            st.code(a.sql, language="sql")
elif run:
    st.warning("Please enter a question.")