"""Deterministic chart selection — moved as-is from the original app.py.
No LLM involvement in chart choice."""
import pandas as pd
import plotly.express as px


def _is_date_col(series: pd.Series) -> bool:
    name = str(series.name).lower()
    if any(k in name for k in ("date", "year", "month")):
        return True
    if series.dtype == object:
        s = series.dropna().astype(str)
        return len(s) > 0 and bool(s.str.match(r"^\d{4}-\d{2}(-\d{2})?").all())
    return False


def choose_chart(df: pd.DataFrame):
    if df is None or df.empty:
        return None
    if df.shape == (1, 1) and pd.api.types.is_numeric_dtype(df.iloc[:, 0]):
        return {"kind": "metric", "label": str(df.columns[0]), "value": df.iloc[0, 0]}

    date_col = next((c for c in df.columns if _is_date_col(df[c])), None)
    numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and c != date_col]
    if not numeric:
        return None

    if date_col is not None:
        fig = px.line(df.sort_values(date_col), x=date_col, y=numeric, markers=True,
                       template="plotly_dark")
        return {"kind": "figure", "fig": fig}

    data = df.head(30)
    others = [c for c in df.columns if c not in numeric]
    if others:
        fig = px.bar(data, x=others[0], y=numeric, template="plotly_dark")
    elif len(numeric) >= 2:
        fig = px.scatter(data, x=numeric[0], y=numeric[1], template="plotly_dark")
    else:
        return None
    return {"kind": "figure", "fig": fig}


def explain(result) -> str:
    if not result.success:
        return "QueryPilot could not produce a working query within the retry limit."
    rows, cols = result.df.shape
    text = f"Returned {rows} row(s) and {cols} column(s)"
    if len(result.attempts) > 1:
        text += f" after {len(result.attempts)} attempts (self-corrected)"
    text += ". Execution success does not guarantee semantic correctness — review the SQL."
    return text