"""QueryPilot — Self-Correcting Text-to-SQL Analyst."""

import glob

import json

import os

from pathlib import Path

import pandas as pd

import streamlit as st

from dotenv import load_dotenv

from agent.corrector import run_agent

from agent.generator import get_client, LLMError

from agent.schema import extract_schema

from ui import theme

from ui.attempt_panel import render as render_attempts

from ui.charts import choose_chart, explain

from ui.pipeline_view import render as render_pipeline

load_dotenv()

CHINOOK_PATH = "data/chinook.db"

SPIDER_DB_DIR = Path("data/spider/database")

st.set_page_config(
    page_title="QueryPilot",
    page_icon="🧭",
    layout="wide"
)

theme.inject()


@st.cache_data
def load_schema(path: str) -> dict:
    return extract_schema(path)


@st.cache_resource
def _client(provider: str, model: str):
    return get_client(provider=provider)


@st.cache_data
def list_spider_dbs() -> list:
    if not SPIDER_DB_DIR.exists():
        return []
    return sorted(
        p.name
        for p in SPIDER_DB_DIR.iterdir()
        if p.is_dir()
        and (p / f"{p.name}.sqlite").exists()
    )


def latest_json(pattern: str):
    files = sorted(glob.glob(pattern))
    if not files:
        return None
    return json.loads(
        Path(files[-1]).read_text(encoding="utf-8")
    )


# ------------------------------------------------------------------ header
st.markdown(
    '<p class="qp-title">🧭 QueryPilot</p>',
    unsafe_allow_html=True
)

st.markdown(
    '<p class="qp-subtitle">Self-correcting text-to-SQL analyst</p>',
    unsafe_allow_html=True
)

tab_analyst, tab_eval, tab_audit, tab_schema = st.tabs(
    ["Analyst", "Evaluation Dashboard", "Audit View", "Schema Explorer"]
)

# ================================================================== ANALYST
with tab_analyst:

    with st.sidebar:

        st.header("Settings")

        mode = st.radio(
            "Database",
            ["Demo (Chinook)", "Benchmark (Spider)"]
        )

        if mode == "Demo (Chinook)":
            db_path = CHINOOK_PATH

        else:
            dbs = list_spider_dbs()

            # Deployment guard: Spider databases are intentionally
            # not bundled with the deployed app.
            if not dbs:
                st.warning(
                    "Spider databases aren't bundled in this deployment. "
                    "Clone the repository locally to explore the Spider benchmark."
                )
                st.stop()

            db_id = st.selectbox("Spider database", dbs)

            db_path = str(
                SPIDER_DB_DIR / db_id / f"{db_id}.sqlite"
            )

        provider = st.selectbox(
            "LLM Provider",
            ["gemini", "openai"],
            index=["gemini", "openai"].index(
                os.getenv("LLM_PROVIDER", "gemini").lower()
                if os.getenv("LLM_PROVIDER", "gemini").lower()
                in ["gemini", "openai"]
                else "gemini"
            )
        )

        if provider == "gemini":
            model = os.getenv(
                "GEMINI_MODEL",
                "gemini-2.5-flash"
            )
        else:
            model = os.getenv(
                "OPENAI_MODEL",
                "gpt-4o-mini"
            )

        st.caption(f"Provider: `{provider}`")

        st.caption(f"Model: `{model}`")

        max_retries = st.slider(
            "Max retries",
            0,
            5,
            3
        )

        max_rows = st.number_input(
            "Max rows",
            10,
            1000,
            100,
            10
        )

        self_correct = st.checkbox(
            "Self-correction",
            value=True
        )

        prune = st.checkbox(
            "Schema pruning",
            value=False
        )

    col_q, col_run = st.columns([5, 1])

    with col_q:
        question = st.text_input(
            "Ask a question",
            placeholder="Which artist has the most tracks?",
            label_visibility="collapsed"
        )

    with col_run:
        run = st.button(
            "Run",
            type="primary",
            use_container_width=True
        )

    left, right = st.columns([2, 1])

    if run and question.strip():

        try:
            client = _client(provider, model)

        except LLMError as e:
            st.error(str(e))
            st.stop()

        schema = load_schema(db_path)

        with st.spinner("Running pipeline..."):

            result = run_agent(
                question.strip(),
                client,
                db_path,
                schema,
                max_retries=max_retries,
                max_rows=int(max_rows),
                self_correct=self_correct,
                prune=prune,
            )

        st.session_state["last_result"] = result

        st.session_state["last_prune"] = prune

    result = st.session_state.get("last_result")

    with right:

        theme.card_open()

        st.markdown("**Pipeline**")

        render_pipeline(
            result,
            st.session_state.get("last_prune", False)
        )

        theme.card_close()

    with left:

        if result is None:

            st.info("Ask a question to get started.")

        else:

            shown_sql = (
                result.final_sql
                or (
                    result.attempts[-1].sql
                    if result.attempts
                    else ""
                )
            )

            st.markdown("**Generated SQL**")

            st.code(
                shown_sql or "-- no SQL produced",
                language="sql"
            )

            c1, c2, c3, c4 = st.columns(4)

            status = (
                "Success"
                if result.answered
                else (
                    "Empty"
                    if result.success
                    else "Failed"
                )
            )

            c1.metric("Status", status)

            c2.metric(
                "Attempts",
                len(result.attempts)
            )

            c3.metric(
                "Latency",
                f"{result.total_latency_s:.2f}s"
            )

            c4.metric(
                "Rows",
                0 if result.df is None else len(result.df)
            )

            if result.error:
                st.error(result.error)

            if result.empty:
                st.warning("Query ran but returned no rows.")

            if result.truncated:
                st.warning(
                    f"Capped at {int(max_rows)} rows."
                )

            if result.df is not None and not result.df.empty:

                st.markdown("**Results**")

                st.dataframe(
                    result.df,
                    use_container_width=True
                )

                chart = choose_chart(result.df)

                if chart:

                    st.markdown("**Visualization**")

                    if chart["kind"] == "metric":

                        st.metric(
                            chart["label"],
                            chart["value"]
                        )

                    else:

                        st.plotly_chart(
                            chart["fig"],
                            use_container_width=True
                        )

                st.markdown("**Summary**")

                st.write(explain(result))

            render_attempts(result)


