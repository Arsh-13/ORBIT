"""Read-only folder scanner.

Walks a directory tree, collects metadata for each regular file, and computes its SHA-256
hash. It never writes, renames, moves, or deletes anything. Every file is opened read-only.

Safety rules:
  * Symlinks are never followed. They're reported as "skipped", so a link can't lead the
    scanner outside the folder it was asked to scan.
  * Only regular files are read. FIFOs, sockets, and device files are skipped, because
    reading a FIFO can block forever.
  * Problems with one file (permission denied, file vanished) are recorded and the scan
    continues. One bad file never crashes the whole scan.
"""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .config import HASH_CHUNK_SIZE, MAX_FILES_PER_SCAN


# ---------------------------------------------------------------------------
# Data shapes returned by the scanner
# ---------------------------------------------------------------------------


@dataclass
class FileRecord:
    name: str
    extension: str  # lower-case, including the dot (".pdf"), or "" if none
    size_bytes: int
    modified_at: str  # ISO-8601 timestamp in UTC
    absolute_path: str
    relative_path: str  # relative to the scanned folder, always with "/" separators
    sha256: str
    duplicate_group: int | None = None  # filled in later by duplicates.build_report()


@dataclass
class ScanIssue:
    relative_path: str
    reason: str


@dataclass
class ScanResult:
    root: str
    files: list[FileRecord] = field(default_factory=list)
    skipped: list[ScanIssue] = field(default_factory=list)  # intentionally not read
    errors: list[ScanIssue] = field(default_factory=list)  # tried to read, but failed
    truncated: bool = False  # True if MAX_FILES_PER_SCAN was hit


class ScanRootError(Exception):
    """The folder to scan is missing or is not a usable directory."""


class NotARegularFileError(OSError):
    """Raised when a path turns out not to be a regular file at the moment we open it."""


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


def hash_file(path: Path, chunk_size: int = HASH_CHUNK_SIZE) -> tuple[str, os.stat_result]:
    """Return (sha256_hex, stat) for a regular file, reading it in streaming chunks.

    O_NOFOLLOW makes open() fail if `path` is a symlink, even if it was swapped in after
    we listed the directory. O_NONBLOCK stops the open from hanging on a FIFO. We then
    check, on the already-open file, that it really is a regular file.
    """
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as handle:  # takes ownership of fd and closes it for us
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise NotARegularFileError(f"{path.name} is not a regular file")

        digest = hashlib.sha256()
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest(), info


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------


def _describe_os_error(exc: OSError) -> str:
    if isinstance(exc, PermissionError):
        return "Permission denied"
    if isinstance(exc, FileNotFoundError):
        return "File disappeared during the scan"
    if isinstance(exc, NotARegularFileError):
        return "Not a regular file"
    return f"Could not read file ({exc.strerror or type(exc).__name__})"


def scan_directory(
    directory: Path, *, max_files: int = MAX_FILES_PER_SCAN, relative_to: Path | None = None
) -> ScanResult:
    """Scan `directory` recursively (read-only) and return file metadata and hashes.

    `relative_to` controls how `relative_path` is written. By default paths are relative to
    `directory`. The API passes the workspace root, so a subfolder scan still reports
    "downloads/a.pdf" rather than "a.pdf", one consistent way of naming files everywhere.

    Hidden entries (names starting with ".", e.g. .DS_Store) are ignored.
    Raises ScanRootError if `directory` doesn't exist, isn't a folder, or is a symlink.
    """
    if directory.is_symlink():
        raise ScanRootError("The folder to scan is a symlink, which is not allowed")
    if not directory.exists():
        raise ScanRootError("The folder to scan does not exist")
    if not directory.is_dir():
        raise ScanRootError("The path to scan is not a folder")

    root = directory.resolve()
    base = relative_to.resolve() if relative_to is not None else root
    if not root.is_relative_to(base):
        raise ValueError("relative_to must contain the scanned folder")
    result = ScanResult(root=str(root))
    pending: list[Path] = [root]

    while pending:
        current = pending.pop()

        # Defence in depth: double-check that every folder we enter is still inside root
        # (guards against a folder being swapped for a symlink mid-scan).
        if not Path(os.path.realpath(current)).is_relative_to(root):
            result.skipped.append(ScanIssue(_rel(current, base), "Folder resolves outside the scan root"))
            continue

        try:
            with os.scandir(current) as iterator:
                entries = sorted(iterator, key=lambda e: e.name)
        except OSError as exc:
            result.errors.append(ScanIssue(_rel(current, base) or ".", _describe_os_error(exc)))
            continue

        for entry in entries:
            if entry.name.startswith("."):
                continue

            entry_path = Path(entry.path)
            rel = _rel(entry_path, base)

            try:
                if entry.is_symlink():
                    result.skipped.append(ScanIssue(rel, "Symlink (not followed)"))
                    continue
                if entry.is_dir(follow_symlinks=False):
                    pending.append(entry_path)
                    continue
                if not entry.is_file(follow_symlinks=False):
                    result.skipped.append(ScanIssue(rel, "Not a regular file"))
                    continue
            except OSError as exc:
                result.errors.append(ScanIssue(rel, _describe_os_error(exc)))
                continue

            if len(result.files) >= max_files:
                result.truncated = True
                pending.clear()
                break

            try:
                digest, info = hash_file(entry_path)
            except OSError as exc:
                result.errors.append(ScanIssue(rel, _describe_os_error(exc)))
                continue

            result.files.append(
                FileRecord(
                    name=entry.name,
                    extension=entry_path.suffix.lower(),
                    size_bytes=info.st_size,
                    modified_at=datetime.fromtimestamp(info.st_mtime, tz=timezone.utc).isoformat(),
                    absolute_path=str(entry_path),
                    relative_path=rel,
                    sha256=digest,
                )
            )

    result.files.sort(key=lambda f: f.relative_path)
    result.skipped.sort(key=lambda i: i.relative_path)
    result.errors.sort(key=lambda i: i.relative_path)
    return result


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name
