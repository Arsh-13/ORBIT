"""Tests for the read-only scanner: metadata, hashing, symlinks, errors, and read-only behaviour."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime
from pathlib import Path

import pytest

from orbit.scanner import ScanRootError, hash_file, scan_directory

from .conftest import is_root_user, write


def by_path(result):
    return {f.relative_path: f for f in result.files}


def test_metadata_is_collected(workspace: Path):
    result = scan_directory(workspace)
    files = by_path(result)

    rec = files["archive/old_name.TXT"]
    assert rec.name == "old_name.TXT"
    assert rec.extension == ".txt"  # normalised to lower case
    assert rec.size_bytes == (workspace / "archive" / "old_name.TXT").stat().st_size
    assert rec.absolute_path == str((workspace / "archive" / "old_name.TXT").resolve())
    assert Path(rec.absolute_path).is_absolute()
    assert datetime.fromisoformat(rec.modified_at).tzinfo is not None
    assert result.errors == []


def test_all_regular_files_found_recursively(workspace: Path):
    result = scan_directory(workspace)
    assert sorted(by_path(result)) == sorted(
        [
            "archive/old_name.TXT",
            "copies/IMG_0001.jpg",
            "copies/report (1).txt",
            "empty1.txt",
            "empty2.txt",
            "notes.md",
            "photo.jpg",
            "report.txt",
            "same_size_different.txt",
        ]
    )


def test_file_without_extension(workspace: Path):
    write(workspace / "README", "hello")
    assert by_path(scan_directory(workspace))["README"].extension == ""


def test_sha256_matches_hashlib(workspace: Path):
    data = (workspace / "photo.jpg").read_bytes()
    assert by_path(scan_directory(workspace))["photo.jpg"].sha256 == hashlib.sha256(data).hexdigest()


def test_streaming_hash_with_tiny_chunks_matches_one_shot_hash(tmp_path: Path):
    # 1 MB+ of data read 7 bytes at a time must give the same hash as reading it all at once.
    data = os.urandom(1_000_003)
    path = write(tmp_path / "big.bin", data)
    digest, info = hash_file(path, chunk_size=7)
    assert digest == hashlib.sha256(data).hexdigest()
    assert info.st_size == len(data)


def test_hash_file_refuses_symlinks(workspace: Path, outside: Path):
    link = workspace / "link.txt"
    os.symlink(outside / "secret.txt", link)
    with pytest.raises(OSError):
        hash_file(link)


def test_symlinked_file_is_skipped_not_followed(workspace: Path, outside: Path):
    os.symlink(outside / "secret.txt", workspace / "secret_link.txt")
    result = scan_directory(workspace)
    assert "secret_link.txt" not in by_path(result)
    assert any(i.relative_path == "secret_link.txt" and "Symlink" in i.reason for i in result.skipped)


def test_symlinked_directory_is_not_entered(workspace: Path, outside: Path):
    os.symlink(outside, workspace / "escape_dir")
    result = scan_directory(workspace)
    assert not any("secret" in f.name for f in result.files)
    assert all(str(outside) not in f.absolute_path for f in result.files)
    assert any(i.relative_path == "escape_dir" for i in result.skipped)


def test_hidden_files_are_ignored(workspace: Path):
    write(workspace / ".DS_Store", "junk")
    write(workspace / ".hidden_dir" / "inside.txt", "junk")
    names = by_path(scan_directory(workspace))
    assert ".DS_Store" not in names
    assert ".hidden_dir/inside.txt" not in names


def test_fifo_is_skipped_without_hanging(workspace: Path):
    os.mkfifo(workspace / "a_pipe")
    result = scan_directory(workspace)
    assert any(i.relative_path == "a_pipe" for i in result.skipped)


@pytest.mark.skipif(is_root_user(), reason="root can read files regardless of permissions")
def test_unreadable_file_is_reported_and_scan_continues(workspace: Path, restore_permissions):
    locked = workspace / "locked.txt"
    write(locked, "no access")
    os.chmod(locked, 0o000)
    restore_permissions.append(locked)

    result = scan_directory(workspace)
    assert any(e.relative_path == "locked.txt" and e.reason == "Permission denied" for e in result.errors)
    assert "report.txt" in by_path(result)  # other files still scanned


@pytest.mark.skipif(is_root_user(), reason="root can read folders regardless of permissions")
def test_unreadable_folder_is_reported_and_scan_continues(workspace: Path, restore_permissions):
    locked = workspace / "locked_dir"
    write(locked / "inside.txt", "hidden")
    os.chmod(locked, 0o000)
    restore_permissions.append(locked)

    result = scan_directory(workspace)
    assert any(e.relative_path == "locked_dir" for e in result.errors)
    assert "report.txt" in by_path(result)


def test_missing_directory_raises(tmp_path: Path):
    with pytest.raises(ScanRootError):
        scan_directory(tmp_path / "nope")


def test_file_instead_of_directory_raises(workspace: Path):
    with pytest.raises(ScanRootError):
        scan_directory(workspace / "notes.md")


def test_symlink_as_scan_root_raises(tmp_path: Path, outside: Path):
    link = tmp_path / "root_link"
    os.symlink(outside, link)
    with pytest.raises(ScanRootError):
        scan_directory(link)


def test_max_files_limit_truncates(workspace: Path):
    result = scan_directory(workspace, max_files=3)
    assert len(result.files) == 3
    assert result.truncated is True


def test_scan_is_read_only(workspace: Path):
    """Nothing in the folder may change: same names, bytes, sizes, and mtimes before and after."""

    def snapshot():
        snap = {}
        for path in sorted(workspace.rglob("*")):
            st = path.lstat()
            snap[str(path)] = (st.st_size, st.st_mtime_ns, path.read_bytes() if path.is_file() else None)
        return snap

    before = snapshot()
    scan_directory(workspace)
    scan_directory(workspace)
    assert snapshot() == before
