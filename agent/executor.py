"""Read-only SQLite execution with a timeout and simple result assessment."""

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import sqlglot
from sqlglot import exp


@dataclass
class ExecutionResult:
    ok: bool
    df: pd.DataFrame | None = None
    error: str = ""
    row_count: int = 0
    latency_s: float = 0.0
    


def open_readonly(db_path) -> sqlite3.Connection:
    """mode=ro is enforced by SQLite itself; query_only is a second lock."""
    uri = f"{Path(db_path).resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only = ON")
    return conn


def execute_query(
    sql: str,
    db_path,
    timeout_s: float = 5.0,
) -> ExecutionResult:
    start = time.perf_counter()
    conn = None

    try:
        conn = open_readonly(db_path)
        deadline = time.monotonic() + timeout_s

        # Called every 10,000 SQLite VM steps; returning non-zero aborts the query.
        conn.set_progress_handler(
            lambda: 1 if time.monotonic() > deadline else 0,
            10000,
        )

        cur = conn.execute(sql)
        columns = [d[0] for d in cur.description] if cur.description else []
        df = pd.DataFrame(cur.fetchall(), columns=columns)

        return ExecutionResult(
            True,
            df,
            "",
            len(df),
            time.perf_counter() - start,
        )

    except sqlite3.Error as e:
        msg = str(e)

        if "interrupted" in msg.lower():
            msg = f"Query exceeded the {timeout_s:.0f}s time limit"

        return ExecutionResult(
            False,
            None,
            msg,
            0,
            time.perf_counter() - start,
        )

    finally:
        if conn is not None:
            conn.close()


def assess_result(
    df: pd.DataFrame | None,
    max_rows: int,
) -> tuple[str, str]:
    """Simple result validation: returns (kind, message).

    kind is "empty", "truncated" or "ok". NOTE:
    "ok" only means the query ran and returned rows. It does NOT
    prove the answer is semantically correct.
    """
    if df is None or df.empty:
        return "empty", "The query ran successfully but returned zero rows."

    if len(df) >= max_rows:
        return (
            "truncated",
            f"Result hit the {max_rows}-row limit and may be incomplete.",
        )

    return "ok", ""


def check_fanout_plausibility(
    sql: str,
    df: "pd.DataFrame | None",
) -> str | None:
    """Lightweight heuristic for possible aggregate inflation from JOIN fan-out.

    Returns a warning string when an aggregate is used over multiple JOINs
    without DISTINCT. This is only a warning; it never blocks execution.
    """
    if df is None or df.empty:
        return None

    try:
        tree = sqlglot.parse_one(sql, read="sqlite")
    except Exception:
        return None

    if not isinstance(tree, exp.Select):
        return None

    join_count = len(list(tree.find_all(exp.Join)))

    if join_count < 2:
        return None

    agg_funcs = [
        f for f in tree.find_all((exp.Count, exp.Sum, exp.Avg))
    ]

    if not agg_funcs:
        return None

    def aggregate_has_distinct(f):
        return (
            f.find(exp.Distinct) is not None
            or (
                isinstance(f, exp.Count)
                and f.args.get("this")
                and isinstance(f.args["this"], exp.Distinct)
            )
        )

    all_aggregates_distinct = all(
        aggregate_has_distinct(f) for f in agg_funcs
    )

    if all_aggregates_distinct:
        return None

    has_group_by = tree.args.get("group") is not None

    if has_group_by:
        return (
            "Possible join fan-out detected: an aggregate "
            "(COUNT/SUM/AVG) is computed over "
            f"{join_count} joined tables without DISTINCT. "
            "If any join is one-to-many, this may double-count "
            "rows and inflate the aggregate."
        )

    return None