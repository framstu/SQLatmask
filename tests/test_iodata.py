"""Tests for loading, saving and exporting tables."""

import json
import os

import pandas as pd
import pytest

from sqlatmask import cmds
from sqlatmask import iodata
from sqlatmask import queryparser as qp
from sample_data import CODES, PEOPLE


def write(directory, name, payload):
    path = directory / name
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def test_load_reads_every_json_table(data_dir, capture):
    report = iodata.load_json_files(str(data_dir), out=capture)

    assert report.loaded == ["people"]
    assert report.ok
    assert len(iodata.DATABASES["people"]) == 6
    assert "[OK] Loaded: people (6 rows)" in capture.text


def test_load_skips_files_it_cannot_use(data_dir, capture):
    write(data_dir, "object.json", {"id": 1})
    write(data_dir, "rows.json", [1, 2, 3])
    write(data_dir, "broken.json", "{not json")
    write(data_dir, "ignored.txt", "hello")

    report = iodata.load_json_files(str(data_dir), out=capture)

    assert report.loaded == ["people"]
    assert sorted(name for name, _ in report.skipped) == [
        "broken.json",
        "object.json",
        "rows.json",
    ]
    assert not report.ok
    assert set(iodata.DATABASES) == {"people"}
    assert "expected a JSON array of objects" in capture.text
    assert "row 1 is not an object" in capture.text


def test_load_creates_a_missing_directory(tmp_path, capture):
    missing = tmp_path / "fresh"
    report = iodata.load_json_files(str(missing), out=capture)

    assert missing.is_dir()
    assert report.loaded == []
    assert report.ok is True
    assert "[INFO] Created directory" in capture.text


def test_load_accepts_a_utf8_bom(data_dir):
    payload = json.dumps(CODES)
    (data_dir / "codes.json").write_bytes(b"\xef\xbb\xbf" + payload.encode("utf-8"))

    report = iodata.load_json_files(str(data_dir), out=lambda *_: None)

    assert "codes" in report.loaded
    assert len(iodata.DATABASES["codes"]) == 3


def test_table_names_come_from_the_file_name(data_dir):
    write(data_dir, "Orders_2025.json", [{"id": 1}])
    iodata.load_json_files(str(data_dir), out=lambda *_: None)
    assert "Orders_2025" in iodata.DATABASES


# ---------------------------------------------------------------------------
# Saving
# ---------------------------------------------------------------------------


def test_save_writes_only_dirty_tables(data_dir, capture):
    write(data_dir, "codes.json", CODES)
    iodata.load_json_files(str(data_dir), out=capture)

    before = (data_dir / "codes.json").read_text(encoding="utf-8")
    iodata.DATABASES["people"] = iodata.DATABASES["people"].iloc[:2]
    iodata.mark_dirty("people")

    failures = iodata.save_json_files(out=capture)

    assert failures == []
    assert iodata.DIRTY == set()
    after = json.loads((data_dir / "people.json").read_text(encoding="utf-8"))
    assert len(after) == 2
    # The table that was not dirty is untouched, byte for byte.
    assert (data_dir / "codes.json").read_text(encoding="utf-8") == before


def test_save_leaves_no_temporary_files(data_dir, capture):
    iodata.load_json_files(str(data_dir), out=capture)
    iodata.mark_dirty("people")
    iodata.save_json_files(out=capture)

    assert not list(data_dir.glob("*.tmp"))


def test_save_reports_unknown_tables(capture):
    failures = iodata.save_json_files(tables=["ghost"], out=capture)
    assert failures == [("ghost", "table is not loaded")]


def test_round_trip(data_dir, capture):
    iodata.load_json_files(str(data_dir), out=capture)
    iodata.DATABASES["people"] = iodata.DATABASES["people"][["id", "name"]]
    iodata.mark_dirty("people")
    iodata.save_json_files(out=capture)

    iodata.DATABASES.clear()
    iodata.load_json_files(str(data_dir), out=capture)

    assert list(iodata.DATABASES["people"].columns) == ["id", "name"]
    assert len(iodata.DATABASES["people"]) == 6


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


def test_resolve_table_is_case_insensitive(people):
    assert iodata.resolve_table("PEOPLE") == "people"


def test_resolve_table_reports_missing_tables(people):
    with pytest.raises(qp.QueryError, match="loaded tables: people"):
        iodata.resolve_table("nope")


def test_resolve_table_prefers_an_exact_name(people):
    iodata.DATABASES["People"] = people.copy()
    assert iodata.resolve_table("people") == "people"
    assert iodata.resolve_table("People") == "People"


def test_resolve_table_refuses_ambiguous_names(people):
    iodata.DATABASES["People"] = people.copy()
    with pytest.raises(qp.QueryError, match="ambiguous"):
        iodata.resolve_table("PEOPLE")


