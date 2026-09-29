from pathlib import Path

import pytest

from agent.executor import assess_result, execute_query

DB = Path("data/chinook.db")
pytestmark = pytest.mark.skipif(not DB.exists(), reason="chinook.db not found")


def test_select_works():
    r = execute_query("SELECT COUNT(*) AS n FROM customers", DB)
    assert r.ok and r.df.iloc[0, 0] > 0 and r.row_count == 1


def test_writes_blocked_at_database_level():
    # Bypasses the validator on purpose: the DB itself must refuse.
    r = execute_query("INSERT INTO genres (Name) VALUES ('Hacked')", DB)
    assert not r.ok and "readonly" in r.error.lower()


def test_bad_column_returns_clean_error():
    r = execute_query("SELECT nope FROM customers", DB)
    assert not r.ok and "no such column" in r.error


def test_timeout():
    sql = "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r) SELECT COUNT(*) FROM r"
    r = execute_query(sql, DB, timeout_s=1)
    assert not r.ok and "time limit" in r.error


def test_assess_result():
    import pandas as pd
    assert assess_result(pd.DataFrame(), 100)[0] == "empty"
    assert assess_result(pd.DataFrame({"a": range(100)}), 100)[0] == "truncated"
    assert assess_result(pd.DataFrame({"a": [1]}), 100)[0] == "ok"