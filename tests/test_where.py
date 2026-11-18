"""Tests for WHERE evaluation against real DataFrames."""

import pandas as pd
import pytest

from sqlatmask import queryparser as qp
from sqlatmask import where


def select(query):
    statement = qp.parse_statement(query)
    assert isinstance(statement, qp.SelectStatement)
    return statement


def names(query, frame):
    mask = where.evaluate(select(query).where, frame)
    return list(frame[mask]["name"])


def test_numeric_comparison(people):
    assert names("SELECT * FROM people WHERE age > 30", people) == ["Bob", "Eve"]
    assert names("SELECT * FROM people WHERE age >= 32", people) == ["Bob", "Eve"]
    assert names("SELECT * FROM people WHERE age = 29", people) == ["Charlie"]


def test_rows_with_null_never_match_a_comparison(people):
    matched = names("SELECT * FROM people WHERE age < 100", people)
    assert "Dana" not in matched  # age is NULL for Dana


def test_text_comparison(people):
    assert names("SELECT * FROM people WHERE city = 'Sopot'", people) == ["Bob", "Eve"]
    assert names("SELECT * FROM people WHERE city != 'Sopot'", people) == [
        "Alice",
        "Charlie",
        "Dana",
        "Frank",
    ]


def test_column_names_are_case_insensitive(people):
    assert names("SELECT * FROM people WHERE CITY = 'Sopot'", people) == ["Bob", "Eve"]


def test_between_accepts_decimals_and_negatives(people):
    assert names("SELECT * FROM people WHERE score BETWEEN 2.5 AND 4.5", people) == [
        "Alice",
        "Bob",
        "Charlie",
    ]
    assert names("SELECT * FROM people WHERE score BETWEEN -1 AND 2", people) == ["Frank"]


def test_between_on_text_is_compared_as_text(people):
    # This used to fail inside DataFrame.query() and, on DELETE, remove every row.
    # Lexicographic: "Charlie" sorts above "C" (it only starts with it).
    assert names("SELECT * FROM people WHERE name BETWEEN 'A' AND 'C'", people) == [
        "Alice",
        "Bob",
    ]
    assert names("SELECT * FROM people WHERE name BETWEEN 'A' AND 'Cz'", people) == [
        "Alice",
        "Bob",
        "Charlie",
    ]


def test_between_on_dates(orders):
    statement = select(
        "SELECT * FROM orders WHERE day BETWEEN '2025-01-01' AND '2025-02-01'"
    )
    mask = where.evaluate(statement.where, orders)
    assert list(orders[mask]["id"]) == [2]


def test_in_list(people):
    assert names("SELECT * FROM people WHERE city IN ('Sopot', 'Kraków')", people) == [
        "Bob",
        "Eve",
        "Frank",
    ]
    assert names("SELECT * FROM people WHERE id IN (1, 3)", people) == ["Alice", "Charlie"]


def test_in_list_with_null_only_matches_nothing(people):
    assert names("SELECT * FROM people WHERE note IN (NULL)", people) == []


def test_like_wildcards(people):
    assert names("SELECT * FROM people WHERE city LIKE 'Gd%'", people) == [
        "Alice",
        "Charlie",
        "Dana",
    ]
    assert names("SELECT * FROM people WHERE city LIKE '_dynia'", people) == ["Charlie"]


def test_like_is_case_insensitive_by_default(people):
    assert names("SELECT * FROM people WHERE name LIKE 'a%'", people) == ["Alice"]


def test_like_can_be_made_case_sensitive(people, monkeypatch):
    monkeypatch.setattr(where, "LIKE_CASE_SENSITIVE", True)
    assert names("SELECT * FROM people WHERE name LIKE 'a%'", people) == []


def test_not_like(people):
    assert names("SELECT * FROM people WHERE name NOT LIKE 'A%'", people) == [
        "Bob",
        "Charlie",
        "Dana",
        "Eve",
        "Frank",
    ]


