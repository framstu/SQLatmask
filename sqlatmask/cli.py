# main.py
# Main file containing the main function.

"""SQLatmask - query JSON tables with a small SQL dialect.

Three ways to use it::

    python main.py                                  # interactive prompt
    python main.py -c "SELECT * FROM customers"     # one statement
    python main.py --file queries.sql               # a script of statements
"""

from __future__ import annotations

import argparse
import sys

from . import cmds
from . import iodata
from . import queryparser
from . import shelp

PROMPT = "SQL> "


def ask_yes_no(question: str) -> bool:
    """Ask a yes/no question; anything but y/yes is a no."""
    try:
        answer = input(question)
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer.strip().casefold() in ("y", "yes")


# ---------------------------------------------------------------------------
# Statement execution
# ---------------------------------------------------------------------------


def run_statement(statement, *, confirm=None, out=print, interactive=False) -> bool:
    """Run one parsed statement. Returns False when the session should end."""
    if isinstance(statement, queryparser.ExitStatement):
        if interactive:
            save_changes(confirm=confirm, out=out)
        return False

    if isinstance(statement, queryparser.HelpStatement):
        shelp.showhelp(out=out)
        return True

    if isinstance(statement, queryparser.ShowTablesStatement):
        iodata.show_tables(out=out)
        return True

    if isinstance(statement, queryparser.DescribeStatement):
        iodata.describe_table(statement.table, out=out)
        return True

    if isinstance(statement, queryparser.SelectStatement):
        cmds.execute_select(statement, out=out)
        return True

    if isinstance(statement, queryparser.DeleteStatement):
        cmds.execute_delete(statement, out=out)
        return True

    if isinstance(statement, queryparser.ExportStatement):
        iodata.execute_export_last(statement, confirm=confirm, out=out)
        return True

    raise queryparser.QueryError(f"nothing to do for {type(statement).__name__}")


def run_line(line: str, *, confirm=None, out=print, interactive=False) -> bool:
    """Parse and run one line of input. Errors are printed, never raised."""
    text = line.strip()
    if not text:
        return True

    try:
        statement = queryparser.parse_statement(text)
    except queryparser.QueryError as error:
        out(f"[ERROR] {error}")
        return True

    try:
        return run_statement(
            statement, confirm=confirm, out=out, interactive=interactive
        )
    except queryparser.QueryError as error:
        out(f"[ERROR] {error}")
        return True
    except Exception as error:  # noqa: BLE001 - a bad statement must not end the session
        out(f"[CRASH] {type(error).__name__}: {error}")
        return True


def save_changes(*, confirm=None, out=print) -> None:
    """Offer to write unsaved tables back to disk."""
    if not iodata.DIRTY:
        return

    tables = ", ".join(sorted(iodata.DIRTY))
    question = f"Save changes to {tables} before exiting? (Y/N): "
    confirmed = confirm(question) if confirm is not None else ask_yes_no(question)
    if not confirmed:
        out("[INFO] Changes not saved")
        return

    failures = iodata.save_json_files(out=out)
    if failures:
        out(
            "[ERROR] Some tables could not be saved: "
            + ", ".join(table for table, _ in failures)
        )
    else:
        out("[OK] Changes saved")


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    argument_parser = argparse.ArgumentParser(
        prog="sqlatmask",
        description="Query JSON tables with a small SQL dialect.",
    )
    argument_parser.add_argument(
        "--data",
        metavar="DIR",
        default=None,
        help="directory holding the .json tables (default: mockdata)",
    )
    argument_parser.add_argument(
        "-c",
        "--query",
        metavar="SQL",
        action="append",
        default=None,
        help="run one statement and exit (repeatable)",
    )
    argument_parser.add_argument(
        "--file",
        metavar="PATH",
        default=None,
        help="run the statements of a script file and exit",
    )
    argument_parser.add_argument(
        "--no-banner",
        action="store_true",
        help="do not print the help banner",
    )
    argument_parser.add_argument(
        "--max-rows",
        metavar="N",
        type=int,
        default=None,
        help=f"rows printed per result (default {cmds.MAX_PRINT_ROWS}, 0 for all)",
    )
    return argument_parser


def run_batch(statements) -> int:
    """Run statements without a prompt. Returns a process exit code."""
    failures = 0
    for text in statements:
        if not text.strip():
            continue
        try:
            statement = queryparser.parse_statement(text)
            finished = run_statement(statement, out=print, interactive=False)
        except queryparser.QueryError as error:
            print(f"[ERROR] {error}")
            failures += 1
            continue
        except Exception as error:  # noqa: BLE001 - report and keep going
            print(f"[CRASH] {type(error).__name__}: {error}")
            failures += 1
            continue

        if not finished:
            break

    return 1 if failures else 0


def interactive_loop() -> int:
    while True:
        try:
            line = input(PROMPT)
        except EOFError:
            print()
            save_changes()
            break
        except KeyboardInterrupt:
            print()
            save_changes()
            break

        try:
            if not run_line(line, confirm=ask_yes_no, interactive=True):
                break
        except KeyboardInterrupt:
            print()
            break

    return 0


def main(argv=None) -> int:
    arguments = build_parser().parse_args(argv)

    if arguments.data:
        iodata.set_data_dir(arguments.data)
    iodata.load_json_files()

    if arguments.max_rows is not None:
        cmds.MAX_PRINT_ROWS = arguments.max_rows

    statements: list[str] = list(arguments.query or [])

    if arguments.file:
        try:
            with open(arguments.file, "r", encoding="utf-8") as handle:
                statements.extend(queryparser.split_statements(handle.read()))
        except OSError as error:
            print(f"[ERROR] Cannot read {arguments.file}: {error}")
            return 2

    if statements:
        return run_batch(statements)

    if not arguments.no_banner:
        shelp.showhelp()

    return interactive_loop()


# Always loading the main function
if __name__ == "__main__":
    sys.exit(main())
