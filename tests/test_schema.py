from pathlib import Path

import pytest

from agent.schema import extract_schema, format_schema, select_relevant_tables

DB = Path("data/chinook.db")
pytestmark = pytest.mark.skipif(not DB.exists(), reason="chinook.db not found")


@pytest.fixture(scope="module")
def schema():
    return extract_schema(DB)


def test_tables_found(schema):
    assert {"customers", "tracks", "albums", "artists", "invoices"} <= set(schema)


def test_columns_pk_fk_samples(schema):
    tracks = schema["tracks"]
    assert any(c["name"] == "TrackId" and c["pk"] for c in tracks["columns"])
    assert any(fk["table"] == "albums" for fk in tracks["foreign_keys"])
    assert len(tracks["samples"]) == 3


def test_format_contains_key_info(schema):
    text = format_schema(schema, ["tracks"])
    assert "Table: tracks" in text and "Foreign keys" in text and "Sample rows" in text
    assert "Table: customers" not in text


def test_pruning_includes_join_path(schema):
    tables = select_relevant_tables("Which artist generated the most revenue?", schema)
    assert {"artists", "albums", "tracks", "invoice_items"} <= set(tables)


def test_pruning_falls_back_to_all(schema):
    assert set(select_relevant_tables("zzz qqq", schema)) == set(schema)