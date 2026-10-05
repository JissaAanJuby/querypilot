"""The agent loop: generate -> validate -> execute -> (fail?) -> correct -> retry."""

import logging
import re
import time
from dataclasses import dataclass, field

import pandas as pd
import sqlglot
from sqlglot import exp

from agent.executor import assess_result, execute_query
from agent.generator import LLMClient, LLMError, correct_sql, generate_sql
from agent.schema import format_schema, select_relevant_tables
from agent.validator import validate_sql

log = logging.getLogger("querypilot")

EMPTY_ERROR = (
    "The query ran successfully but returned zero rows. "
    "Check join conditions and that filter values match the sample rows."
)


@dataclass
class Attempt:
    number: int
    sql: str
    executed_sql: str
    status: str
    error: str = ""
    reason: str = ""
    latency_s: float = 0.0
    plausibility_warning: str = ""


@dataclass
class AgentResult:
    question: str
    success: bool
    empty: bool = False
    truncated: bool = False
    df: pd.DataFrame | None = None
    final_sql: str = ""
    error: str = ""
    attempts: list = field(default_factory=list)
    total_latency_s: float = 0.0

    @property
    def answered(self) -> bool:
        """Executed AND returned rows."""
        return self.success and not self.empty

    @property
    def initial_failure(self) -> bool:
        return not self.attempts or self.attempts[0].status != "ok"


def summarize_error(status: str, error: str) -> str:
    """One-line, non-technical summary for the UI (no chain-of-thought)."""
    if status == "empty":
        return "query returned no rows"

    if status == "validation_failed":
        return f"blocked by safety validator ({error})"

    for pattern, text in [
        (r"no such column: (\S+)", "column `{}` was not found"),
        (r"no such table: (\S+)", "table `{}` was not found"),
        (r"ambiguous column name: (\S+)", "column `{}` is ambiguous"),
        (r"no such function: (\S+)", "function `{}` does not exist"),
    ]:
        m = re.search(pattern, error)
        if m:
            return text.format(m.group(1))

    if "syntax error" in error.lower():
        return "SQL syntax error"

    if "time limit" in error:
        return "query took too long"

    return error[:120]


def empty_result_is_suspicious(sql: str) -> bool:
    """Heuristic for deciding whether an empty result is worth retrying.

    String/date equality filters are the most common source of empty results
    caused by formatting mismatches such as case or whitespace.

    Queries with no restrictive filter, or only numeric/range filters,
    are more likely to have a genuinely empty result.
    """
    try:
        tree = sqlglot.parse_one(sql, read="sqlite")
    except Exception:
        return True

    where = tree.args.get("where")

    if where is None:
        return False

    string_eq_filters = [
        eq
        for eq in where.find_all(exp.EQ)
        if isinstance(eq.expression, exp.Literal)
        and eq.expression.is_string
    ]

    return len(string_eq_filters) > 0


def run_agent(
    question: str,
    client: LLMClient,
    db_path,
    schema: dict,
    max_retries: int = 3,
    max_rows: int = 100,
    self_correct: bool = True,
    prune: bool = False,
    retry_on_empty: bool = True,
) -> AgentResult:
    started = time.perf_counter()

    full_text = format_schema(schema)

    first_text = (
        format_schema(
            schema,
            select_relevant_tables(question, schema),
        )
        if prune
        else full_text
    )

    attempts: list[Attempt] = []
    history: list[dict] = []

    empty_fallback = None

    def finish(**kwargs) -> AgentResult:
        return AgentResult(
            question=question,
            attempts=attempts,
            total_latency_s=time.perf_counter() - started,
            **kwargs,
        )

    try:
        sql = generate_sql(client, question, first_text)
    except LLMError as e:
        return finish(
            success=False,
            error=f"LLM error: {e}",
        )

    for i in range(max_retries + 1):
        t0 = time.perf_counter()

        executed, ex, kind = "", None, ""

        check = validate_sql(sql, max_rows)

        if not check.ok:
            status, error = "validation_failed", check.error

        else:
            executed = check.sql
            ex = execute_query(executed, db_path)

            if not ex.ok:
                status, error = "execution_failed", ex.error

            else:
                kind, _ = assess_result(ex.df, max_rows)

                if kind == "empty":
                    status, error = "empty", EMPTY_ERROR
                    attempt_retry_on_empty = empty_result_is_suspicious(
                        executed
                    )
                else:
                    status, error = "ok", ""

        attempt = Attempt(
            number=i + 1,
            sql=sql,
            executed_sql=executed,
            status=status,
            error=error,
            reason=(
                summarize_error(status, error)
                if status != "ok"
                else ""
            ),
            latency_s=time.perf_counter() - t0,
        )

        attempts.append(attempt)

        log.info(
            "Attempt %d [%s] %s | %s",
            attempt.number,
            status,
            error[:100],
            sql.replace("\n", " ")[:120],
        )

        if status == "ok":
            from agent.executor import check_fanout_plausibility

            warning = check_fanout_plausibility(
                executed,
                ex.df,
            )

            attempt.plausibility_warning = warning or ""

            return finish(
                success=True,
                df=ex.df,
                final_sql=executed,
                truncated=(kind == "truncated"),
            )

        if status == "empty":
            empty_fallback = (executed, ex)

            if not retry_on_empty or not attempt_retry_on_empty:
                break

        if not self_correct or i == max_retries:
            break

        history.append(
            {
                "sql": sql,
                "error": error,
            }
        )

        try:
            sql = correct_sql(
                client,
                question,
                full_text,
                history,
            )
        except LLMError as e:
            return finish(
                success=False,
                final_sql=sql,
                error=f"LLM error during correction: {e}",
            )

    if empty_fallback is not None:
        executed, ex = empty_fallback

        return finish(
            success=True,
            empty=True,
            df=ex.df,
            final_sql=executed,
        )

    last = attempts[-1]

    return finish(
        success=False,
        final_sql=last.sql,
        error=last.reason or last.error,
    )