"""Shared fixtures for the SQLatmask test suite."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from sqlatmask import iodata
from sample_data import CODES, ORDERS, PEOPLE


class Capture:
    """Collect printed lines instead of sending them to stdout."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def __call__(self, message: str = "") -> None:
        self.lines.append(str(message))

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


@pytest.fixture(autouse=True)
def clean_state(tmp_path, monkeypatch):
    """Every test starts with an empty in-memory database and its own directory."""
    monkeypatch.setattr(iodata, "DATABASES", {})
    monkeypatch.setattr(iodata, "LAST_RESULT", None)
    monkeypatch.setattr(iodata, "DIRTY", set())
    monkeypatch.setattr(iodata, "DATA", str(tmp_path / "data"))
    yield


@pytest.fixture
def people():
    frame = pd.DataFrame(PEOPLE)
    iodata.DATABASES["people"] = frame
    return frame


@pytest.fixture
def codes():
    frame = pd.DataFrame(CODES)
    iodata.DATABASES["codes"] = frame
    return frame


@pytest.fixture
def orders():
    frame = pd.DataFrame(ORDERS)
    iodata.DATABASES["orders"] = frame
    return frame


@pytest.fixture
def capture():
    return Capture()


@pytest.fixture
def data_dir(tmp_path):
    """A temporary data directory holding people.json."""
    directory = tmp_path / "tables"
    directory.mkdir()
    (directory / "people.json").write_text(json.dumps(PEOPLE), encoding="utf-8")
    iodata.set_data_dir(str(directory))
    return directory
