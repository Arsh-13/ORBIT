"""Create the synthetic files in sample_workspace/ (safe to re-run).

Every file is invented test data. This script writes ONLY inside the repository's
sample_workspace/ folder and refuses to run if that path looks wrong.

Usage (from the repository root):  python3 scripts/make_sample_workspace.py
"""

from __future__ import annotations

import hashlib
import os
import re
import struct
import zlib
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET = REPO_ROOT / "sample_workspace"


def tiny_pdf(text: str) -> bytes:
    """A minimal, valid one-page PDF showing `text`."""
    stream = f"BT /F1 18 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


def tiny_png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    """A small solid-colour PNG image."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


INVOICE = tiny_pdf("Invoice #1042 - Acme Example Co. - Total: $120.00")
LECTURE = (
    "Lecture 1 - Introduction to Data Structures\n"
    "- Arrays store items next to each other in memory.\n"
    "- Linked lists store items anywhere, connected by pointers.\n"
    "- Hash tables give near-constant-time lookups.\n"
)
SUNSET = tiny_png(48, 32, (240, 128, 64))


# ---------------------------------------------------------------------------
# Course-reader PDFs: one document in several versions, for annotation research.
#
# Object layout: 1 Catalog, 2 Pages, 3 Font, then per page i: page = 4+2i, content = 5+2i,
# then a Link annotation (a publisher's hyperlink, NOT a user mark), then user annotations.
# ---------------------------------------------------------------------------


def _pdf_str(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _page_num(i: int) -> int:
    return 4 + 2 * i


def _page_object(i: int, annot_refs: list[int]) -> bytes:
    annots = f" /Annots [{' '.join(f'{r} 0 R' for r in annot_refs)}]" if annot_refs else ""
    return (
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {5 + 2 * i} 0 R "
        f"/Resources << /Font << /F1 3 0 R >> >>{annots} >>"
    ).encode()


def _base_objects(pages: list[list[str]]) -> dict[int, bytes]:
    link = 4 + 2 * len(pages)
    kids = " ".join(f"{_page_num(i)} 0 R" for i in range(len(pages)))
    objs = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode(),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        link: b"<< /Type /Annot /Subtype /Link /Rect [72 60 320 76] /Border [0 0 0] "
        b"/A << /S /URI /URI (https://example.com/course-reader) >> >>",
    }
    for i, lines in enumerate(pages):
        objs[_page_num(i)] = _page_object(i, [link] if i == 0 else [])
        body = " Tj T* ".join(f"({_pdf_str(line)})" for line in lines)
        stream = f"BT /F1 12 Tf 16 TL 72 720 Td {body} Tj ET".encode()
        objs[5 + 2 * i] = b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream)
    return objs


def _file_id(seed: str) -> str:
    return hashlib.md5(seed.encode()).hexdigest()


def _trailer(size: int, ids: tuple[str, str], extra: str = "") -> bytes:
    return f"trailer\n<< /Size {size} /Root 1 0 R /ID [<{ids[0]}> <{ids[1]}>]{extra} >>\n".encode()


def _serialize(objs: dict[int, bytes], ids: tuple[str, str]) -> bytes:
    """Write a complete PDF file (header, objects, cross-reference table, trailer)."""
    out = bytearray(b"%PDF-1.7\n")
    offsets = {}
    for num in sorted(objs):
        offsets[num] = len(out)
        out += b"%d 0 obj\n%s\nendobj\n" % (num, objs[num])
    xref = len(out)
    size = max(objs) + 1
    out += b"xref\n0 %d\n0000000000 65535 f \n" % size
    out += b"".join(b"%010d 00000 n \n" % offsets[n] for n in range(1, size))
    out += _trailer(size, ids) + b"startxref\n%d\n%%%%EOF\n" % xref
    return bytes(out)


def _append_update(original: bytes, changed: dict[int, bytes], ids: tuple[str, str]) -> bytes:
    """Incremental update: keep every original byte and append only new/changed objects.

    This is how many PDF editors save annotations. The original file is an exact PREFIX of
    the annotated file, which is a very strong "same document" signal.
    """
    prev_xref = int(re.findall(rb"startxref\s+(\d+)", original)[-1])
    out = bytearray(original)
    offsets = {}
    for num in sorted(changed):
        offsets[num] = len(out)
        out += b"%d 0 obj\n%s\nendobj\n" % (num, changed[num])
    xref = len(out)
    # Starting with the object-0 entry (as many PDF writers do) keeps strict parsers happy.
    out += b"xref\n0 1\n0000000000 65535 f \n"
    out += b"".join(b"%d 1\n%010d 00000 n \n" % (n, offsets[n]) for n in sorted(changed))
    size = max(changed) + 1
    out += _trailer(size, ids, f" /Prev {prev_xref}") + b"startxref\n%d\n%%%%EOF\n" % xref
    return bytes(out)


def _highlight(x1: int, y1: int, x2: int, y2: int, note: str) -> bytes:
    return (
        f"<< /Type /Annot /Subtype /Highlight /Rect [{x1} {y1} {x2} {y2}] "
        f"/QuadPoints [{x1} {y2} {x2} {y2} {x1} {y1} {x2} {y1}] /C [1 0.85 0.2] /CA 0.5 "
        f"/T (Sample Student) /Contents ({_pdf_str(note)}) /M (D:20260210183000Z) /F 4 >>"
    ).encode()


def _sticky_note(x: int, y: int, note: str) -> bytes:
    return (
        f"<< /Type /Annot /Subtype /Text /Rect [{x} {y} {x + 20} {y + 20}] /Name /Comment /Open false "
        f"/T (Sample Student) /Contents ({_pdf_str(note)}) /M (D:20260210184500Z) /F 4 >>"
    ).encode()


def _with_user_annotations(pages: list[list[str]], user_annots: dict[int, list[bytes]]) -> dict[int, bytes]:
    """Return only the objects that change when a reader adds annotations."""
    link = 4 + 2 * len(pages)
    next_num = link + 1
    changed: dict[int, bytes] = {}
    for page_index, annots in user_annots.items():
        refs = []
        for annot in annots:
            changed[next_num] = annot
            refs.append(next_num)
            next_num += 1
        changed[_page_num(page_index)] = _page_object(page_index, ([link] if page_index == 0 else []) + refs)
    return changed


READER_ED1 = [
    [
        "Course Reader: Introduction to Data Structures",
        "Edition 1 - synthetic sample document for ORBIT",
        "",
        "Chapter 1: Arrays",
        "An array stores items next to each other in memory.",
        "Reading item i takes the same time for every i.",
    ],
    [
        "Chapter 2: Hash tables",
        "A hash table maps keys to values using a hash function.",
        "Average lookup time is constant.",
    ],
]
READER_ED2 = [
    [
        "Course Reader: Introduction to Data Structures",
        "Edition 2 - synthetic sample document for ORBIT",
        "",
        "Chapter 1: Arrays and dynamic arrays",
        "An array stores items next to each other in memory.",
        "Dynamic arrays grow by copying into a bigger block.",
    ],
    READER_ED1[1],
    ["Chapter 3: Trees", "A binary search tree keeps keys in sorted order."],
]
READER_ID = _file_id("course-reader-edition-1")  # permanent ID, shared by every version of edition 1
READER_ANNOTATIONS = {
    0: [_highlight(72, 640, 380, 654, "Key definition"), _sticky_note(500, 650, "Exam: know this!")],
    1: [_highlight(72, 702, 400, 716, "Compare with trees")],
}
_reader_objs = _base_objects(READER_ED1)
_reader_changes = _with_user_annotations(READER_ED1, READER_ANNOTATIONS)

COURSE_READER = _serialize(_reader_objs, (READER_ID, READER_ID))
# Annotated in an app that appends changes (original bytes kept as a prefix).
COURSE_READER_ANNOTATED_INCREMENTAL = _append_update(
    COURSE_READER, _reader_changes, (READER_ID, _file_id("course-reader-annotated-incremental"))
)
# Annotated in an app that rewrites the whole file (macOS Preview often does this).
COURSE_READER_ANNOTATED_REWRITTEN = _serialize(
    {**_reader_objs, **_reader_changes}, (READER_ID, _file_id("course-reader-annotated-rewritten"))
)
# A newer edition: different text, an extra page, and a NEW permanent ID.
_ed2_id = _file_id("course-reader-edition-2")
COURSE_READER_ED2 = _serialize(_base_objects(READER_ED2), (_ed2_id, _ed2_id))

MEETING_NOTES = "# Team sync\n\n- Demo the duplicate dashboard\n- Decide on keep rules\n"
PROJECT_PLAN = "# ORBIT plan\n\n1. Scanner\n2. Recommendations\n3. PDF matching\n"

FILES: dict[str, bytes | str] = {
    # Duplicate group: the same invoice PDF downloaded three times under different names.
    "downloads/invoice_1042.pdf": INVOICE,
    "downloads/invoice_1042 (1).pdf": INVOICE,
    "downloads/scan0001.pdf": INVOICE,
    # Duplicate group: identical notes in two folders.
    "notes/lecture_01.txt": LECTURE,
    "downloads/Lecture Notes - Week 1.txt": LECTURE,
    # Duplicate group: the same image with a camera-style name.
    "images/sunset.png": SUNSET,
    "images/IMG_4821.PNG": SUNSET,
    # Unique files.
    "images/forest.png": tiny_png(48, 32, (40, 140, 70)),
    "downloads/invoice_1043.pdf": tiny_pdf("Invoice #1043 - Acme Example Co. - Total: $75.50"),
    "notes/todo.md": "# To do\n\n- [ ] Finish ORBIT milestone 1\n- [ ] Review duplicate groups\n",
    "notes/lecture_02.txt": LECTURE.replace("Lecture 1", "Lecture 2"),  # same size, different bytes
    "data/budget.csv": "month,category,amount\n2026-01,books,42.10\n2026-01,transport,18.00\n",
    "data/readings.json": '{"sensor": "demo", "values": [1.2, 3.4, 5.6]}\n',
    "README_sample.txt": "Everything in this folder is synthetic test data generated for ORBIT.\n",
    # An empty file: shown in the table but never counted as a duplicate.
    "data/empty_placeholder.txt": b"",
    # --- Milestone 2 ---
    # Conflicting signals: the copy outside downloads has a "(1)" name; the downloads copy has a clean name.
    "notes/meeting_notes (1).md": MEETING_NOTES,
    "downloads/meeting_notes.md": MEETING_NOTES,
    # Ambiguous: same name, neutral folders, same timestamp. No rule can pick a winner.
    "projects/plan.md": PROJECT_PLAN,
    "archive/plan.md": PROJECT_PLAN,
    # Course reader: one exact re-download, plus versions that are NOT exact duplicates.
    "downloads/course_reader.pdf": COURSE_READER,
    "downloads/course_reader (1).pdf": COURSE_READER,
    "documents/course_reader_annotated.pdf": COURSE_READER_ANNOTATED_INCREMENTAL,
    "archive/course_reader_marked_up.pdf": COURSE_READER_ANNOTATED_REWRITTEN,
    "downloads/course_reader_2nd_edition.pdf": COURSE_READER_ED2,
}

# Fixed, realistic timestamps (UTC) so the dashboard and the "oldest copy" rule are predictable.
# Note: Git doesn't store timestamps, so a fresh clone shows checkout time until you re-run this script.
DEFAULT_MTIME = datetime(2026, 1, 15, 9, 0, tzinfo=timezone.utc)
MTIMES = {
    "downloads/": datetime(2026, 3, 2, 14, 30, tzinfo=timezone.utc),
    "documents/course_reader_annotated.pdf": datetime(2026, 2, 10, 18, 45, tzinfo=timezone.utc),
    "archive/course_reader_marked_up.pdf": datetime(2026, 2, 11, 20, 5, tzinfo=timezone.utc),
}


def mtime_for(relative: str) -> float:
    for prefix, when in MTIMES.items():
        if relative == prefix or (prefix.endswith("/") and relative.startswith(prefix)):
            return when.timestamp()
    return DEFAULT_MTIME.timestamp()


def main() -> None:
    if TARGET.parent != REPO_ROOT or TARGET.name != "sample_workspace":
        raise SystemExit("Refusing to run: unexpected target folder")
    for relative, content in FILES.items():
        path = (TARGET / relative).resolve()
        if not path.is_relative_to(TARGET.resolve()):
            raise SystemExit(f"Refusing to write outside the sample workspace: {relative}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode() if isinstance(content, str) else content)
        stamp = mtime_for(relative)
        os.utime(path, (stamp, stamp))
    print(f"Wrote {len(FILES)} synthetic files to {TARGET}")


if __name__ == "__main__":
    main()
