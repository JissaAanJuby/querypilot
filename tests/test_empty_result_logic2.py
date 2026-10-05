from agent.corrector import empty_result_is_suspicious


def test_string_equality_filter_is_suspicious():
    assert empty_result_is_suspicious("SELECT * FROM t WHERE city = 'Aberdeen'")


def test_no_filter_not_suspicious():
    assert not empty_result_is_suspicious("SELECT * FROM t")


def test_numeric_filter_not_suspicious():
    assert not empty_result_is_suspicious("SELECT * FROM t WHERE gpa > 4.5")


def test_join_with_string_filter_is_suspicious():
    sql = "SELECT * FROM t JOIN u ON u.id=t.id WHERE t.status = 'active'"
    assert empty_result_is_suspicious(sql)