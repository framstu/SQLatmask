"""Evaluation of WHERE conditions against a pandas DataFrame.

The old code translated a WHERE clause into a ``DataFrame.query()`` string with
``str.replace`` calls and, when anything went wrong, returned the *whole*
DataFrame. In a SELECT that meant "no filtering"; in a DELETE it meant the
entire table was wiped. This module evaluates the parsed condition directly
against the data and raises :class:`queryparser.QueryError` for anything it cannot
answer, so a broken condition can never be mistaken for "everything matches".
"""

from __future__ import annotations

import operator
import re

import pandas as pd
from pandas.api import types as ptypes

from .queryparser import (
    Between,
    Column,
    Compare,
    InList,
    IsNull,
    Like,
    Literal,
    Logical,
    Not,
    QueryError,
)

__all__ = ["evaluate", "match_column", "LIKE_CASE_SENSITIVE"]

#: LIKE is matched case-insensitively, as SQLite does, so that
#: ``LIKE 'al%'`` finds "Alice". Set to True to make it exact-case.
LIKE_CASE_SENSITIVE = False

_OPERATORS = {
    "=": operator.eq,
    "==": operator.eq,
    "!=": operator.ne,
    "<>": operator.ne,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
}


# ---------------------------------------------------------------------------
# Column resolution
# ---------------------------------------------------------------------------


def _column_index(df: pd.DataFrame) -> dict[str, list[object]]:
    index: dict[str, list[object]] = {}
    for column in df.columns:
        index.setdefault(str(column).casefold(), []).append(column)
    return index


def match_column(df: pd.DataFrame, name: str) -> object:
    """Return the real column label for ``name``, matching case-insensitively."""
    if name in df.columns:
        return name

    candidates = _column_index(df).get(str(name).casefold(), [])
    if not candidates:
        available = ", ".join(str(column) for column in df.columns)
        raise QueryError(
            f"unknown column {name!r}; table has: {available or '(no columns)'}"
        )
    if len(candidates) > 1:
        raise QueryError(
            f"column name {name!r} is ambiguous: "
            + ", ".join(str(column) for column in candidates)
        )
    return candidates[0]


def _is_bool_series(series: pd.Series) -> bool:
    return ptypes.is_bool_dtype(series.dtype)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_text_series(series: pd.Series) -> bool:
    return ptypes.is_string_dtype(series.dtype) or ptypes.is_object_dtype(series.dtype)


# ---------------------------------------------------------------------------
# Operand handling
# ---------------------------------------------------------------------------


def _operand(node, df: pd.DataFrame, label: str):
    if isinstance(node, Column):
        return df[match_column(df, node.name)]
    if isinstance(node, Literal):
        return node.value
    if isinstance(node, (Between, Compare, Logical, Not, InList, Like, IsNull)):
        raise QueryError(
            f"{label} needs a column name or a plain value, not a nested condition"
        )
    raise QueryError(f"{label} contains an unsupported expression")


def _series_label(node, df: pd.DataFrame) -> str:
    if isinstance(node, Column):
        return f"column {match_column(df, node.name)!r}"
    return "value"


def _check_comparable(series: pd.Series, value: object, label: str) -> tuple:
    """Coerce ``series``/``value`` to a comparable pair or explain why not."""
    if value is None:
        raise QueryError(
            f"{label} cannot be compared with NULL (it never matches); "
            "use IS NULL or IS NOT NULL"
        )

    if isinstance(value, bool):
        if _is_bool_series(series):
            return series, value
        if ptypes.is_numeric_dtype(series.dtype):
            raise QueryError(
                f"{label} holds numbers, so compare it with a number "
                "instead of TRUE/FALSE"
            )
        raise QueryError(f"{label} does not hold boolean values")

    if _is_number(value):
        if _is_bool_series(series):
            raise QueryError(f"{label} holds boolean values, not numbers")
        if ptypes.is_numeric_dtype(series.dtype):
            return series, value

        coerced = pd.Series(pd.to_numeric(series, errors="coerce"))
        if coerced.notna().sum() == 0:
            raise QueryError(
                f"{label} holds text that cannot be compared with the number "
                f"{value!r}; quote the value to compare it as text"
            )
        return coerced, value

    if isinstance(value, str):
        if ptypes.is_numeric_dtype(series.dtype) and not _is_bool_series(series):
            raise QueryError(
                f"{label} holds numbers, so {value!r} (text) cannot be "
                "compared with it; remove the quotes"
            )
        if _is_bool_series(series):
            raise QueryError(f"{label} holds boolean values, not text")
        return series.astype("string"), value

    raise QueryError(f"{label} cannot be compared with {type(value).__name__}")


def _as_mask(result, index: pd.Index) -> pd.Series:
    if isinstance(result, pd.Series):
        mask = result
        if mask.dtype != bool:
            mask = mask.astype("boolean").fillna(False).astype(bool)
        return mask.reindex(index)
    return pd.Series(bool(result), index=index)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def evaluate(node, df: pd.DataFrame) -> pd.Series:
    """Return a boolean Series selecting the rows that satisfy ``node``."""
    mask = _evaluate(node, df)
    return _as_mask(mask, df.index).fillna(False).astype(bool)