# =========================================================== EVALUATION TAB
with tab_eval:

    st.markdown("### Evaluation Dashboard")

    chinook = latest_json(
        "evaluation/results/results_*.json"
    )

    spider = latest_json(
        "evaluation/results/spider_results_*.json"
    )

    if chinook is None and spider is None:

        st.info(
            "No evaluation results found yet. Run "
            "`python -m evaluation.run_eval` "
            "and/or `python -m evaluation.run_eval --spider` first."
        )

    else:

        if chinook:

            st.markdown("#### Chinook (single schema)")

            rows = []

            for name, s in chinook["summaries"].items():

                rows.append(
                    {
                        "Config": name,
                        "Accuracy %": round(
                            s["accuracy"],
                            1
                        ),
                        "Avg Latency (s)": round(
                            s["avg_latency"],
                            2
                        ),
                        "Failed": s["failed_queries"],
                    }
                )

            st.dataframe(
                pd.DataFrame(rows),
                use_container_width=True,
                hide_index=True
            )

        if spider:

            st.markdown("#### Spider (10 unseen schemas)")

            rows = []

            for name, s in spider["summaries"].items():

                rows.append(
                    {
                        "Config": name,
                        "Accuracy %": round(
                            s["accuracy"],
                            1
                        ),
                        "Avg Latency (s)": round(
                            s["avg_latency"],
                            2
                        ),
                        "Failed": s["failed_queries"],
                    }
                )

            df = pd.DataFrame(rows)

            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True
            )

            import plotly.express as px

            fig = px.bar(
                df,
                x="Config",
                y="Accuracy %",
                template="plotly_dark",
                text="Accuracy %"
            )

            st.plotly_chart(
                fig,
                use_container_width=True
            )

            st.info(
                "Self-correction's raw score here is lower than baseline's — this was "
                "audited by hand. See the **Audit View** tab: most 'failures' were "
                "benchmark gold-SQL defects the agent correctly worked around, with "
                "exactly one confirmed model error."
            )


# =============================================================== AUDIT TAB
with tab_audit:

    st.markdown("### Audit View")

    audit_files = sorted(
        glob.glob(
            "evaluation/results/spider_audit_*.json"
        )
    )

    if not audit_files:

        st.info(
            "No audit report found. Run "
            "`python -m evaluation.audit_spider` first."
        )

    else:

        audit = json.loads(
            Path(audit_files[-1]).read_text(
                encoding="utf-8"
            )
        )

        counts = {}

        for r in audit:

            k = r["audit"]["classification"]

            counts[k] = counts.get(k, 0) + 1

        cols = st.columns(len(counts) or 1)

        for col, (k, v) in zip(
            cols,
            counts.items()
        ):

            col.metric(
                k.replace("_", " ").title(),
                v
            )

        for r in audit:

            cls = r["audit"]["classification"]

            kind = {
                "model_error": "error",
                "benchmark_defect": "warn",
                "ambiguous": "pending",
                "legitimate_empty": "ok",
                "needs_manual_review": "pending",
            }.get(
                cls,
                "pending"
            )

            with st.expander(
                f"Q{r['id']} ({r['db_id']}) — "
                f"{cls.replace('_', ' ')}"
            ):

                st.markdown(
                    theme.pill(
                        cls.replace("_", " "),
                        kind
                    ),
                    unsafe_allow_html=True
                )

                st.write(r["question"])

                st.caption("Gold SQL")

                st.code(
                    r["gold_sql"],
                    language="sql"
                )

                st.caption(
                    "Final SQL (self-correction)"
                )

                st.code(
                    r["final_sql"],
                    language="sql"
                )

                st.caption(
                    r["audit"]["reason"]
                )


# ============================================================== SCHEMA TAB
with tab_schema:

    st.markdown("### Schema Explorer")

    src = st.radio(
        "Source",
        ["Chinook"]
        + (["Spider"] if list_spider_dbs() else []),
        horizontal=True
    )

    if src == "Chinook":

        schema = load_schema(CHINOOK_PATH)

    else:

        db_id = st.selectbox(
            "Database",
            list_spider_dbs(),
            key="schema_tab_db"
        )

        schema = load_schema(
            str(
                SPIDER_DB_DIR
                / db_id
                / f"{db_id}.sqlite"
            )
        )

    for table, info in schema.items():

        with st.expander(table):

            cols = pd.DataFrame(
                info["columns"]
            )

            st.dataframe(
                cols,
                use_container_width=True,
                hide_index=True
            )

            if info["foreign_keys"]:

                st.caption("Foreign keys")

                for fk in info["foreign_keys"]:

                    st.code(
                        f"{table}.{fk['from']} → "
                        f"{fk['table']}.{fk['to']}",
                        language=None
                    )