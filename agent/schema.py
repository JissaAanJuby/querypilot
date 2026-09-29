"""Schema extraction, formatting and simple pruning for a SQLite database."""
import re
import sqlite3
from collections import deque
from pathlib import Path


def _connect_ro(db_path) -> sqlite3.Connection:
    uri = f"{Path(db_path).resolve().as_uri()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def extract_schema(db_path, sample_rows: int = 3) -> dict:
    """Return {table: {"columns": [...], "foreign_keys": [...], "samples": [...]}}."""
    conn = _connect_ro(db_path)
    try:
        names = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        schema = {}
        for table in names:
            columns = [
                {"name": r[1], "type": r[2] or "", "pk": bool(r[5])}
                for r in conn.execute(f'PRAGMA table_info("{table}")')
            ]
            fks = [
                {"from": r[3], "table": r[2], "to": r[4] or "?"}
                for r in conn.execute(f'PRAGMA foreign_key_list("{table}")')
            ]
            samples = [
                list(r)
                for r in conn.execute(f'SELECT * FROM "{table}" LIMIT {int(sample_rows)}')
            ]
            schema[table] = {"columns": columns, "foreign_keys": fks, "samples": samples}
        return schema
    finally:
        conn.close()


def _short(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bytes):
        return "<blob>"
    if isinstance(value, str) and len(value) > 30:
        return repr(value[:27] + "...")
    return repr(value)


def format_schema(schema: dict, tables: list | None = None) -> str:
    """Compact text description of the schema (optionally only some tables)."""
    lines = []
    for table, info in schema.items():
        if tables is not None and table not in tables:
            continue
        cols = ", ".join(
            f"{c['name']} {c['type']}".strip() + (" (PK)" if c["pk"] else "")
            for c in info["columns"]
        )
        lines.append(f"Table: {table}")
        lines.append(f"  Columns: {cols}")
        if info["foreign_keys"]:
            fks = "; ".join(
                f"{table}.{fk['from']} -> {fk['table']}.{fk['to']}"
                for fk in info["foreign_keys"]
            )
            lines.append(f"  Foreign keys: {fks}")
        if info["samples"]:
            lines.append("  Sample rows (values in column order):")
            for row in info["samples"]:
                lines.append("    (" + ", ".join(_short(v) for v in row) + ")")
        lines.append("")
    return "\n".join(lines).strip()


# ---------------------------------------------------------------- pruning --
# Keys are stemmed (trailing "s" removed) question words -> tables they imply.
_SYNONYMS = {
    "revenue": ["invoice_items", "invoices"],
    "sale": ["invoice_items", "invoices"],
    "sold": ["invoice_items"],
    "spent": ["invoices"],
    "spend": ["invoices"],
    "purchase": ["invoices"],
    "bought": ["invoices"],
    "song": ["tracks"],
    "track": ["tracks"],
    "artist": ["artists"],
    "album": ["albums"],
    "genre": ["genres"],
    "customer": ["customers"],
    "employee": ["employees"],
    "playlist": ["playlists"],
}
_GENERIC_COLUMN_WORDS = {"name", "id", "type", "title"}


def _stem(word: str) -> str:
    return word[:-1] if word.endswith("s") and len(word) > 3 else word


def _tokens(text: str) -> set:
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)  # split CamelCase
    return {_stem(w) for w in re.findall(r"[a-z]+", text.lower())}


def _path(graph: dict, start: str, goal: str) -> list:
    """Shortest path in the foreign-key graph (BFS)."""
    prev, queue = {start: None}, deque([start])
    while queue:
        cur = queue.popleft()
        if cur == goal:
            break
        for nxt in graph.get(cur, ()):
            if nxt not in prev:
                prev[nxt] = cur
                queue.append(nxt)
    if goal not in prev:
        return []
    out, node = [], goal
    while node is not None:
        out.append(node)
        node = prev[node]
    return out


def select_relevant_tables(question: str, schema: dict) -> list:
    """Keyword-based pruning: match tables/columns, then add join-path tables.

    Falls back to ALL tables if nothing matches. Deliberately simple.
    """
    q = _tokens(question)
    selected = set()
    for word in q:
        for table in _SYNONYMS.get(word, []):
            if table in schema:
                selected.add(table)
    for table, info in schema.items():
        name_tokens = _tokens(table.replace("_", " "))
        if name_tokens and name_tokens <= q:
            selected.add(table)
        for col in info["columns"]:
            col_tokens = _tokens(col["name"]) - _GENERIC_COLUMN_WORDS
            if col_tokens and col_tokens <= q:
                selected.add(table)

    if not selected:
        return list(schema)

    graph = {t: set() for t in schema}
    for table, info in schema.items():
        for fk in info["foreign_keys"]:
            if fk["table"] in schema:
                graph[table].add(fk["table"])
                graph[fk["table"]].add(table)

    result = set(selected)
    ordered = sorted(selected)
    for i, a in enumerate(ordered):
        for b in ordered[i + 1:]:
            result.update(_path(graph, a, b))
    return [t for t in schema if t in result]