def test_show_tables_lists_row_counts_and_changes(people, capture):
    iodata.mark_dirty("people")
    names = iodata.show_tables(out=capture)

    assert names == ["people"]
    assert " - people (6 rows) *" in capture.text


def test_show_tables_without_tables(capture):
    assert iodata.show_tables(out=capture) == []
    assert "(no tables loaded)" in capture.text


def test_describe_table(people, capture):
    summary = iodata.describe_table("people", out=capture)

    assert list(summary["column"]) == ["id", "name", "age", "city", "score", "note"]
    row = summary.set_index("column")
    assert row.loc["age", "null"] == 1
    assert row.loc["name", "null"] == 0
    assert row.loc["name", "example"] == "Alice"
    assert "people (6 rows, 6 columns)" in capture.text


def test_describe_unknown_table(people, capture):
    with pytest.raises(qp.QueryError, match="table 'nope' not found"):
        iodata.describe_table("nope", out=capture)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["../escape.json", "/etc/passwd.json", "sub/out.json", "out.txt", "", ".."],
)
def test_safe_export_path_rejects_paths_outside_the_data_directory(data_dir, name):
    with pytest.raises(qp.QueryError):
        iodata.safe_export_path(name, directory=str(data_dir))


def test_safe_export_path_keeps_plain_names(data_dir):
    path = iodata.safe_export_path("filtered.json", directory=str(data_dir))
    assert os.path.dirname(path) == os.path.realpath(data_dir)


def test_export_writes_the_last_result(data_dir, capture):
    iodata.set_data_dir(str(data_dir))
    iodata.LAST_RESULT = pd.DataFrame(PEOPLE[:2])

    path = iodata.execute_export_last("EXPORT LAST TO 'out.json'", out=capture)

    assert path is not None
    written = json.loads((data_dir / "out.json").read_text(encoding="utf-8"))
    assert len(written) == 2
    assert "Exported 2 rows" in capture.text


def test_export_requires_a_previous_select(data_dir):
    iodata.set_data_dir(str(data_dir))
    with pytest.raises(qp.QueryError, match="no previous result"):
        iodata.execute_export_last("EXPORT LAST TO 'out.json'", out=lambda *_: None)


def test_export_refuses_to_overwrite_without_a_prompt(data_dir):
    iodata.set_data_dir(str(data_dir))
    iodata.LAST_RESULT = pd.DataFrame(PEOPLE[:1])
    (data_dir / "out.json").write_text("[]", encoding="utf-8")

    with pytest.raises(qp.QueryError, match="already exists"):
        iodata.execute_export_last("EXPORT LAST TO 'out.json'", out=lambda *_: None)


def test_export_can_be_cancelled(data_dir, capture):
    iodata.set_data_dir(str(data_dir))
    iodata.LAST_RESULT = pd.DataFrame(PEOPLE[:1])
    (data_dir / "out.json").write_text("[]", encoding="utf-8")

    result = iodata.execute_export_last(
        "EXPORT LAST TO 'out.json'", confirm=lambda question: False, out=capture
    )

    assert result is None
    assert json.loads((data_dir / "out.json").read_text(encoding="utf-8")) == []
    assert "[INFO] Export cancelled" in capture.text


def test_export_can_overwrite_after_confirmation(data_dir, capture):
    iodata.set_data_dir(str(data_dir))
    iodata.LAST_RESULT = pd.DataFrame(PEOPLE[:3])
    (data_dir / "out.json").write_text("[]", encoding="utf-8")

    path = iodata.execute_export_last(
        "EXPORT LAST TO 'out.json'", confirm=lambda question: True, out=capture
    )

    assert path is not None
    assert len(json.loads((data_dir / "out.json").read_text(encoding="utf-8"))) == 3


def test_export_overwrite_keyword_skips_the_prompt(data_dir):
    iodata.set_data_dir(str(data_dir))
    iodata.LAST_RESULT = pd.DataFrame(PEOPLE[:1])
    (data_dir / "out.json").write_text("[]", encoding="utf-8")

    def refuse(question):  # pragma: no cover - must not be called
        raise AssertionError("OVERWRITE should not ask")

    path = iodata.execute_export_last(
        "EXPORT LAST TO 'out.json' OVERWRITE", confirm=refuse, out=lambda *_: None
    )
    assert path is not None


def test_export_through_a_select(data_dir, capture):
    iodata.set_data_dir(str(data_dir))
    iodata.load_json_files(str(data_dir), out=lambda *_: None)

    cmds.execute_select("SELECT name FROM people WHERE id < 3", out=capture)
    path = iodata.execute_export_last("EXPORT LAST TO 'first_two.json'", out=capture)

    assert path is not None
    rows = json.loads((data_dir / "first_two.json").read_text(encoding="utf-8"))
    assert [row["name"] for row in rows] == ["Alice", "Bob"]
