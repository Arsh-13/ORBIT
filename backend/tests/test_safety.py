"""Tests for path-traversal and symlink-escape protection."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from orbit.config import PROJECT_ROOT, SAMPLE_WORKSPACE
from orbit.safety import PathSafetyError, resolve_inside


def test_empty_path_is_the_root(workspace: Path):
    assert resolve_inside(workspace, "") == workspace.resolve()


def test_subfolder_is_allowed(workspace: Path):
    assert resolve_inside(workspace, "copies") == (workspace / "copies").resolve()


def test_dotdot_that_stays_inside_is_allowed(workspace: Path):
    assert resolve_inside(workspace, "copies/../archive") == (workspace / "archive").resolve()


@pytest.mark.parametrize(
    "evil",
    [
        "..",
        "../",
        "../outside",
        "copies/../../outside",
        "copies/../../../../../../etc",
        "/etc",
        "/Users",
        "~",
        "~/Downloads",
        "ok\x00/../..",
    ],
)
def test_escapes_are_rejected(workspace: Path, evil: str):
    with pytest.raises(PathSafetyError):
        resolve_inside(workspace, evil)


def test_symlink_pointing_outside_is_rejected(workspace: Path, outside: Path):
    os.symlink(outside, workspace / "sneaky_link")
    with pytest.raises(PathSafetyError):
        resolve_inside(workspace, "sneaky_link")


def test_symlink_pointing_inside_is_allowed(workspace: Path):
    os.symlink(workspace / "copies", workspace / "inner_link")
    assert resolve_inside(workspace, "inner_link") == (workspace / "copies").resolve()


def test_missing_root_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        resolve_inside(tmp_path / "does_not_exist", "")


def test_default_sandbox_lives_inside_the_project():
    # Guards against someone pointing the default at a real personal folder.
    assert SAMPLE_WORKSPACE.resolve().is_relative_to(PROJECT_ROOT)
    assert SAMPLE_WORKSPACE.name == "sample_workspace"
    for personal in ("Downloads", "Documents", "Desktop"):
        assert SAMPLE_WORKSPACE.resolve() != (Path.home() / personal).resolve()