def test_is_null_and_is_not_null(people):
    assert names("SELECT * FROM people WHERE note IS NULL", people) == ["Bob", "Eve"]
    assert names("SELECT * FROM people WHERE note IS NOT NULL", people) == [
        "Alice",
        "Charlie",
        "Dana",
        "Frank",
    ]


def test_null_comparison_is_explained(people):
    statement = select("SELECT * FROM people WHERE note = NULL")
    with pytest.raises(qp.QueryError, match="use IS NULL"):
        where.evaluate(statement.where, people)


def test_and_binds_tighter_than_or(people):
    # id = 1 OR (id = 2 AND age > 30)
    assert names("SELECT * FROM people WHERE id = 1 OR id = 2 AND age > 30", people) == [
        "Alice",
        "Bob",
    ]


def test_parentheses_override_precedence(people):
    assert names(
        "SELECT * FROM people WHERE (id = 1 OR id = 2) AND age > 30", people
    ) == ["Bob"]


def test_not_group(people):
    assert names(
        "SELECT * FROM people WHERE NOT (city = 'Sopot' OR age < 20)", people
    ) == ["Alice", "Charlie", "Dana"]


def test_column_to_column_comparison(people):
    assert names("SELECT * FROM people WHERE age > id", people) == [
        "Alice",
        "Bob",
        "Charlie",
        "Eve",
        "Frank",
    ]


def test_numeric_column_rejects_a_quoted_value(people):
    statement = select("SELECT * FROM people WHERE age = '32'")
    with pytest.raises(qp.QueryError, match="remove the quotes"):
        where.evaluate(statement.where, people)


def test_text_column_rejects_a_number(people):
    statement = select("SELECT * FROM people WHERE city > 5")
    with pytest.raises(qp.QueryError, match="cannot be compared with the number"):
        where.evaluate(statement.where, people)


def test_numeric_text_column_is_compared_as_numbers(codes):
    statement = select("SELECT * FROM codes WHERE code > 15")
    mask = where.evaluate(statement.where, codes)
    assert list(codes[mask]["id"]) == [2]


def test_numeric_text_column_still_matches_text(codes):
    statement = select("SELECT * FROM codes WHERE code = 'x'")
    mask = where.evaluate(statement.where, codes)
    assert list(codes[mask]["id"]) == [3]


def test_mixed_column_and_text_column_comparison_is_refused(people):
    statement = select("SELECT * FROM people WHERE age > name")
    with pytest.raises(qp.QueryError, match="one holds numbers and the other text"):
        where.evaluate(statement.where, people)


def test_in_list_type_mismatch_is_refused(people):
    statement = select("SELECT * FROM people WHERE age IN (1, 'x')")
    with pytest.raises(qp.QueryError, match="every value of the IN list must be a number"):
        where.evaluate(statement.where, people)


def test_unknown_column_lists_the_available_ones(people):
    statement = select("SELECT * FROM people WHERE nme = 'Alice'")
    with pytest.raises(qp.QueryError) as error:
        where.evaluate(statement.where, people)
    message = str(error.value)
    assert "unknown column 'nme'" in message
    assert "name" in message


def test_match_column_is_case_insensitive_and_reports_unknown_names(people):
    assert where.match_column(people, "NAME") == "name"
    with pytest.raises(qp.QueryError, match="unknown column"):
        where.match_column(people, "salary")


def test_ambiguous_case_insensitive_column_is_refused():
    frame = pd.DataFrame([{"Name": "a", "name": "b"}])
    with pytest.raises(qp.QueryError, match="ambiguous"):
        where.match_column(frame, "NAME")


def test_constant_conditions_are_allowed(people):
    statement = select("SELECT * FROM people WHERE 1 = 1")
    assert where.evaluate(statement.where, people).all()

    statement = select("SELECT * FROM people WHERE 1 = 2")
    assert not where.evaluate(statement.where, people).any()


def test_like_on_a_numeric_column_is_refused(people):
    statement = select("SELECT * FROM people WHERE age LIKE '2%'")
    with pytest.raises(qp.QueryError, match="does not hold text"):
        where.evaluate(statement.where, people)
