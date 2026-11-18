"""End-to-end tests for the command line interface."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from sample_data import PEOPLE

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def cli_dir(tmp_path):
    directory = tmp_path / "tables"
    directory.mkdir()
    (directory / "people.json").write_text(json.dumps(PEOPLE), encoding="utf-8")
    return directory


def run_cli(args, *, data_dir, stdin=None):
    return subprocess.run(
        [sys.executable, "main.py", "--data", str(data_dir), *args],
        cwd=ROOT,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_single_statement(cli_dir):
    result = run_cli(
        ["-c", "select name from people where age > 30 order by age"], data_dir=cli_dir
    )

    assert result.returncode == 0
    assert "Bob" in result.stdout
    assert "Eve" in result.stdout
    assert "Alice" not in result.stdout


def test_several_statements(cli_dir):
    result = run_cli(
        ["-c", "SELECT name FROM people ORDER BY id LIMIT 1", "-c", "SHOW TABLES"],
        data_dir=cli_dir,
    )

    assert result.returncode == 0
    assert "Alice" in result.stdout
    assert "people (6 rows)" in result.stdout


def test_failing_statement_sets_the_exit_code(cli_dir):
    result = run_cli(["-c", "SELECT nope FROM people"], data_dir=cli_dir)

    assert result.returncode == 1
    assert "[ERROR] unknown column 'nope'" in result.stdout


def test_script_file(cli_dir, tmp_path):
    script = tmp_path / "queries.sql"
    script.write_text(
        "SELECT name FROM people WHERE id = 1;\n"
        "SELECT name FROM people WHERE id = 2\n",
        encoding="utf-8",
    )

    result = run_cli(["--file", str(script)], data_dir=cli_dir)

    assert result.returncode == 0
    assert "Alice" in result.stdout
    assert "Bob" in result.stdout


def test_missing_script_file(cli_dir, tmp_path):
    result = run_cli(["--file", str(tmp_path / "nope.sql")], data_dir=cli_dir)

    assert result.returncode == 2
    assert "Cannot read" in result.stdout


def test_max_rows(cli_dir):
    result = run_cli(["--max-rows", "2", "-c", "SELECT * FROM people"], data_dir=cli_dir)
    assert "showing 2 of 6 rows" in result.stdout


def test_export_from_the_command_line(cli_dir):
    result = run_cli(
        [
            "-c",
            "SELECT name FROM people WHERE id = 1",
            "-c",
            "EXPORT LAST TO 'one.json'",
        ],
        data_dir=cli_dir,
    )

    assert result.returncode == 0
    written = json.loads((cli_dir / "one.json").read_text(encoding="utf-8"))
    assert written == [{"name": "Alice"}]


def test_interactive_saves_with_a_lowercase_answer(cli_dir):
    result = run_cli(
        [],
        data_dir=cli_dir,
        stdin="DELETE FROM people WHERE id = 1\nexit\ny\n",
    )

    assert result.returncode == 0
    assert "Save changes to people" in result.stdout
    assert "[OK] Changes saved" in result.stdout
    saved = json.loads((cli_dir / "people.json").read_text(encoding="utf-8"))
    assert len(saved) == 5
    assert all(row["id"] != 1 for row in saved)


def test_interactive_can_decline_to_save(cli_dir):
    result = run_cli(
        [],
        data_dir=cli_dir,
        stdin="DELETE FROM people WHERE id = 1\nexit\nn\n",
    )

    assert result.returncode == 0
    assert "[INFO] Changes not saved" in result.stdout
    saved = json.loads((cli_dir / "people.json").read_text(encoding="utf-8"))
    assert len(saved) == 6


def test_interactive_does_not_ask_when_nothing_changed(cli_dir):
    result = run_cli([], data_dir=cli_dir, stdin="SELECT * FROM people LIMIT 1\nexit\n")

    assert result.returncode == 0
    assert "Save changes" not in result.stdout


def test_interactive_survives_a_broken_statement(cli_dir):
    result = run_cli(
        [],
        data_dir=cli_dir,
        stdin="SELECT * FROM nope\nSHOW TABLES\nexit\n",
    )

    assert result.returncode == 0
    assert "[ERROR] table 'nope' not found" in result.stdout
    assert "people (6 rows)" in result.stdout


def test_interactive_describe_without_a_table_name(cli_dir):
    result = run_cli([], data_dir=cli_dir, stdin="DESCRIBE\nSHOW TABLES\nexit\n")

    assert result.returncode == 0
    assert "[ERROR] DESCRIBE needs a table name" in result.stdout
    assert "people (6 rows)" in result.stdout


def test_interactive_accepts_lowercase_commands(cli_dir):
    result = run_cli([], data_dir=cli_dir, stdin="show tables\nhelp\nexit\n")

    assert result.returncode == 0
    assert "people (6 rows)" in result.stdout
    assert "SQLatmask" in result.stdout


def test_interactive_eof_saves_nothing_when_unchanged(cli_dir):
    result = run_cli([], data_dir=cli_dir, stdin="SHOW TABLES\n")

    assert result.returncode == 0
    assert "Tables:" in result.stdout
