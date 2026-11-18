# iodata.py
# Functions for loading, importing, saving and exporting tables into .JSON files

import json
import os
from dataclasses import dataclass, field
from typing import cast

import pandas as pd

from .queryparser import ExportStatement, QueryError, parse_statement

#: Directory the tables are read from and written to. Override with the
#: SQLATMASK_DATA environment variable or iodata.set_data_dir().
DATA = os.environ.get("SQLATMASK_DATA", "mockdata")

DATABASES: dict[str, pd.DataFrame] = {}  # Tables loaded into memory
LAST_RESULT = None  # Result of the latest SELECT, ready for EXPORT LAST
DIRTY: set[str] = set()  # Tables changed since the last save


@dataclass
class LoadReport:
    """What load_json_files() managed to read, and what it had to skip."""

    loaded: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.skipped


def set_data_dir(path: str) -> None:
    """Point the module at another data directory."""
    global DATA
    DATA = str(path)


def data_dir() -> str:
    return DATA


def _print(message: str = "", *, out=print) -> None:
    out(message)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _frame_from_json(payload) -> pd.DataFrame:
    """Validate the shape of a table file: a JSON array of objects."""
    if not isinstance(payload, list):
        raise ValueError(
            f"expected a JSON array of objects, found {type(payload).__name__}"
        )
    for position, row in enumerate(payload, start=1):
        if not isinstance(row, dict):
            raise ValueError(
                f"row {position} is not an object (found {type(row).__name__})"
            )
    return pd.DataFrame(payload)


def load_json_files(path: str | None = None, *, out=print) -> LoadReport:
    """Load every .json table in ``path``.

    A file that cannot be used is reported and skipped; it is never replaced by
    an empty table, because that would make a broken file look like a table
    with no rows.
    """
    directory = path or data_dir()
    report = LoadReport()

    if not os.path.exists(directory):
        os.makedirs(directory)
        _print(f"[INFO] Created directory: {directory}", out=out)  # Fresh checkout

    try:
        entries = sorted(os.listdir(directory))
    except OSError as error:
        _print(f"[ERROR] Cannot read {directory}: {error}", out=out)
        report.skipped.append((directory, str(error)))
        return report

    for filename in entries:
        if not filename.endswith(".json"):  # Only reading .json files!
            continue

        file_path = os.path.join(directory, filename)
        table_name = filename[:-5]

        try:
            with open(file_path, "r", encoding="utf-8-sig") as handle:
                payload = json.load(handle)
            DATABASES[table_name] = _frame_from_json(payload)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            report.skipped.append((filename, str(error)))
            _print(f"[ERROR] Failed loading {filename}: {error}", out=out)
            continue

        report.loaded.append(table_name)
        _print(f"[OK] Loaded: {table_name} ({len(DATABASES[table_name])} rows)", out=out)

    return report


# Saving data, function for .json only
# ---------------------------------------------------------------------------
# Saving
# ---------------------------------------------------------------------------


def mark_dirty(table: str) -> None:
    DIRTY.add(table)


def save_json_files(tables=None, *, out=print) -> list[tuple[str, str]]:
    """Write tables back to disk. Returns the list of tables that failed.

    Only tables listed in :data:`DIRTY` are written unless ``tables`` is given,
    and every file goes through a temporary file first, so an interrupted save
    cannot leave a half-written table behind.
    """
    targets = sorted(DIRTY) if tables is None else [str(table) for table in tables]
    failures: list[tuple[str, str]] = []

    for table in targets:
        if table not in DATABASES:
            failures.append((table, "table is not loaded"))
            continue
        path = os.path.join(data_dir(), f"{table}.json")
        temp = f"{path}.tmp"
        try:
            DATABASES[table].to_json(temp, orient="records", indent=2)
            os.replace(temp, path)
            DIRTY.discard(table)
        except Exception as error:  # noqa: BLE001 - reported, never swallowed
            failures.append((table, str(error)))
            _print(f"[ERROR] Failed saving {table}: {error}", out=out)
            if os.path.exists(temp):
                os.remove(temp)

    return failures


# Showing / listing tables
# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


