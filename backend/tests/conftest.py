"""Shared pytest fixtures. Every test works inside pytest's temporary folders, never real user files."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from orbit.api import create_app


def write(path: Path, content: bytes | str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode() if isinstance(content, str) else content)
    return path


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A small sandbox with known duplicates:

    group A (3 copies): report.txt, copies/report (1).txt, archive/old_name.TXT
    group B (2 copies): photo.jpg, copies/IMG_0001.jpg
    unique:             notes.md, same_size_different.txt
    empty (ignored):    empty1.txt, empty2.txt
    """
    root = tmp_path / "workspace"
    root.mkdir()
    report = "Quarterly report: synthetic content.\n" * 10
    write(root / "report.txt", report)
    write(root / "copies" / "report (1).txt", report)
    write(root / "archive" / "old_name.TXT", report)
    write(root / "photo.jpg", bytes(range(256)) * 4)
    write(root / "copies" / "IMG_0001.jpg", bytes(range(256)) * 4)
    write(root / "notes.md", "# Notes\nunique\n")
    # Same length as report.txt but different bytes -> must NOT be a duplicate.
    write(root / "same_size_different.txt", "X" * len(report))
    write(root / "empty1.txt", b"")
    write(root / "empty2.txt", b"")
    return root


@pytest.fixture
def outside(tmp_path: Path) -> Path:
    """A folder OUTSIDE the sandbox holding a 'secret'. Nothing should ever reach it."""
    secret_dir = tmp_path / "outside"
    write(secret_dir / "secret.txt", "TOP SECRET - must never be scanned")
    return secret_dir


@pytest.fixture
def client(workspace: Path) -> TestClient:
    app = create_app(sample_root=workspace, allowed_hosts=["testserver", "localhost", "127.0.0.1"])
    return TestClient(app)


@pytest.fixture
def restore_permissions():
    """Collect paths whose permissions a test removes, and restore them afterwards for cleanup."""
    changed: list[Path] = []
    yield changed
    for path in changed:
        os.chmod(path, 0o755)


def is_root_user() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0
