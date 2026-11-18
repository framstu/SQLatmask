"""Tests for the statement parser (no pandas involved)."""

import pytest

from sqlatmask import queryparser as qp


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------


def kinds(text):
    return [(token.kind, token.value) for token in qp.tokenize(text) if token.kind != qp.EOF]


def test_tokenizer_splits_names_numbers_and_operators():
    assert kinds("SELECT name, age>=30") == [
        ("NAME", "SELECT"),
        ("NAME", "name"),
        ("COMMA", ","),
        ("NAME", "age"),
        ("OP", ">="),
        ("NUMBER", "30"),
    ]


def test_tokenizer_keeps_keywords_inside_quotes():
    tokens = qp.tokenize("WHERE city = 'Sale LIMIT 3'")
    assert [token.value for token in tokens].count("LIMIT") == 0
    assert tokens[-2].kind == qp.STRING
    assert tokens[-2].value == "Sale LIMIT 3"


def test_tokenizer_supports_doubled_quote_escape():
    tokens = qp.tokenize("WHERE name = 'O''Brien'")
    assert tokens[-2].kind == qp.STRING
    assert tokens[-2].value == "O'Brien"


def test_tokenizer_reports_unterminated_string():
    with pytest.raises(qp.QueryError, match="unterminated string literal"):
        qp.tokenize("SELECT * FROM t WHERE name = 'Alice")


def test_tokenizer_reports_unknown_character():
    with pytest.raises(qp.QueryError, match="unexpected character"):
        qp.tokenize("SELECT * FROM t WHERE name @ 'x'")


def test_tokenizer_reads_decimals_and_exponents():
    values = [token.value for token in qp.tokenize("4.5 .5 1e3 2.5e-2")]
    assert values[:4] == ["4.5", ".5", "1e3", "2.5e-2"]


# ---------------------------------------------------------------------------
# Statement splitting
# ---------------------------------------------------------------------------


def test_split_statements_ignores_semicolons_in_strings():
    script = "SELECT * FROM t WHERE city = 'a;b'; DELETE FROM t WHERE id = 1;"
    assert qp.split_statements(script) == [
        "SELECT * FROM t WHERE city = 'a;b'",
        "DELETE FROM t WHERE id = 1",
    ]


def test_split_statements_keeps_a_trailing_statement_without_semicolon():
    assert qp.split_statements("SELECT 1 FROM t\n\nSHOW TABLES") == [
        "SELECT 1 FROM t\n\nSHOW TABLES"
    ]


# ---------------------------------------------------------------------------
# SELECT
# ---------------------------------------------------------------------------


def test_select_all_is_case_insensitive():
    statement = qp.parse_statement("select * from customers;")
    assert isinstance(statement, qp.SelectStatement)
    assert statement.table == "customers"
    assert statement.select_all


def test_select_columns_and_alias():
    statement = qp.parse_statement("SELECT name AS who, age FROM people")
    assert [(item.name, item.alias) for item in statement.items] == [
        ("name", "who"),
        ("age", None),
    ]


def test_select_parses_where_order_and_limit():
    statement = qp.parse_statement(
        "SELECT * FROM people WHERE age BETWEEN 20 AND 30 "
        "ORDER BY age DESC, name ASC LIMIT 5 OFFSET 2"
    )
    assert isinstance(statement.where, qp.Between)
    assert [(key.column, key.descending) for key in statement.order_by] == [
        ("age", True),
        ("name", False),
    ]
    assert statement.limit == 5
    assert statement.offset == 2


def test_select_without_limit_has_no_limit():
    statement = qp.parse_statement("SELECT * FROM people LIMIT 4")
    assert statement.limit == 4
    assert statement.offset == 0


def test_offset_without_limit():
    statement = qp.parse_statement("SELECT * FROM people OFFSET 3")
    assert statement.limit is None
    assert statement.offset == 3


def test_distinct_flag():
    assert qp.parse_statement("SELECT DISTINCT city FROM people").distinct


@pytest.mark.parametrize(
    "query, message",
    [
        ("SELECT * people", "expected FROM"),
        ("SELECT name FROM", "expected a table name"),
        ("SELECT * FROM people LIMIT -1", "LIMIT needs a whole number"),
        ("SELECT * FROM people LIMIT 2.5", "LIMIT needs a whole number"),
        ("SELECT * FROM people WHERE", "expected a column name or a value"),
        ("SELECT *, name FROM people", "has to be the only entry"),
        ("SELECT * FROM people FROBNICATE", "unexpected"),
        ("SELECT * FROM people ORDER BY", "expected a column name"),
        ("SELECT * FROM people WHERE age = ", "expected a column name or a value"),
        ("SELECT * FROM people WHERE age IN ()", "at least one value"),
    ],
)
def test_select_errors_are_explained(query, message):
    with pytest.raises(qp.QueryError, match=message):
        qp.parse_statement(query)


