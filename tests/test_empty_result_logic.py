from agent.corrector import empty_result_is_suspicious


def test_string_equality_is_suspicious():
    sql = "SELECT * FROM customers WHERE Country = 'USA'"
    assert empty_result_is_suspicious(sql) is True


def test_no_filter_is_not_suspicious():
    sql = "SELECT * FROM customers"
    assert empty_result_is_suspicious(sql) is False


def test_numeric_filter_is_not_suspicious():
    sql = "SELECT * FROM customers WHERE CustomerId = 999999"
    assert empty_result_is_suspicious(sql) is False


def test_join_with_string_filter_is_suspicious():
    sql = """
    SELECT c.CustomerId
    FROM customers c
    JOIN invoices i ON c.CustomerId = i.CustomerId
    WHERE c.Country = 'USA'
    """
    assert empty_result_is_suspicious(sql) is True