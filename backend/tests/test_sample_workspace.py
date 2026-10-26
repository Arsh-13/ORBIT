"""Integration tests against the committed synthetic sample_workspace (with default keep rules)."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from orbit.api import create_app
from orbit.config import SAMPLE_WORKSPACE

PDF = SAMPLE_WORKSPACE / "downloads" / "course_reader.pdf"
PDF_COPY = SAMPLE_WORKSPACE / "downloads" / "course_reader (1).pdf"
PDF_ANNOTATED_APPENDED = SAMPLE_WORKSPACE / "documents" / "course_reader_annotated.pdf"
PDF_ANNOTATED_REWRITTEN = SAMPLE_WORKSPACE / "archive" / "course_reader_marked_up.pdf"
PDF_SECOND_EDITION = SAMPLE_WORKSPACE / "downloads" / "course_reader_2nd_edition.pdf"


@pytest.fixture(scope="module")
def body(tmp_path_factory) -> dict:
    db = tmp_path_factory.mktemp("db") / "orbit.sqlite3"
    app = create_app(sample_root=SAMPLE_WORKSPACE, allowed_hosts=["testserver"], db_path=db)
    return TestClient(app).get("/api/scan").json()


def groups(body: dict) -> list[set[str]]:
    return [set(g["relative_paths"]) for g in body["duplicate_groups"]]


def test_expected_exact_duplicate_groups(body: dict):
    assert sorted(groups(body), key=sorted) == sorted(
        [
            {"downloads/invoice_1042.pdf", "downloads/invoice_1042 (1).pdf", "downloads/scan0001.pdf"},
            {"downloads/Lecture Notes - Week 1.txt", "notes/lecture_01.txt"},
            {"images/IMG_4821.PNG", "images/sunset.png"},
            {"downloads/course_reader.pdf", "downloads/course_reader (1).pdf"},
            {"downloads/meeting_notes.md", "notes/meeting_notes (1).md"},
            {"archive/plan.md", "projects/plan.md"},
        ],
        key=sorted,
    )


def test_annotated_and_newer_pdfs_are_not_exact_duplicates(body: dict):
    grouped = set().union(*groups(body))
    for path in ("documents/course_reader_annotated.pdf", "archive/course_reader_marked_up.pdf", "downloads/course_reader_2nd_edition.pdf"):
        assert path not in grouped


@pytest.mark.parametrize(
    "member, preferred, confidence",
    [
        ("downloads/scan0001.pdf", "downloads/invoice_1042.pdf", "medium"),
        ("notes/lecture_01.txt", "notes/lecture_01.txt", "high"),
        ("images/sunset.png", "images/sunset.png", "medium"),
        ("downloads/course_reader.pdf", "downloads/course_reader.pdf", "medium"),
        ("notes/meeting_notes (1).md", "notes/meeting_notes (1).md", "high"),
        ("projects/plan.md", "archive/plan.md", "low"),
    ],
)
def test_sample_recommendations(body: dict, member: str, preferred: str, confidence: str):
    rec = next(r for r in body["recommendations"] if member in [c["relative_path"] for c in r["copies"]])
    assert rec["preferred_path"] == preferred
    assert rec["confidence"] == confidence


def test_conflict_sample_reports_a_caveat(body: dict):
    rec = next(r for r in body["recommendations"] if r["preferred_path"] == "notes/meeting_notes (1).md")
    assert any("cleaner name" in c for c in rec["caveats"])


# --- Shape of the synthetic PDF fixtures (simple byte checks, no PDF library needed) ---


def test_pdf_fixture_shapes():
    original = PDF.read_bytes()
    appended = PDF_ANNOTATED_APPENDED.read_bytes()
    rewritten = PDF_ANNOTATED_REWRITTEN.read_bytes()
    second = PDF_SECOND_EDITION.read_bytes()

    assert PDF_COPY.read_bytes() == original
    # Incremental save: original bytes are an exact prefix, followed by an update pointing back (/Prev).
    assert appended.startswith(original) and b"/Prev" in appended[len(original):]
    # Full rewrite: different bytes, not a prefix.
    assert not rewritten.startswith(original)

    for annotated in (appended, rewritten):
        assert b"/Subtype /Highlight" in annotated and b"/Subtype /Text" in annotated
    for plain in (original, second):
        assert b"/Subtype /Highlight" not in plain
        assert b"/Subtype /Link" in plain  # publisher links exist but are NOT user annotations


def _ids(data: bytes) -> list[tuple[bytes, bytes]]:
    return re.findall(rb"/ID \[<([0-9a-f]+)> <([0-9a-f]+)>\]", data)


def test_pdf_fixture_ids():
    original_id = _ids(PDF.read_bytes())[-1]
    assert original_id[0] == original_id[1]
    for annotated in (PDF_ANNOTATED_APPENDED, PDF_ANNOTATED_REWRITTEN):
        permanent, changing = _ids(annotated.read_bytes())[-1]
        assert permanent == original_id[0]  # same document...
        assert changing != original_id[1]  # ...different revision
    assert _ids(PDF_SECOND_EDITION.read_bytes())[-1][0] != original_id[0]  # a new edition gets a new ID
