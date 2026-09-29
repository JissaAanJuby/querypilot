from pathlib import Path

import pytest

from agent.corrector import run_agent
from agent.generator import LLMClient
from agent.schema import extract_schema

DB = Path("data/chinook.db")
pytestmark = pytest.mark.skipif(not DB.exists(), reason="chinook.db not found")


class ScriptedClient(LLMClient):
    def __init__(self, *sqls):
        self.sqls, self.calls = list(sqls), 0

    def complete(self, system, prompt):
        sql = self.sqls[min(self.calls, len(self.sqls) - 1)]
        self.calls += 1
        return sql


@pytest.fixture(scope="module")
def schema():
    return extract_schema(DB)


def test_corrects_bad_column(schema):
    client = ScriptedClient("SELECT artist_name FROM artists", "SELECT Name FROM artists")
    res = run_agent("list artists", client, DB, schema)
    assert res.answered and len(res.attempts) == 2
    assert res.attempts[0].status == "execution_failed"


def test_no_correction_when_disabled(schema):
    client = ScriptedClient("SELECT artist_name FROM artists", "SELECT Name FROM artists")
    res = run_agent("list artists", client, DB, schema, self_correct=False)
    assert not res.success and len(res.attempts) == 1


def test_retry_limit(schema):
    client = ScriptedClient("SELECT nope FROM artists")
    res = run_agent("x", client, DB, schema, max_retries=3)
    assert not res.success and len(res.attempts) == 4


def test_dangerous_sql_blocked(schema):
    client = ScriptedClient("DROP TABLE customers")
    res = run_agent("drop it", client, DB, schema, self_correct=False)
    assert res.attempts[0].status == "validation_failed"


def test_empty_result_retried(schema):
    client = ScriptedClient(
        "SELECT FirstName FROM customers WHERE Country = 'United States'",
        "SELECT FirstName FROM customers WHERE Country = 'USA'",
    )
    res = run_agent("us customers", client, DB, schema)
    assert res.answered and res.attempts[0].status == "empty"