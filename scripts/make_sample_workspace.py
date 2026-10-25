"""Create the synthetic files in sample_workspace/ (safe to re-run).

Every file is invented test data. This script writes ONLY inside the repository's
sample_workspace/ folder and refuses to run if that path looks wrong.

Usage (from the repository root):  python3 scripts/make_sample_workspace.py
"""

from __future__ import annotations

import struct
import zlib
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
}


def main() -> None:
    if TARGET.parent != REPO_ROOT or TARGET.name != "sample_workspace":
        raise SystemExit("Refusing to run: unexpected target folder")
    for relative, content in FILES.items():
        path = (TARGET / relative).resolve()
        if not path.is_relative_to(TARGET.resolve()):
            raise SystemExit(f"Refusing to write outside the sample workspace: {relative}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode() if isinstance(content, str) else content)
    print(f"Wrote {len(FILES)} synthetic files to {TARGET}")


if __name__ == "__main__":
    main()
