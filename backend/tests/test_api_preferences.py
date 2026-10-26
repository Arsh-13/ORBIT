"""API tests for recommendations and the preference endpoints (which only write ORBIT's own database)."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from orbit.api import create_app


def sha_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recommendation_for(client: TestClient, sha: str) -> dict:
    body = client.get("/api/scan").json()
    return next(r for r in body["recommendations"] if r["sha256"] == sha)


def test_scan_includes_a_recommendation_per_group(client: TestClient):
    body = client.get("/api/scan").json()
    assert len(body["recommendations"]) == len(body["duplicate_groups"]) == 2
    assert body["keep_rules"] == {"preferred_folders": ["documents"], "avoid_folders": ["downloads"]}
    for r in body["recommendations"]:
        assert r["preferred_path"] in r["copies"][0]["relative_path"]
        assert r["reasons"]
        assert r["reclaimable_bytes"] > 0


def test_choose_a_preferred_copy_then_reset(client: TestClient, workspace: Path):
    sha = sha_of(workspace / "report.txt")
    assert recommendation_for(client, sha)["source"] == "rules"

    response = client.put("/api/preferences/choices", json={"sha256": sha, "relative_path": "copies/report (1).txt"})
    assert response.status_code == 200
    assert response.json() == {"sha256": sha, "relative_path": "copies/report (1).txt"}

    r = recommendation_for(client, sha)
    assert r["source"] == "user"
    assert r["preferred_path"] == "copies/report (1).txt"
    assert r["suggested_path"] != "copies/report (1).txt"

    assert client.get("/api/preferences").json()["choices"] == [{"sha256": sha, "relative_path": "copies/report (1).txt"}]

    assert client.delete(f"/api/preferences/choices/{sha}").status_code == 204
    assert recommendation_for(client, sha)["source"] == "rules"


def test_choice_path_is_normalised(client: TestClient, workspace: Path):
    sha = sha_of(workspace / "report.txt")
    response = client.put("/api/preferences/choices", json={"sha256": sha, "relative_path": "copies/../report.txt"})
    assert response.status_code == 200
    assert response.json()["relative_path"] == "report.txt"


@pytest.mark.parametrize("evil", ["../outside/secret.txt", "/etc/passwd", "~/Downloads/x.pdf", "copies/../../outside/secret.txt"])
def test_choice_rejects_paths_outside_the_workspace(client: TestClient, workspace: Path, outside: Path, evil: str):
    sha = sha_of(outside / "secret.txt")
    response = client.put("/api/preferences/choices", json={"sha256": sha, "relative_path": evil})
    assert response.status_code == 400


def test_choice_rejects_symlink_escape(client: TestClient, workspace: Path, outside: Path):
    os.symlink(outside / "secret.txt", workspace / "link.txt")
    response = client.put(
        "/api/preferences/choices", json={"sha256": sha_of(outside / "secret.txt"), "relative_path": "link.txt"}
    )
    assert response.status_code == 400


def test_choice_rejects_file_from_a_different_group(client: TestClient, workspace: Path):
    sha = sha_of(workspace / "report.txt")
    response = client.put("/api/preferences/choices", json={"sha256": sha, "relative_path": "photo.jpg"})
    assert response.status_code == 409


def test_choice_rejects_missing_file_and_folders(client: TestClient, workspace: Path):
    sha = sha_of(workspace / "report.txt")
    assert client.put("/api/preferences/choices", json={"sha256": sha, "relative_path": "nope.txt"}).status_code == 404
    assert client.put("/api/preferences/choices", json={"sha256": sha, "relative_path": "copies"}).status_code == 404


@pytest.mark.parametrize("bad_sha", ["abc", "G" * 64, "A" * 64, ""])
def test_choice_rejects_malformed_hashes(client: TestClient, bad_sha: str):
    response = client.put("/api/preferences/choices", json={"sha256": bad_sha, "relative_path": "report.txt"})
    assert response.status_code == 422


def test_delete_rejects_malformed_hash(client: TestClient):
    assert client.delete("/api/preferences/choices/not-a-hash").status_code == 422


def test_update_rules_changes_the_recommendation(client: TestClient, workspace: Path):
    sha = sha_of(workspace / "report.txt")
    response = client.put("/api/preferences/rules", json={"preferred_folders": ["Archive"], "avoid_folders": []})
    assert response.status_code == 200
    assert response.json() == {"preferred_folders": ["archive"], "avoid_folders": []}
    assert recommendation_for(client, sha)["preferred_path"] == "archive/old_name.TXT"


@pytest.mark.parametrize(
    "body",
    [
        {"preferred_folders": ["../etc"], "avoid_folders": []},
        {"preferred_folders": ["/Users"], "avoid_folders": []},
        {"preferred_folders": ["notes"], "avoid_folders": ["notes"]},
    ],
)
def test_invalid_rules_are_rejected(client: TestClient, body: dict):
    assert client.put("/api/preferences/rules", json=body).status_code == 400


def test_cross_site_requests_are_blocked(client: TestClient, workspace: Path):
    sha = sha_of(workspace / "report.txt")
    evil = {"Origin": "https://evil.example.com"}
    body = {"sha256": sha, "relative_path": "report.txt"}
    assert client.put("/api/preferences/choices", json=body, headers=evil).status_code == 403
    assert client.put("/api/preferences/rules", json={"preferred_folders": []}, headers=evil).status_code == 403
    assert client.delete(f"/api/preferences/choices/{sha}", headers=evil).status_code == 403
    # Our own dashboard's origin is fine.
    ok = client.put("/api/preferences/choices", json=body, headers={"Origin": "http://127.0.0.1:5173"})
    assert ok.status_code == 200


def test_non_json_bodies_are_not_accepted(client: TestClient, workspace: Path):
    # An HTML form on another site can only send "simple" content types like text/plain.
    sha = sha_of(workspace / "report.txt")
    response = client.put(
        "/api/preferences/choices",
        content=f'{{"sha256": "{sha}", "relative_path": "report.txt"}}',
        headers={"Content-Type": "text/plain"},
    )
    assert response.status_code == 422


def test_preference_writes_never_touch_workspace_files(client: TestClient, workspace: Path):
    def snapshot():
        return {
            str(p): (p.lstat().st_size, p.lstat().st_mtime_ns, p.read_bytes() if p.is_file() else None)
            for p in sorted(workspace.rglob("*"))
        }

    before = snapshot()
    sha = sha_of(workspace / "report.txt")
    client.put("/api/preferences/choices", json={"sha256": sha, "relative_path": "copies/report (1).txt"})
    client.put("/api/preferences/rules", json={"preferred_folders": ["copies"], "avoid_folders": []})
    client.get("/api/scan")
    client.delete(f"/api/preferences/choices/{sha}")
    assert snapshot() == before


def test_subfolder_scan_translates_saved_choices(client: TestClient, workspace: Path):
    sha = sha_of(workspace / "photo.jpg")
    client.put("/api/preferences/choices", json={"sha256": sha, "relative_path": "copies/IMG_0001.jpg"})
    # Only one copy is inside "copies", so there's no group there, and the scan must not crash.
    body = client.get("/api/scan", params={"folder": "copies"}).json()
    assert body["recommendations"] == []


def test_database_inside_workspace_is_refused(workspace: Path):
    with pytest.raises(ValueError):
        create_app(sample_root=workspace, db_path=workspace / "orbit.sqlite3")