def resolve_table(name: str) -> str:
    """Return the loaded table called ``name`` (case-insensitive)."""
    if name in DATABASES:
        return name

    folded = str(name).casefold()
    matches = [table for table in DATABASES if table.casefold() == folded]
    if not matches:
        available = ", ".join(sorted(DATABASES)) or "(none)"
        raise QueryError(f"table {name!r} not found; loaded tables: {available}")
    if len(matches) > 1:
        raise QueryError(
            f"table name {name!r} is ambiguous: " + ", ".join(sorted(matches))
        )
    return matches[0]


def table_frame(name: str) -> pd.DataFrame:
    return DATABASES[resolve_table(name)]


def show_tables(*, out=print) -> list[str]:
    _print("\nTables:", out=out)
    if not DATABASES:
        _print(" (no tables loaded)", out=out)
    for name in sorted(DATABASES):
        marker = " *" if name in DIRTY else ""
        _print(f" - {name} ({len(DATABASES[name])} rows){marker}", out=out)
    return sorted(DATABASES)


# Describing table
def describe_table(table: str, *, out=print) -> pd.DataFrame:
    """Print a column summary and return it as a DataFrame."""
    name = resolve_table(table)
    frame = DATABASES[name]

    rows = []
    total = len(frame)
    for column in frame.columns:
        series = cast(pd.Series, frame[column])
        missing = len(series) - len(series.dropna())
        rows.append(
            {
                "column": str(column),
                "type": str(series.dtype),
                "non_null": total - missing,
                "null": missing,
                "example": _first_value(series),
            }
        )

    summary = pd.DataFrame(
        rows, columns=["column", "type", "non_null", "null", "example"]
    )

    _print(f"\n{name} ({len(frame)} rows, {len(frame.columns)} columns)", out=out)
    if summary.empty:
        _print(" (no columns)", out=out)
    else:
        _print(summary.to_string(index=False), out=out)
    return summary


def _first_value(series: pd.Series) -> str:
    for value in series:
        if pd.isna(value):
            continue
        text = str(value)
        return text if len(text) <= 24 else text[:21] + "..."
    return ""


# Export function; when exporting, exports the last results
# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def safe_export_path(filename: str, *, directory: str | None = None) -> str:
    """Turn a user supplied file name into a path inside the data directory."""
    name = str(filename).strip()
    if not name:
        raise QueryError(
            "EXPORT needs a file name, for example: EXPORT LAST TO 'out.json'"
        )

    if os.path.basename(name) != name or name in (".", ".."):
        raise QueryError(
            f"{filename!r} has to be a plain file name inside the data directory"
        )
    if not name.lower().endswith(".json"):
        raise QueryError(f"{filename!r} has to end with .json")

    folder = os.path.realpath(directory or data_dir())
    candidate = os.path.realpath(os.path.join(folder, name))
    if os.path.dirname(candidate) != folder:
        raise QueryError(
            f"{filename!r} has to be a plain file name inside the data directory"
        )
    return candidate


def execute_export_last(query, *, confirm=None, out=print) -> str | None:
    """Export the last SELECT result and return the path (or None if cancelled)."""
    statement = query
    if isinstance(query, str):
        statement = parse_statement(query)

    if not isinstance(statement, ExportStatement):  # pragma: no cover - CLI guards
        raise QueryError("internal error: not an EXPORT statement")

    if LAST_RESULT is None:
        raise QueryError("no previous result to export; run a SELECT first")

    path = safe_export_path(statement.filename)

    if os.path.exists(path) and not statement.overwrite:
        if confirm is None:
            raise QueryError(
                f"{os.path.basename(path)!r} already exists; "
                "add OVERWRITE to the command to replace it"
            )
        if not confirm(f"File {os.path.basename(path)!r} exists. Overwrite? (Y/N): "):
            _print("[INFO] Export cancelled", out=out)
            return None

    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    temp = f"{path}.tmp"
    try:
        LAST_RESULT.to_json(temp, orient="records", indent=2)
        os.replace(temp, path)
    except Exception:
        if os.path.exists(temp):
            os.remove(temp)
        raise

    _print(f"[OK] Exported {len(LAST_RESULT)} rows to {path}", out=out)
    return path
