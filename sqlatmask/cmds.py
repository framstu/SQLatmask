# cmds.py
# Functions for queries

import pandas as pd

from . import iodata
from . import where
from .queryparser import (
    DeleteStatement,
    OrderKey,
    QueryError,
    SelectItem,
    SelectStatement,
    parse_statement,
)

#: How many rows a printed result shows before it is truncated. EXPORT LAST
#: always writes every row of the result.
MAX_PRINT_ROWS = 100


def _statement(query):
    """Accept either a parsed statement or the text of one."""
    if isinstance(query, (SelectStatement, DeleteStatement)):
        return query
    return parse_statement(query)


# ---------------------------------------------------------------------------
# Printing
# ---------------------------------------------------------------------------


def format_table(frame: pd.DataFrame, max_rows: int | None = MAX_PRINT_ROWS) -> str:
    """Render ``frame`` as text, truncated to ``max_rows`` rows."""
    if frame.empty:
        columns = ", ".join(str(column) for column in frame.columns)
        return f"(0 rows), columns: {columns}" if columns else "(0 rows)"

    rows = len(frame)
    if max_rows is None or max_rows <= 0:
        shown = frame
    else:
        shown = frame.head(max_rows)

    text = shown.to_string(index=False)
    if len(shown) == rows:
        return f"{text}\n({rows} row{'' if rows == 1 else 's'})"
    return (
        f"{text}\n(showing {len(shown)} of {rows} rows - "
        "EXPORT LAST TO 'file.json' saves all of them)"
    )


def _print_result(frame: pd.DataFrame, *, out=print, max_rows=None) -> None:
    limit = MAX_PRINT_ROWS if max_rows is None else max_rows
    out(format_table(frame, limit))


# ---------------------------------------------------------------------------
# SELECT
# ---------------------------------------------------------------------------


def _project(frame: pd.DataFrame, items: tuple[SelectItem, ...]) -> pd.DataFrame:
    """Pick the requested columns, honouring ``AS`` aliases."""
    if len(items) == 1 and items[0].is_star:
        return frame

    chosen: list[object] = []
    renamed: dict[object, str] = {}
    for item in items:
        assert item.name is not None
        column = where.match_column(frame, item.name)
        output = item.output_name
        if output in renamed.values():
            raise QueryError(f"two columns would both be called {output!r}")
        chosen.append(column)
        renamed[column] = output

    selected = frame[chosen].copy()
    selected.columns = [renamed[column] for column in chosen]
    return selected


def _order(frame: pd.DataFrame, keys: tuple[OrderKey, ...]) -> pd.DataFrame:
    columns = [where.match_column(frame, key.column) for key in keys]
    if len(set(columns)) != len(columns):
        raise QueryError(
            "ORDER BY lists the same column twice: "
            + ", ".join(str(column) for column in columns)
        )
    ascending = [not key.descending for key in keys]
    return frame.sort_values(
        by=columns, ascending=ascending, kind="stable", na_position="last"
    )


def execute_select(query, *, out=print, max_rows=None) -> pd.DataFrame:
    """Run a SELECT and return its result.

    Raises :class:`queryparser.QueryError` for anything wrong with the statement or
    the data. The result is also stored in ``iodata.LAST_RESULT`` so that
    ``EXPORT LAST TO`` can write it out.
    """
    statement = _statement(query)
    if not isinstance(statement, SelectStatement):  # pragma: no cover - CLI guards
        raise QueryError("internal error: not a SELECT statement")

    frame = iodata.table_frame(statement.table)

    if statement.where is not None:
        mask = where.evaluate(statement.where, frame)
        frame = frame[mask]

    if statement.order_by:
        frame = _order(frame, statement.order_by)

    if statement.offset:
        frame = frame.iloc[statement.offset :]
    if statement.limit is not None:
        frame = frame.iloc[: statement.limit]

    frame = _project(frame, statement.items)

    if statement.distinct:
        frame = frame.drop_duplicates()

    result = frame.reset_index(drop=True)
    iodata.LAST_RESULT = result.copy()

    _print_result(result, out=out, max_rows=max_rows)
    return result


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------


def execute_delete(query, *, out=print) -> int:
    """Delete the matching rows and return how many were removed."""
    statement = _statement(query)
    if not isinstance(statement, DeleteStatement):  # pragma: no cover - CLI guards
        raise QueryError("internal error: not a DELETE statement")

    name = iodata.resolve_table(statement.table)
    frame = iodata.DATABASES[name]

    if statement.where is None:
        if not statement.all_rows:
            raise QueryError(
                f"refusing to delete every row of {name!r} without a WHERE clause; "
                f"use DELETE FROM {name} WHERE <condition>, "
                f"or DELETE ALL FROM {name} to empty the table on purpose"
            )
        masked = slice(0, 0)
        kept = frame.iloc[masked]
        removed = frame
    else:
        mask = where.evaluate(statement.where, frame)
        removed = frame[mask]
        kept = frame[~mask]

    iodata.DATABASES[name] = kept.reset_index(drop=True)
    if len(removed):
        iodata.mark_dirty(name)

    out(f"[OK] Deleted {len(removed)} of {len(frame)} rows from '{name}'")
    return len(removed)
