"""Statement parser for SQLatmask.

The command line used to be split with ``str.index`` and ``str.replace`` calls,
which meant a keyword inside a quoted value ("city = 'Sale LIMIT 3'") cut the
statement in half and every mistake was silent. This module tokenises the input
once, understands quoted strings, and builds a small syntax tree.

Only the standard library is used here so the parser can be tested (and reused)
without pandas installed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

__all__ = [
    "QueryError",
    "Token",
    "tokenize",
    "split_statements",
    "parse_statement",
    "SelectStatement",
    "DeleteStatement",
    "ExportStatement",
    "DescribeStatement",
    "ShowTablesStatement",
    "HelpStatement",
    "ExitStatement",
    "Statement",
    "SelectItem",
    "OrderKey",
    "Column",
    "Literal",
    "Compare",
    "Between",
    "InList",
    "Like",
    "IsNull",
    "Logical",
    "Not",
]

# Token kinds
NAME = "NAME"
NUMBER = "NUMBER"
STRING = "STRING"
OP = "OP"
LPAREN = "LPAREN"
RPAREN = "RPAREN"
COMMA = "COMMA"
STAR = "STAR"
SEMICOLON = "SEMICOLON"
EOF = "EOF"


class QueryError(ValueError):
    """Raised when a statement cannot be parsed or is not valid for the data."""


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    pos: int

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        if self.kind == EOF:
            return "end of statement"
        return f"{self.value!r} (position {self.pos + 1})"


_NUMBER_RE = re.compile(r"\d+(?:\.\d*)?(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?")
_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_TWO_CHAR_OPS = ("<=", ">=", "<>", "!=", "==")
_ONE_CHAR_OPS = ("=", "<", ">", "+", "-")
_COMPARISON_OPS = frozenset({"<=", ">=", "<>", "!=", "==", "=", "<", ">"})

_SIMPLE_PUNCT = {
    "(": LPAREN,
    ")": RPAREN,
    ",": COMMA,
    "*": STAR,
    ";": SEMICOLON,
}

#: Words with a meaning inside an expression. Using one as a bare column name
#: would be ambiguous, so they are rejected with a clear message instead.
RESERVED_WORDS = frozenset(
    {
        "and",
        "or",
        "not",
        "between",
        "in",
        "like",
        "is",
        "null",
        "true",
        "false",
        "select",
        "from",
        "where",
        "order",
        "by",
        "limit",
        "offset",
        "delete",
        "all",
        "distinct",
        "as",
        "export",
        "last",
        "to",
        "describe",
        "show",
        "tables",
        "help",
        "exit",
        "quit",
    }
)


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------


def tokenize(text: str) -> list[Token]:
    """Split ``text`` into tokens, honouring quoted string literals."""
    tokens: list[Token] = []
    i = 0
    n = len(text)

    while i < n:
        ch = text[i]

        if ch.isspace():
            i += 1
            continue

        # String literal. A doubled quote is an escaped quote, as in SQL.
        if ch in ("'", '"'):
            quote = ch
            start = i
            i += 1
            buf: list[str] = []
            while i < n:
                if text[i] == quote:
                    if i + 1 < n and text[i + 1] == quote:
                        buf.append(quote)
                        i += 2
                        continue
                    break
                buf.append(text[i])
                i += 1
            if i >= n:
                raise QueryError(
                    f"unterminated string literal starting at position {start + 1}"
                )
            tokens.append(Token(STRING, "".join(buf), start))
            i += 1
            continue

        if ch.isdigit() or (ch == "." and i + 1 < n and text[i + 1].isdigit()):
            match = _NUMBER_RE.match(text, i)
            assert match is not None  # guarded by the condition above
            tokens.append(Token(NUMBER, match.group(0), i))
            i = match.end()
            continue

        if ch.isalpha() or ch == "_":
            match = _NAME_RE.match(text, i)
            assert match is not None
            tokens.append(Token(NAME, match.group(0), i))
            i = match.end()
            continue

        two = text[i : i + 2]
        if two in _TWO_CHAR_OPS:
            tokens.append(Token(OP, two, i))
            i += 2
            continue

        if ch in _ONE_CHAR_OPS:
            tokens.append(Token(OP, ch, i))
            i += 1
            continue

        if ch in _SIMPLE_PUNCT:
            tokens.append(Token(_SIMPLE_PUNCT[ch], ch, i))
            i += 1
            continue

        raise QueryError(f"unexpected character {ch!r} at position {i + 1}")

    tokens.append(Token(EOF, "", n))
    return tokens


def split_statements(text: str) -> list[str]:
    """Split a script into statements on ``;`` outside of quoted strings."""
    statements: list[str] = []
    current: list[str] = []
    quote: str | None = None
    i = 0
    while i < len(text):
        ch = text[i]
        if quote is not None:
            current.append(ch)
            if ch == quote:
                if i + 1 < len(text) and text[i + 1] == quote:
                    current.append(text[i + 1])
                    i += 2
                    continue
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            current.append(ch)
        elif ch == ";":
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        else:
            current.append(ch)
        i += 1

    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


# ---------------------------------------------------------------------------
# Syntax tree
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Column:
    """A reference to a column of the table being queried."""

    name: str


@dataclass(frozen=True)
class Literal:
    """A constant value: number, quoted string, TRUE, FALSE or NULL."""

    value: object


@dataclass(frozen=True)
class Compare:
    left: object
    op: str
    right: object


@dataclass(frozen=True)
class Between:
    operand: object
    low: object
    high: object


@dataclass(frozen=True)
class InList:
    operand: object
    values: tuple


@dataclass(frozen=True)
class Like:
    operand: object
    pattern: str


@dataclass(frozen=True)
class IsNull:
    operand: object
    negated: bool = False


@dataclass(frozen=True)
class Logical:
    op: str  # "and" | "or"
    left: object
    right: object


@dataclass(frozen=True)
class Not:
    operand: object


@dataclass(frozen=True)
class SelectItem:
    name: str | None  # None means ``*``
    alias: str | None = None

    @property
    def is_star(self) -> bool:
        return self.name is None

    @property
    def output_name(self) -> str:
        if self.alias is not None:
            return self.alias
        assert self.name is not None
        return self.name


@dataclass(frozen=True)
class OrderKey:
    column: str
    descending: bool = False


@dataclass(frozen=True)
class SelectStatement:
    table: str
    items: tuple[SelectItem, ...]
    where: object | None = None
    order_by: tuple[OrderKey, ...] = ()
    limit: int | None = None
    offset: int = 0
    distinct: bool = False

    @property
    def select_all(self) -> bool:
        return len(self.items) == 1 and self.items[0].is_star


@dataclass(frozen=True)
class DeleteStatement:
    table: str
    where: object | None = None
    all_rows: bool = False


@dataclass(frozen=True)
class ExportStatement:
    filename: str
    overwrite: bool = False


@dataclass(frozen=True)
class DescribeStatement:
    table: str


@dataclass(frozen=True)
class ShowTablesStatement:
    pass


@dataclass(frozen=True)
class HelpStatement:
    pass


@dataclass(frozen=True)
class ExitStatement:
    pass


#: Every statement the parser can return.
Statement = (
    SelectStatement
    | DeleteStatement
    | ExportStatement
    | DescribeStatement
    | ShowTablesStatement
    | HelpStatement
    | ExitStatement
)


# ---------------------------------------------------------------------------
# Recursive descent parser
# ---------------------------------------------------------------------------


class _Parser:
    def __init__(self, tokens: Sequence[Token]) -> None:
        self.tokens = list(tokens)
        self.index = 0

    # -- cursor helpers ---------------------------------------------------
    def peek(self, offset: int = 0) -> Token:
        position = min(self.index + offset, len(self.tokens) - 1)
        return self.tokens[position]

    def advance(self) -> Token:
        token = self.peek()
        if token.kind != EOF:
            self.index += 1
        return token

    def check(self, kind: str) -> bool:
        return self.peek().kind == kind

    def accept(self, kind: str) -> Token | None:
        if self.check(kind):
            return self.advance()
        return None

    def expect(self, kind: str, expected: str) -> Token:
        token = self.peek()
        if token.kind != kind:
            raise QueryError(f"expected {expected}, found {token}")
        return self.advance()

    def accept_keyword(self, word: str) -> Token | None:
        token = self.peek()
        if token.kind == NAME and token.value.casefold() == word.casefold():
            return self.advance()
        return None

    def check_keyword(self, word: str) -> bool:
        token = self.peek()
        return token.kind == NAME and token.value.casefold() == word.casefold()

    def expect_keyword(self, word: str) -> None:
        if not self.accept_keyword(word):
            raise QueryError(f"expected {word.upper()}, found {self.peek()}")

    def expect_name(self, expected: str) -> str:
        token = self.expect(NAME, expected)
        return token.value

    def at_end(self) -> bool:
        return self.peek().kind == EOF

    def finish(self) -> None:
        while self.accept(SEMICOLON):
            pass
        if not self.at_end():
            raise QueryError(
                f"unexpected {self.peek()} after the end of the statement"
            )

    # -- statements -------------------------------------------------------
    def parse(self):
        token = self.peek()
        if token.kind != NAME:
            raise QueryError(f"expected a command, found {token}")

        command = token.value.casefold()
        if command == "select":
            return self.parse_select()
        if command == "delete":
            return self.parse_delete()
        if command == "export":
            return self.parse_export()
        if command == "describe":
            return self.parse_describe()
        if command == "show":
            self.advance()
            self.expect_keyword("tables")
            self.finish()
            return ShowTablesStatement()
        if command == "help":
            self.advance()
            self.finish()
            return HelpStatement()
        if command in ("exit", "quit"):
            self.advance()
            self.finish()
            return ExitStatement()
        raise QueryError(
            f"unknown command {token.value!r}; type HELP to see the available commands"
        )

    def parse_select(self) -> SelectStatement:
        self.advance()  # SELECT
        distinct = self.accept_keyword("distinct") is not None
        items = self.parse_select_items()
        self.expect_keyword("from")
        table = self.expect_name("a table name after FROM")

        where = None
        if self.accept_keyword("where"):
            where = self.parse_expression()

        order_by: tuple[OrderKey, ...] = ()
        if self.check_keyword("order"):
            order_by = self.parse_order_by()

        limit, offset = self.parse_limit_offset()
        self.finish()
        return SelectStatement(
            table=table,
            items=items,
            where=where,
            order_by=order_by,
            limit=limit,
            offset=offset,
            distinct=distinct,
        )

    def parse_select_items(self) -> tuple[SelectItem, ...]:
        if self.accept(STAR) is not None:
            if self.check(COMMA):
                raise QueryError("'*' has to be the only entry of the column list")
            return (SelectItem(None),)

        items: list[SelectItem] = []
        while True:
            if self.check(STAR):
                raise QueryError(
                    "'*' has to be the only entry of the column list"
                )
            name = self.expect_name("a column name or '*'")
            alias = None
            if self.accept_keyword("as"):
                alias = self.expect_name("a column alias after AS")
            items.append(SelectItem(name, alias))
            if self.accept(COMMA) is None:
                break
        return tuple(items)

    def parse_delete(self) -> DeleteStatement:
        self.advance()  # DELETE
        all_rows = self.accept_keyword("all") is not None
        self.expect_keyword("from")
        table = self.expect_name("a table name after FROM")

        where = None
        if self.accept_keyword("where"):
            where = self.parse_expression()

        if all_rows and where is not None:
            raise QueryError(
                "DELETE ALL deletes every row and cannot take a WHERE clause; "
                "use DELETE FROM <table> WHERE <condition> instead"
            )

        self.finish()
        return DeleteStatement(table=table, where=where, all_rows=all_rows)

    def parse_export(self) -> ExportStatement:
        self.advance()  # EXPORT
        self.expect_keyword("last")
        self.expect_keyword("to")
        token = self.expect(STRING, "a quoted file name after EXPORT LAST TO")
        overwrite = self.accept_keyword("overwrite") is not None
        self.finish()
        return ExportStatement(filename=token.value, overwrite=overwrite)

    def parse_describe(self) -> DescribeStatement:
        self.advance()  # DESCRIBE
        if not self.check(NAME):
            raise QueryError(
                "DESCRIBE needs a table name, for example: DESCRIBE customers"
            )
        table = self.expect_name("a table name after DESCRIBE")
        self.finish()
        return DescribeStatement(table=table)

    def parse_order_by(self) -> tuple[OrderKey, ...]:
        self.expect_keyword("order")
        self.expect_keyword("by")

        keys: list[OrderKey] = []
        while True:
            column = self.expect_name("a column name after ORDER BY")
            descending = False
            if self.accept_keyword("desc"):
                descending = True
            else:
                self.accept_keyword("asc")
            keys.append(OrderKey(column, descending))
            if self.accept(COMMA) is None:
                break
        return tuple(keys)

    def parse_limit_offset(self) -> tuple[int | None, int]:
        limit: int | None = None
        offset = 0

        if self.accept_keyword("limit") is not None:
            limit = self.parse_non_negative_int("LIMIT")
        if self.accept_keyword("offset") is not None:
            offset = self.parse_non_negative_int("OFFSET")

        return limit, offset

    def parse_non_negative_int(self, clause: str) -> int:
        token = self.peek()
        if token.kind != NUMBER or not token.value.isdigit():
            raise QueryError(
                f"{clause} needs a whole number of 0 or more, found {token}"
            )
        self.advance()
        return int(token.value)

    # -- expressions ------------------------------------------------------
    def parse_expression(self):
        return self.parse_or()

    def parse_or(self):
        node = self.parse_and()
        while self.accept_keyword("or"):
            node = Logical("or", node, self.parse_and())
        return node

    def parse_and(self):
        node = self.parse_not()
        while self.accept_keyword("and"):
            node = Logical("and", node, self.parse_not())
        return node

    def parse_not(self):
        if self.accept_keyword("not"):
            return Not(self.parse_not())
        return self.parse_primary()

    def parse_primary(self):
        if self.accept(LPAREN) is not None:
            node = self.parse_expression()
            self.expect(RPAREN, "')'")
            return node
        return self.parse_predicate()

    def parse_predicate(self):
        left = self.parse_operand()

        negated = self.accept_keyword("not") is not None

        if self.accept_keyword("between") is not None:
            low = self.parse_operand()
            self.expect_keyword("and")
            high = self.parse_operand()
            node = Between(left, low, high)
            return Not(node) if negated else node

        if self.accept_keyword("in") is not None:
            self.expect(LPAREN, "'(' after IN")
            values: list[object] = []
            if self.check(RPAREN):
                raise QueryError("IN needs at least one value, for example IN (1, 2)")
            while True:
                values.append(self.parse_operand())
                if self.accept(COMMA) is None:
                    break
            self.expect(RPAREN, "')' after the IN list")
            node = InList(left, tuple(values))
            return Not(node) if negated else node

        if self.accept_keyword("like") is not None:
            token = self.expect(STRING, "a quoted pattern after LIKE")
            node = Like(left, token.value)
            return Not(node) if negated else node

        if self.accept_keyword("is") is not None:
            if negated:
                raise QueryError("write IS NOT NULL instead of NOT ... IS NULL")
            is_not = self.accept_keyword("not") is not None
            self.expect_keyword("null")
            return IsNull(left, negated=is_not)

        if negated:
            raise QueryError(
                "NOT is only supported before BETWEEN, IN or LIKE; "
                "use a comparison operator instead"
            )

        op_token = self.expect(OP, "a comparison operator such as = or >=")
        if op_token.value not in _COMPARISON_OPS:
            raise QueryError(
                f"expected a comparison operator, found {op_token.value!r}"
            )
        right = self.parse_operand()
        return Compare(left, op_token.value, right)

    def parse_operand(self):
        token = self.peek()

        if token.kind == NUMBER:
            self.advance()
            return Literal(_as_number(token.value))

        if token.kind == STRING:
            self.advance()
            return Literal(token.value)

        if token.kind == OP and token.value in ("+", "-"):
            self.advance()
            number = self.expect(NUMBER, "a number after the sign")
            value = _as_number(number.value)
            return Literal(-value if token.value == "-" else value)

        if token.kind == NAME:
            keyword = token.value.casefold()
            if keyword == "true":
                self.advance()
                return Literal(True)
            if keyword == "false":
                self.advance()
                return Literal(False)
            if keyword == "null":
                self.advance()
                return Literal(None)
            if keyword in RESERVED_WORDS:
                raise QueryError(
                    f"unexpected keyword {token.value!r}; "
                    "quote it as a string or rename the column"
                )
            self.advance()
            return Column(token.value)

        raise QueryError(f"expected a column name or a value, found {token}")


def _as_number(text: str):
    if re.fullmatch(r"\d+", text):
        return int(text)
    return float(text)


def parse_statement(text: str) -> Statement:
    """Parse one statement. Raises :class:`QueryError` if it is not valid."""
    if not str(text).strip():
        raise QueryError("empty statement")
    return _Parser(tokenize(str(text))).parse()
