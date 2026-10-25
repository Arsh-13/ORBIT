"""Tests for the HTTP API, including attempts to reach files outside the sandbox."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from orbit.api import create_app
from orbit.config import SAMPLE_WORKSPACE


def test_health(client: TestClient):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_scan_whole_workspace(client: TestClient, workspace: Path):
    response = client.get("/api/scan")
    assert response.status_code == 200
    body = response.json()
    assert body["root"] == str(workspace.resolve())
    assert body["summary"]["total_files"] == 9
    assert body["summary"]["duplicate_groups"] == 2
    first = body["files"][0]
    for key in ("name", "extension", "size_bytes", "modified_at", "absolute_path", "sha256", "duplicate_group"):
        assert key in first


def test_scan_subfolder(client: TestClient):
    response = client.get("/api/scan", params={"folder": "copies"})
    assert response.status_code == 200
    names = {f["name"] for f in response.json()["files"]}
    assert names == {"report (1).txt", "IMG_0001.jpg"}


@pytest.mark.parametrize("evil", ["..", "../outside", "copies/../../outside", "/etc", "/Users", "~/Downloads"])
def test_path_traversal_is_rejected(client: TestClient, evil: str):
    response = client.get("/api/scan", params={"folder": evil})
    assert response.status_code == 400
    assert "secret" not in response.text.lower()


def test_url_encoded_traversal_is_rejected(client: TestClient):
    response = client.get("/api/scan?folder=%2e%2e%2f%2e%2e")
    assert response.status_code == 400


def test_symlink_escape_via_api_is_rejected(client: TestClient, workspace: Path, outside: Path):
    os.symlink(outside, workspace / "escape")
    response = client.get("/api/scan", params={"folder": "escape"})
    assert response.status_code == 400


def test_missing_subfolder_returns_404(client: TestClient):
    response = client.get("/api/scan", params={"folder": "does_not_exist"})
    assert response.status_code == 404


def test_scanning_a_file_returns_404(client: TestClient):
    response = client.get("/api/scan", params={"folder": "notes.md"})
    assert response.status_code == 404


def test_overlong_folder_param_is_rejected(client: TestClient):
    response = client.get("/api/scan", params={"folder": "a" * 1000})
    assert response.status_code == 422


def test_missing_sandbox_returns_503(tmp_path: Path):
    app = create_app(sample_root=tmp_path / "gone", allowed_hosts=["testserver"])
    response = TestClient(app).get("/api/scan")
    assert response.status_code == 503


def test_foreign_host_header_is_rejected(workspace: Path):
    # The real app only answers to localhost / 127.0.0.1.
    app = create_app(sample_root=workspace)
    response = TestClient(app, base_url="http://evil.example.com").get("/api/health")
    assert response.status_code == 400
    ok = TestClient(app, base_url="http://127.0.0.1:8000").get("/api/health")
    assert ok.status_code == 200


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_no_write_methods_exist(client: TestClient, method: str):
    response = getattr(client, method)("/api/scan")
    assert response.status_code == 405


def test_real_sample_workspace_has_expected_duplicates():
    """Integration check against the committed synthetic sample files."""
    app = create_app(sample_root=SAMPLE_WORKSPACE, allowed_hosts=["testserver"])
    body = TestClient(app).get("/api/scan").json()
    assert body["summary"]["total_files"] >= 10
    assert body["summary"]["duplicate_groups"] == 3
    assert body["errors"] == []
