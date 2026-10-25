"""Tests for exact duplicate detection."""

from __future__ import annotations

from pathlib import Path

from orbit.duplicates import build_report, find_duplicate_groups
from orbit.scanner import scan_directory

from .conftest import write


def groups_as_sets(workspace: Path):
    groups = find_duplicate_groups(scan_directory(workspace).files)
    return [set(g.relative_paths) for g in groups], groups


def test_identical_files_with_different_names_are_grouped(workspace: Path):
    sets, _ = groups_as_sets(workspace)
    assert {"report.txt", "copies/report (1).txt", "archive/old_name.TXT"} in sets
    assert {"photo.jpg", "copies/IMG_0001.jpg"} in sets
    assert len(sets) == 2


def test_same_size_but_different_content_is_not_a_duplicate(workspace: Path):
    sets, _ = groups_as_sets(workspace)
    assert all("same_size_different.txt" not in s for s in sets)


def test_unique_file_is_not_a_duplicate(workspace: Path):
    sets, _ = groups_as_sets(workspace)
    assert all("notes.md" not in s for s in sets)


def test_empty_files_are_not_reported_as_duplicates(workspace: Path):
    sets, _ = groups_as_sets(workspace)
    assert all("empty1.txt" not in s and "empty2.txt" not in s for s in sets)


def test_one_byte_difference_breaks_the_match(tmp_path: Path):
    write(tmp_path / "a.bin", b"A" * 1000)
    write(tmp_path / "b.bin", b"A" * 999 + b"B")
    sets, _ = groups_as_sets(tmp_path)
    assert sets == []


def test_group_numbers_and_wasted_space(workspace: Path):
    _, groups = groups_as_sets(workspace)
    report_size = (workspace / "report.txt").stat().st_size
    photo_size = (workspace / "photo.jpg").stat().st_size

    by_count = {g.file_count: g for g in groups}
    assert by_count[3].wasted_bytes == report_size * 2
    assert by_count[2].wasted_bytes == photo_size * 1

    # Biggest waste first, numbered from 1.
    assert [g.group_id for g in groups] == [1, 2]
    assert groups[0].wasted_bytes >= groups[1].wasted_bytes


def test_report_summary_and_file_tags(workspace: Path):
    report = build_report(scan_directory(workspace))
    s = report.summary
    assert s.total_files == 9
    assert s.duplicate_groups == 2
    assert s.duplicate_files == 5
    assert s.redundant_copies == 3
    assert s.total_bytes == sum(f.size_bytes for f in report.files)
    assert s.wasted_bytes == sum(g.wasted_bytes for g in report.duplicate_groups)

    tags = {f.relative_path: f.duplicate_group for f in report.files}
    assert tags["report.txt"] == tags["copies/report (1).txt"] == tags["archive/old_name.TXT"] is not None
    assert tags["photo.jpg"] == tags["copies/IMG_0001.jpg"] is not None
    assert tags["report.txt"] != tags["photo.jpg"]
    assert tags["notes.md"] is None
    assert tags["empty1.txt"] is None
