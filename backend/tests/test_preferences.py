"""Tests for preference validation and the SQLite preference store."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from orbit import config
from orbit.preferences import KeepRules, PreferenceError, PreferenceStore, normalize_folder, normalize_rules


@pytest.mark.parametrize(
    "raw, expected",
    [("documents", "documents"), (" Documents/School/ ", "documents/school"), ("a//b", "a/b")],
)
def test_folder_names_are_normalised(raw: str, expected: str):
    assert normalize_folder(raw) == expected


@pytest.mark.parametrize("bad", ["", "   ", "..", "../outside", "a/../../b", "/Users", "~/Downloads", ".hidden", "a\x00b", "a\\b", "x" * 101])
def test_bad_folder_names_are_rejected(bad: str):
    with pytest.raises(PreferenceError):
        normalize_folder(bad)


def test_rules_are_deduplicated():
    rules = normalize_rules(["Documents", "documents/", "notes"], ["downloads"])
    assert rules.preferred_folders == ["documents", "notes"]


def test_folder_cannot_be_preferred_and_avoided():
    with pytest.raises(PreferenceError):
        normalize_rules(["downloads"], ["Downloads"])


def test_too_many_folders_rejected():
    with pytest.raises(PreferenceError):
        normalize_rules([f"f{i}" for i in range(21)], [])


def test_defaults_when_nothing_saved_and_reading_creates_no_file(tmp_path: Path):
    store = PreferenceStore(tmp_path / "orbit.sqlite3")
    assert store.get_rules() == KeepRules()
    assert store.get_choices() == {}
    assert not (tmp_path / "orbit.sqlite3").exists()


def test_rules_round_trip_and_persist(tmp_path: Path):
    db = tmp_path / "orbit.sqlite3"
    PreferenceStore(db).save_rules(KeepRules(["school"], ["inbox"]))
    assert PreferenceStore(db).get_rules() == KeepRules(["school"], ["inbox"])  # new instance, same file


def test_choices_set_overwrite_clear(tmp_path: Path):
    store = PreferenceStore(tmp_path / "orbit.sqlite3")
    store.set_choice("a" * 64, "notes/a.txt")
    store.set_choice("a" * 64, "docs/a.txt")  # overwrite
    store.set_choice("b" * 64, "x.txt")
    assert store.get_choices() == {"a" * 64: "docs/a.txt", "b" * 64: "x.txt"}
    assert store.clear_choice("a" * 64) is True
    assert store.clear_choice("a" * 64) is False
    assert store.get_choices() == {"b" * 64: "x.txt"}


def test_damaged_rules_fall_back_to_defaults(tmp_path: Path):
    db = tmp_path / "orbit.sqlite3"
    store = PreferenceStore(db)
    store.save_rules(KeepRules())
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE settings SET value = '{not json' WHERE key = 'keep_rules'")
    assert store.get_rules() == KeepRules()


def test_real_database_lives_outside_the_scanned_workspace():
    assert not config.DB_PATH.resolve().is_relative_to(config.SAMPLE_WORKSPACE.resolve())


def test_tests_use_a_temporary_database(isolated_database: Path):
    # The autouse fixture redirects config.DB_PATH, so no test can write the real database.
    assert config.DB_PATH == isolated_database
    assert config.PROJECT_ROOT not in isolated_database.parents