def test_unknown_command_is_reported():
    with pytest.raises(qp.QueryError, match="unknown command 'FROBNICATE'"):
        qp.parse_statement("FROBNICATE everything")


# ---------------------------------------------------------------------------
# Conditions
# ---------------------------------------------------------------------------


def test_condition_precedence_and_parentheses():
    statement = qp.parse_statement(
        "SELECT * FROM people WHERE city = 'Sopot' OR age > 30 AND id = 2"
    )
    assert isinstance(statement.where, qp.Logical)
    assert statement.where.op == "or"
    assert statement.where.right.op == "and"


def test_between_does_not_swallow_the_following_and():
    statement = qp.parse_statement(
        "SELECT * FROM people WHERE age BETWEEN 20 AND 30 AND city = 'Sopot'"
    )
    assert isinstance(statement.where, qp.Logical)
    assert isinstance(statement.where.left, qp.Between)
    assert isinstance(statement.where.right, qp.Compare)


def test_not_between_in_like():
    statement = qp.parse_statement(
        "SELECT * FROM people WHERE age NOT BETWEEN 20 AND 30"
    )
    assert isinstance(statement.where, qp.Not)

    statement = qp.parse_statement(
        "SELECT * FROM people WHERE city NOT IN ('Sopot')"
    )
    assert isinstance(statement.where, qp.Not)

    statement = qp.parse_statement("SELECT * FROM people WHERE city NOT LIKE 'Gd%'")
    assert isinstance(statement.where, qp.Not)


def test_is_null_both_spellings():
    statement = qp.parse_statement("SELECT * FROM people WHERE note IS NULL")
    assert statement.where == qp.IsNull(qp.Column("note"), negated=False)

    statement = qp.parse_statement("SELECT * FROM people WHERE note IS NOT NULL")
    assert statement.where == qp.IsNull(qp.Column("note"), negated=True)


def test_negative_and_decimal_literals():
    statement = qp.parse_statement(
        "SELECT * FROM people WHERE score BETWEEN -1.5 AND 4.25"
    )
    assert statement.where.low == qp.Literal(-1.5)
    assert statement.where.high == qp.Literal(4.25)


def test_keywords_used_as_column_names_are_rejected_with_a_hint():
    with pytest.raises(qp.QueryError, match="unexpected keyword 'LIMIT'"):
        qp.parse_statement("SELECT * FROM people WHERE LIMIT = 3")


# ---------------------------------------------------------------------------
# DELETE / EXPORT / simple commands
# ---------------------------------------------------------------------------


def test_delete_with_where():
    statement = qp.parse_statement("delete from people where age < 30")
    assert isinstance(statement, qp.DeleteStatement)
    assert statement.all_rows is False
    assert isinstance(statement.where, qp.Compare)


def test_delete_all_is_marked_explicitly():
    statement = qp.parse_statement("DELETE ALL FROM people")
    assert statement.all_rows is True
    assert statement.where is None


def test_delete_all_rejects_a_where_clause():
    with pytest.raises(qp.QueryError, match="cannot take a WHERE clause"):
        qp.parse_statement("DELETE ALL FROM people WHERE age > 1")


def test_export_statement():
    statement = qp.parse_statement("EXPORT LAST TO 'out.json'")
    assert statement == qp.ExportStatement("out.json", overwrite=False)

    statement = qp.parse_statement("export last to \"out.json\" overwrite")
    assert statement == qp.ExportStatement("out.json", overwrite=True)


def test_describe_needs_a_table_name():
    with pytest.raises(qp.QueryError, match="DESCRIBE needs a table name"):
        qp.parse_statement("DESCRIBE")


def test_simple_commands():
    assert isinstance(qp.parse_statement("SHOW TABLES"), qp.ShowTablesStatement)
    assert isinstance(qp.parse_statement("help"), qp.HelpStatement)
    assert isinstance(qp.parse_statement("EXIT;"), qp.ExitStatement)
    assert isinstance(qp.parse_statement("quit"), qp.ExitStatement)


def test_empty_statement_is_rejected():
    with pytest.raises(qp.QueryError, match="empty statement"):
        qp.parse_statement("   ")
