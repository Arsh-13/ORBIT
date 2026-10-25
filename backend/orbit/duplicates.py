"""Exact duplicate detection.

Two files are exact duplicates when their bytes are identical. We decide that by
comparing SHA-256 hashes: equal hashes mean equal content (an accidental SHA-256
collision is not a realistic concern). Filenames and folders don't matter.

Empty (0-byte) files are left out of duplicate groups. Every empty file is technically
identical to every other one, but calling them "duplicates" would only add noise.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace

from .scanner import FileRecord, ScanIssue, ScanResult


@dataclass
class DuplicateGroup:
    group_id: int
    sha256: str
    size_bytes: int  # size of ONE copy
    file_count: int
    wasted_bytes: int  # space used by the extra copies: size * (count - 1)
    relative_paths: list[str]


@dataclass
class ScanSummary:
    total_files: int
    total_bytes: int
    duplicate_groups: int
    duplicate_files: int  # files that belong to any duplicate group
    redundant_copies: int  # duplicate_files minus one "original" per group
    wasted_bytes: int
    skipped_count: int
    error_count: int


@dataclass
class ScanReport:
    root: str
    truncated: bool
    summary: ScanSummary
    files: list[FileRecord]
    duplicate_groups: list[DuplicateGroup]
    skipped: list[ScanIssue]
    errors: list[ScanIssue]


def find_duplicate_groups(files: list[FileRecord]) -> list[DuplicateGroup]:
    """Group files by identical SHA-256. Only groups with 2+ non-empty files are returned.

    Groups are ordered by wasted space (biggest first) and numbered from 1.
    """
    by_hash: dict[str, list[FileRecord]] = defaultdict(list)
    for record in files:
        if record.size_bytes > 0:
            by_hash[record.sha256].append(record)

    clusters = [members for members in by_hash.values() if len(members) > 1]
    clusters.sort(key=lambda m: (-m[0].size_bytes * (len(m) - 1), m[0].sha256))

    groups = []
    for group_id, members in enumerate(clusters, start=1):
        size = members[0].size_bytes
        groups.append(
            DuplicateGroup(
                group_id=group_id,
                sha256=members[0].sha256,
                size_bytes=size,
                file_count=len(members),
                wasted_bytes=size * (len(members) - 1),
                relative_paths=sorted(m.relative_path for m in members),
            )
        )
    return groups


def build_report(scan: ScanResult) -> ScanReport:
    """Combine raw scan output with duplicate analysis into one response object."""
    groups = find_duplicate_groups(scan.files)

    group_of: dict[str, int] = {}
    for group in groups:
        for path in group.relative_paths:
            group_of[path] = group.group_id

    # replace() makes copies, so the original ScanResult is left untouched.
    files = [replace(f, duplicate_group=group_of.get(f.relative_path)) for f in scan.files]

    summary = ScanSummary(
        total_files=len(files),
        total_bytes=sum(f.size_bytes for f in files),
        duplicate_groups=len(groups),
        duplicate_files=sum(g.file_count for g in groups),
        redundant_copies=sum(g.file_count - 1 for g in groups),
        wasted_bytes=sum(g.wasted_bytes for g in groups),
        skipped_count=len(scan.skipped),
        error_count=len(scan.errors),
    )
    return ScanReport(
        root=scan.root,
        truncated=scan.truncated,
        summary=summary,
        files=files,
        duplicate_groups=groups,
        skipped=scan.skipped,
        errors=scan.errors,
    )
