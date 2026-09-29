"""SQL safety validator built on sqlglot.

The LLM is NOT a security boundary. This parser is (together with the
read-only database connection in executor.py).
"""
from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError


def _nodes(*names):
    """Collect sqlglot node classes that exist in the installed version."""
    return tuple(getattr(exp, n) for n in names if hasattr(exp, n))


FORBIDDEN = _nodes(
    "Insert", "Update", "Delete", "Drop", "Alter", "AlterTable", "Create", "Command",
    "Pragma", "Attach", "Detach", "TruncateTable", "Merge", "Transaction",
    "Commit", "Rollback", "Set",
)
ALLOWED_ROOTS = (exp.Select, exp.Union) + _nodes("SetOperation", "Subquery")


@dataclass
class ValidationResult:
    ok: bool
    sql: str = ""     # safe SQL with LIMIT enforced (only when ok)
    error: str = ""


def validate_sql(sql: str, max_rows: int = 100, dialect: str = "sqlite") -> ValidationResult:
    if not sql or not sql.strip():
        return ValidationResult(False, error="Empty SQL")
    try:
        statements = [s for s in sqlglot.parse(sql, read=dialect) if s is not None]
    except SqlglotError as e:
        first_line = str(e).splitlines()[0] if str(e) else "parse error"
        return ValidationResult(False, error=f"SQL could not be parsed: {first_line}")

    if len(statements) != 1:
        return ValidationResult(False, error=f"Exactly one statement is allowed (got {len(statements)})")

    stmt = statements[0]
    if not isinstance(stmt, ALLOWED_ROOTS):
        kind = type(stmt).__name__.upper()
        return ValidationResult(False, error=f"Only SELECT queries are allowed (got {kind})")

    bad = stmt.find(*FORBIDDEN) if FORBIDDEN else None
    if bad is not None:
        return ValidationResult(False, error=f"Forbidden operation inside query: {type(bad).__name__.upper()}")

    return ValidationResult(True, sql=_enforce_limit(stmt, max_rows))


def _enforce_limit(stmt: exp.Expression, max_rows: int) -> str:
    """Guarantee the query returns at most max_rows rows."""
    if isinstance(stmt, exp.Select):
        limit = stmt.args.get("limit")
        existing = None
        if limit is not None:
            try:
                existing = int(limit.expression.name)
            except (ValueError, AttributeError):
                existing = None
        if existing is None or existing > max_rows:
            stmt = stmt.limit(max_rows)  # replaces any existing LIMIT
        return stmt.sql(dialect="sqlite")
    # UNION / parenthesised queries: wrap so the limit always applies
    return f"SELECT * FROM ({stmt.sql(dialect='sqlite')}) AS _qp_limited LIMIT {max_rows}"