def _evaluate(node, df: pd.DataFrame):
    if isinstance(node, Logical):
        left = _as_mask(_evaluate(node.left, df), df.index)
        right = _as_mask(_evaluate(node.right, df), df.index)
        if node.op == "and":
            return left & right
        if node.op == "or":
            return left | right
        raise QueryError(f"unsupported logical operator {node.op!r}")

    if isinstance(node, Not):
        return ~_as_mask(_evaluate(node.operand, df), df.index)

    if isinstance(node, Compare):
        return _compare(node, df)

    if isinstance(node, Between):
        lower = Compare(node.operand, ">=", node.low)
        upper = Compare(node.operand, "<=", node.high)
        return _evaluate(Logical("and", lower, upper), df)

    if isinstance(node, InList):
        return _in_list(node, df)

    if isinstance(node, Like):
        return _like(node, df)

    if isinstance(node, IsNull):
        series = _operand(node.operand, df, "IS NULL")
        if not isinstance(series, pd.Series):
            return pd.Series(series is None, index=df.index)
        mask = series.isna()
        return ~mask if node.negated else mask

    raise QueryError(f"unsupported condition: {node!r}")


def _compare(node: Compare, df: pd.DataFrame):
    left = _operand(node.left, df, "comparison")
    right = _operand(node.right, df, "comparison")
    op = _OPERATORS.get(node.op)
    if op is None:
        raise QueryError(f"unsupported comparison operator {node.op!r}")

    if isinstance(left, pd.Series) and isinstance(right, pd.Series):
        return _compare_series(left, right, op, node, df)

    if isinstance(left, pd.Series):
        series, value = _check_comparable(left, right, _series_label(node.left, df))
        return _as_mask(op(series, value), df.index)

    if isinstance(right, pd.Series):
        series, value = _check_comparable(right, left, _series_label(node.right, df))
        return _as_mask(op(series, value), df.index)

    return pd.Series(bool(op(left, right)), index=df.index)


def _compare_series(left: pd.Series, right: pd.Series, op, node, df: pd.DataFrame):
    left_numeric = ptypes.is_numeric_dtype(left.dtype) and not _is_bool_series(left)
    right_numeric = ptypes.is_numeric_dtype(right.dtype) and not _is_bool_series(right)
    left_text = _is_text_series(left)
    right_text = _is_text_series(right)

    if left_numeric and right_numeric:
        return _as_mask(op(left, right), df.index)
    if left_text and right_text:
        return _as_mask(op(left.astype("string"), right.astype("string")), df.index)

    raise QueryError(
        f"cannot compare {_series_label(node.left, df)} with "
        f"{_series_label(node.right, df)}: one holds numbers and the other text"
    )


def _in_list(node: InList, df: pd.DataFrame):
    operand = _operand(node.operand, df, "IN")
    if not isinstance(operand, pd.Series):
        values = [
            _operand(value, df, "IN") for value in node.values
        ]
        return pd.Series(operand in values, index=df.index)

    label = _series_label(node.operand, df)
    values = []
    for entry in node.values:
        value = _operand(entry, df, f"the IN list of {label}")
        if isinstance(value, pd.Series):
            raise QueryError(f"the IN list of {label} has to contain plain values")
        if value is None:
            continue  # NULL never matches with IN
        values.append(value)

    if not values:
        return pd.Series(False, index=df.index)

    if _is_bool_series(operand):
        if any(not isinstance(value, bool) for value in values):
            raise QueryError(f"{label} holds boolean values, so the IN list must too")
    elif ptypes.is_numeric_dtype(operand.dtype):
        if any(not _is_number(value) for value in values):
            raise QueryError(
                f"{label} holds numbers, so every value of the IN list must be a number"
            )
    else:
        if any(not isinstance(value, str) for value in values):
            raise QueryError(
                f"{label} holds text, so every value of the IN list must be quoted"
            )
        return _as_mask(operand.astype("string").isin(values), df.index)

    return _as_mask(operand.isin(values), df.index)


def _like_regex(pattern: str) -> str:
    parts = []
    for char in pattern:
        if char == "%":
            parts.append(".*")
        elif char == "_":
            parts.append(".")
        else:
            parts.append(re.escape(char))
    return "".join(parts)


def _like(node: Like, df: pd.DataFrame):
    operand = _operand(node.operand, df, "LIKE")
    label = _series_label(node.operand, df)
    if not isinstance(operand, pd.Series):
        raise QueryError("LIKE needs a column on the left, not a plain value")

    if not _is_text_series(operand):
        raise QueryError(
            f"{label} does not hold text, so LIKE cannot be applied to it"
        )

    mask = operand.astype("string").str.fullmatch(
        _like_regex(node.pattern), case=LIKE_CASE_SENSITIVE, na=False
    )
    return _as_mask(mask, df.index)
