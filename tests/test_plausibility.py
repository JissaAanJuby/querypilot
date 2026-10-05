import pandas as pd

from agent.executor import check_fanout_plausibility


def test_flags_count_without_distinct_over_two_joins():
    sql = """SELECT a.id, COUNT(c.x) FROM a
             JOIN b ON b.a_id = a.id
             JOIN c ON c.b_id = b.id
             GROUP BY a.id"""
    warning = check_fanout_plausibility(sql, pd.DataFrame({"id": [1]}))
    assert warning is not None and "fan-out" in warning


def test_no_warning_with_distinct():
    sql = """SELECT a.id, COUNT(DISTINCT c.x) FROM a
             JOIN b ON b.a_id = a.id
             JOIN c ON c.b_id = b.id
             GROUP BY a.id"""
    assert check_fanout_plausibility(sql, pd.DataFrame({"id": [1]})) is None


def test_no_warning_single_join():
    sql = "SELECT a.id, COUNT(b.x) FROM a JOIN b ON b.a_id = a.id GROUP BY a.id"
    assert check_fanout_plausibility(sql, pd.DataFrame({"id": [1]})) is None


def test_no_warning_no_aggregate():
    sql = "SELECT a.id, b.x FROM a JOIN b ON b.a_id=a.id JOIN c ON c.b_id=b.id"
    assert check_fanout_plausibility(sql, pd.DataFrame({"id": [1]})) is None


def test_no_warning_empty_df():
    sql = "SELECT COUNT(x) FROM a JOIN b ON b.a_id=a.id JOIN c ON c.b_id=b.id GROUP BY a.id"
    assert check_fanout_plausibility(sql, pd.DataFrame()) is None