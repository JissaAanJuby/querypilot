import pytest

from agent.validator import validate_sql


def test_simple_select_allowed():
    assert validate_sql("SELECT * FROM customers").ok


def test_trailing_semicolon_allowed():
    assert validate_sql("SELECT 1;").ok


def test_with_cte_select_allowed():
    r = validate_sql("WITH t AS (SELECT * FROM tracks) SELECT COUNT(*) FROM t")
    assert r.ok


def test_union_allowed_and_limited():
    r = validate_sql("SELECT Name FROM artists UNION SELECT Name FROM genres")
    assert r.ok and "LIMIT 100" in r.sql.upper()


@pytest.mark.parametrize("sql", [
    "INSERT INTO customers (FirstName) VALUES ('x')",
    "UPDATE customers SET FirstName = 'x'",
    "DELETE FROM customers",
    "DROP TABLE customers",
    "ALTER TABLE customers ADD COLUMN x TEXT",
    "CREATE TABLE t (id INTEGER)",
    "PRAGMA table_info(customers)",
    "ATTACH DATABASE 'other.db' AS other",
])
def test_non_select_rejected(sql):
    assert not validate_sql(sql).ok


def test_multiple_statements_rejected():
    assert not validate_sql("SELECT 1; DROP TABLE customers").ok


def test_empty_and_garbage_rejected():
    assert not validate_sql("").ok
    assert not validate_sql("this is not sql at all").ok


def test_limit_added():
    assert "LIMIT 100" in validate_sql("SELECT * FROM tracks").sql.upper()


def test_large_limit_clamped():
    assert "LIMIT 100" in validate_sql("SELECT * FROM tracks LIMIT 5000").sql.upper()


def test_small_limit_kept():
    assert "LIMIT 5" in validate_sql("SELECT * FROM tracks LIMIT 5").sql.upper()