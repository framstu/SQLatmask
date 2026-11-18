"""Tests for SELECT and DELETE execution."""

import pandas as pd
import pytest

from sqlatmask import cmds
from sqlatmask import iodata
from sqlatmask import queryparser as qp


def run_select(query, capture):
    return cmds.execute_select(query, out=capture)


# ---------------------------------------------------------------------------
# SELECT
# ---------------------------------------------------------------------------


def test_select_all_sets_last_result(people, capture):
    result = run_select("SELECT * FROM people", capture)

    assert len(result) == len(people)
    assert iodata.LAST_RESULT is not None
    assert iodata.LAST_RESULT is not result
    assert iodata.LAST_RESULT is not iodata.DATABASES["people"]
    assert "(6 rows)" in capture.text


def test_select_does_not_modify_the_table(people, capture):
    run_select("SELECT name FROM people WHERE age > 30", capture)
    assert len(iodata.DATABASES["people"]) == 6


def test_select_projects_in_the_given_order(people, capture):
    result = run_select("SELECT age, name FROM people LIMIT 2", capture)
    assert list(result.columns) == ["age", "name"]


def test_select_alias(people, capture):
    result = run_select("SELECT name AS who FROM people LIMIT 1", capture)
    assert list(result.columns) == ["who"]
    assert result["who"].iloc[0] == "Alice"


def test_select_duplicate_alias_is_refused(people, capture):
    with pytest.raises(qp.QueryError, match="both be called 'x'"):
        run_select("SELECT name AS x, city AS x FROM people", capture)


def test_select_unknown_column_is_reported(people, capture):
    with pytest.raises(qp.QueryError, match="unknown column 'nope'"):
        run_select("SELECT nope FROM people", capture)
    assert iodata.LAST_RESULT is None


def test_select_order_by_desc_with_nulls_last(people, capture):
    result = run_select("SELECT name, age FROM people ORDER BY age DESC", capture)
    assert list(result["name"]) == ["Eve", "Bob", "Charlie", "Alice", "Frank", "Dana"]


def test_select_order_by_two_columns(people, capture):
    result = run_select(
        "SELECT name, city, age FROM people ORDER BY city ASC, age DESC", capture
    )
    # Cities ascending; inside a city the older row comes first and a NULL age
    # sorts after the ages of the same city.
    assert list(result["name"]) == ["Alice", "Dana", "Charlie", "Frank", "Eve", "Bob"]


def test_select_order_by_unknown_column_is_refused(people, capture):
    with pytest.raises(qp.QueryError, match="unknown column 'nope'"):
        run_select("SELECT * FROM people ORDER BY nope", capture)


def test_select_limit_and_offset(people, capture):
    result = run_select("SELECT id FROM people ORDER BY id LIMIT 2 OFFSET 1", capture)
    assert list(result["id"]) == [2, 3]


def test_select_limit_zero_is_an_empty_result(people, capture):
    result = run_select("SELECT * FROM people LIMIT 0", capture)
    assert result.empty
    assert list(result.columns) == list(people.columns)
    assert "0 rows" in capture.text


def test_select_distinct(people, capture):
    result = run_select("SELECT DISTINCT city FROM people", capture)
    assert sorted(result["city"]) == sorted(["Gdańsk", "Sopot", "Gdynia", "Kraków"])


def test_select_table_name_is_case_insensitive(people, capture):
    assert len(run_select("SELECT * FROM PEOPLE", capture)) == 6


def test_select_unknown_table(people, capture):
    with pytest.raises(qp.QueryError, match="table 'nope' not found"):
        run_select("SELECT * FROM nope", capture)


def test_select_string_between_used_to_return_everything(people, capture):
    result = run_select("SELECT name FROM people WHERE name BETWEEN 'A' AND 'C'", capture)
    assert list(result["name"]) == ["Alice", "Bob"]


def test_select_empty_result_keeps_columns(people, capture):
    result = run_select("SELECT name, city FROM people WHERE id = 999", capture)
    assert result.empty
    assert list(result.columns) == ["name", "city"]
    assert "0 rows" in capture.text


def test_select_prints_at_most_max_rows(people, capture):
    cmds.execute_select("SELECT * FROM people", out=capture, max_rows=2)
    assert "showing 2 of 6 rows" in capture.text


def test_format_table_zero_rows():
    frame = pd.DataFrame({"city": pd.Series([], dtype="string")})
    assert cmds.format_table(frame) == "(0 rows), columns: city"


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------


def test_delete_removes_only_matching_rows(people, capture):
    removed = cmds.execute_delete("DELETE FROM people WHERE age < 30", out=capture)

    assert removed == 3
    remaining = iodata.DATABASES["people"]
    assert len(remaining) == 3
    assert all(remaining["age"].dropna() >= 30)
    assert "people" in iodata.DIRTY
    assert "Deleted 3 of 6 rows from 'people'" in capture.text


def test_delete_without_where_is_refused(people, capture):
    with pytest.raises(qp.QueryError, match="refusing to delete every row"):
        cmds.execute_delete("DELETE FROM people", out=capture)

    assert len(iodata.DATABASES["people"]) == 6
    assert iodata.DIRTY == set()


def test_delete_all_is_explicit(people, capture):
    removed = cmds.execute_delete("DELETE ALL FROM people", out=capture)

    assert removed == 6
    assert iodata.DATABASES["people"].empty
    assert "people" in iodata.DIRTY


def test_delete_with_a_broken_condition_leaves_the_table_intact(people, capture):
    # The old code deleted every row as soon as the WHERE clause failed.
    with pytest.raises(qp.QueryError, match="unknown column 'nope'"):
        cmds.execute_delete("DELETE FROM people WHERE nope > 1", out=capture)

    assert len(iodata.DATABASES["people"]) == 6
    assert iodata.DIRTY == set()


def test_delete_with_a_type_mismatch_leaves_the_table_intact(people, capture):
    with pytest.raises(qp.QueryError, match="remove the quotes"):
        cmds.execute_delete("DELETE FROM people WHERE age = 'thirty'", out=capture)

    assert len(iodata.DATABASES["people"]) == 6


def test_delete_with_text_between_is_no_longer_a_wipe(people, capture):
    removed = cmds.execute_delete(
        "DELETE FROM people WHERE name BETWEEN 'A' AND 'C'", out=capture
    )

    assert removed == 2
    assert len(iodata.DATABASES["people"]) == 4


def test_delete_from_unknown_table(people, capture):
    with pytest.raises(qp.QueryError, match="table 'nope' not found"):
        cmds.execute_delete("DELETE FROM nope WHERE id = 1", out=capture)


def test_delete_all_from_unknown_table(people, capture):
    with pytest.raises(qp.QueryError, match="table 'nope' not found"):
        cmds.execute_delete("DELETE ALL FROM nope", out=capture)


def test_delete_nothing_reports_zero(people, capture):
    removed = cmds.execute_delete("DELETE FROM people WHERE id = 999", out=capture)
    assert removed == 0
    assert "people" not in iodata.DIRTY
