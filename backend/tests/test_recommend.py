"""Tests for the recommendation engine. Uses in-memory FileRecords, so no disk access is needed."""

from __future__ import annotations

import random

import pytest

from orbit.duplicates import find_duplicate_groups
from orbit.preferences import KeepRules
from orbit.recommend import name_issues, recommend, recommend_all
from orbit.scanner import FileRecord

HASH_A = "a" * 64
HASH_B = "b" * 64
JAN = "2026-01-10T09:00:00+00:00"
MAR = "2026-03-02T14:30:00+00:00"

NO_RULES = KeepRules(preferred_folders=[], avoid_folders=[])
DEFAULTS = KeepRules()  # preferred: documents, avoid: downloads


def rec(path: str, modified: str = JAN, sha: str = HASH_A, size: int = 100) -> FileRecord:
    name = path.rsplit("/", 1)[-1]
    return FileRecord(
        name=name,
        extension="." + name.rsplit(".", 1)[-1].lower() if "." in name else "",
        size_bytes=size,
        modified_at=modified,
        absolute_path="/sandbox/" + path,
        relative_path=path,
        sha256=sha,
    )


def recommend_for(files: list[FileRecord], rules: KeepRules = DEFAULTS, choice: str | None = None):
    groups = find_duplicate_groups(files)
    assert len(groups) == 1
    return recommend(groups[0], files, rules, choice)


# ---------------------------------------------------------------------------
# Filename patterns
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "invoice (1).pdf",
        "invoice (12).pdf",
        "Copy of notes.txt",
        "notes copy.txt",
        "notes - copy 2.txt",
        "notes_copy.txt",
        "scan0001.pdf",
        "IMG_4821.PNG",
        "DSC_0042.jpg",
        "Screenshot 2026-01-01 at 10.00.00.png",
        "untitled.txt",
        "document.pdf",
    ],
)
def test_copy_like_names_are_flagged(name: str):
    assert name_issues(name), name


@pytest.mark.parametrize(
    "name",
    [
        "invoice_1042.pdf",
        "Lecture Notes - Week 1.txt",
        "documentation_plan.md",
        "copyright_notice.txt",
        "image_resizer.py",
        "photosynthesis.pdf",
        "README",
        "2026 budget.csv",
    ],
)
def test_normal_names_are_not_flagged(name: str):
    assert name_issues(name) == [], name


# ---------------------------------------------------------------------------
# Individual rules
# ---------------------------------------------------------------------------


def test_preferred_folder_wins():
    r = recommend_for([rec("misc/report.pdf"), rec("documents/report.pdf")])
    assert r.preferred_path == "documents/report.pdf"
    assert r.decided_by == ["Preferred folder"]
    assert r.confidence == "high"
    assert "preferred folder “documents”" in r.reasons[0]


def test_earlier_preferred_folder_beats_later_one():
    rules = KeepRules(preferred_folders=["school", "documents"], avoid_folders=[])
    r = recommend_for([rec("documents/a.pdf"), rec("school/a.pdf")], rules)
    assert r.preferred_path == "school/a.pdf"
    assert "higher on your preferred-folders list" in r.reasons[0]


def test_avoided_folder_loses():
    rules = KeepRules(preferred_folders=[], avoid_folders=["downloads"])
    r = recommend_for([rec("downloads/report.pdf"), rec("misc/report.pdf")], rules)
    assert r.preferred_path == "misc/report.pdf"
    assert r.decided_by == ["Avoided folder"]
    assert "“downloads”" in r.reasons[0]


def test_folder_rules_match_whole_folder_names_only():
    rules = KeepRules(preferred_folders=[], avoid_folders=["downloads"])
    r = recommend_for([rec("downloads_old/a.txt"), rec("downloads/a.txt")], rules)
    assert r.preferred_path == "downloads_old/a.txt"  # "downloads_old" is not "downloads"


def test_folder_rules_are_case_insensitive_and_include_subfolders():
    rules = KeepRules(preferred_folders=["documents"], avoid_folders=[])
    r = recommend_for([rec("Documents/School/a.txt"), rec("other/a.txt")], rules)
    assert r.preferred_path == "Documents/School/a.txt"


def test_clean_name_beats_copy_names():
    files = [rec("x/invoice (1).pdf"), rec("x/scan0001.pdf"), rec("x/invoice.pdf"), rec("x/Copy of invoice.pdf")]
    r = recommend_for(files, NO_RULES)
    assert r.preferred_path == "x/invoice.pdf"
    assert r.decided_by == ["Filename"]
    assert r.confidence == "medium"


def test_oldest_copy_wins_when_everything_else_ties():
    r = recommend_for([rec("b/report.pdf", MAR), rec("a/report.pdf", MAR), rec("c/report.pdf", JAN)], NO_RULES)
    assert r.preferred_path == "c/report.pdf"
    assert r.decided_by == ["Oldest copy"]
    assert r.confidence == "low"
    assert any("weak signal" in reason for reason in r.reasons)


def test_reclaimable_bytes_and_reasons_always_present():
    r = recommend_for([rec("a/x.bin", size=500), rec("b/x.bin", size=500), rec("c/x.bin", size=500)], NO_RULES)
    assert r.reclaimable_bytes == 1000
    assert r.reasons and all(r.reasons)


# ---------------------------------------------------------------------------
# Several rules together, conflicts, and ambiguity
# ---------------------------------------------------------------------------


def test_multiple_rules_each_explain_their_step():
    files = [rec("downloads/notes.txt"), rec("documents/notes (1).txt"), rec("documents/notes.txt")]
    r = recommend_for(files)
    assert r.preferred_path == "documents/notes.txt"
    assert r.decided_by == ["Preferred folder", "Filename"]
    assert len(r.reasons) == 2
    assert "documents/notes (1).txt" in r.reasons[1]
    # The last deciding rule (filename) sets the confidence.
    assert r.confidence == "medium"


def test_conflict_location_beats_name_and_is_reported():
    # The downloads copy has the cleaner name, but location rules rank higher.
    files = [rec("downloads/meeting_notes.md"), rec("notes/meeting_notes (1).md")]
    r = recommend_for(files)
    assert r.preferred_path == "notes/meeting_notes (1).md"
    assert any("downloads/meeting_notes.md" in c and "cleaner name" in c for c in r.caveats)


def test_conflict_clean_name_beats_older_copy_and_is_reported():
    files = [rec("x/report (1).pdf", JAN), rec("x/report.pdf", MAR)]
    r = recommend_for(files, NO_RULES)
    assert r.preferred_path == "x/report.pdf"
    assert any("x/report (1).pdf" in c and "is older" in c for c in r.caveats)


def test_true_tie_is_flagged_as_ambiguous():
    files = [rec("projects/plan.md"), rec("archive/plan.md")]
    r = recommend_for(files, NO_RULES)
    assert r.preferred_path == "archive/plan.md"  # alphabetical
    assert r.decided_by == ["Alphabetical tie-break"]
    assert r.confidence == "low"
    assert any("No strong signal" in c for c in r.caveats)


def test_timestamps_within_tolerance_count_as_a_tie():
    files = [rec("b/plan.md", "2026-01-10T09:00:01+00:00"), rec("a/plan.md", "2026-01-10T09:00:00.500000+00:00")]
    r = recommend_for(files, NO_RULES)
    assert r.decided_by == ["Alphabetical tie-break"]


def test_result_does_not_depend_on_input_order():
    files = [rec("downloads/a (1).txt"), rec("misc/a.txt", MAR), rec("misc/scan01.txt"), rec("documents/a copy.txt")]
    expected = recommend_for(files).preferred_path
    for seed in range(10):
        shuffled = files[:]
        random.Random(seed).shuffle(shuffled)
        assert recommend_for(shuffled).preferred_path == expected


# ---------------------------------------------------------------------------
# User-selected preferred copies
# ---------------------------------------------------------------------------


def test_user_choice_overrides_rules():
    files = [rec("documents/report.pdf"), rec("downloads/report (1).pdf")]
    r = recommend_for(files, choice="downloads/report (1).pdf")
    assert r.preferred_path == "downloads/report (1).pdf"
    assert r.suggested_path == "documents/report.pdf"
    assert r.source == "user"
    assert r.confidence == "user"
    assert any("would have suggested “documents/report.pdf”" in reason for reason in r.reasons)
    copies = {c.relative_path: c for c in r.copies}
    assert copies["downloads/report (1).pdf"].is_preferred
    assert copies["documents/report.pdf"].is_suggested and not copies["documents/report.pdf"].is_preferred
    assert r.copies[0].relative_path == "downloads/report (1).pdf"  # preferred copy listed first


def test_user_choice_matching_rules_says_they_agree():
    files = [rec("documents/report.pdf"), rec("downloads/report.pdf")]
    r = recommend_for(files, choice="documents/report.pdf")
    assert r.source == "user"
    assert any("agree" in reason for reason in r.reasons)


def test_stale_user_choice_falls_back_to_rules():
    files = [rec("documents/report.pdf"), rec("downloads/report.pdf")]
    r = recommend_for(files, choice="documents/renamed_or_deleted.pdf")
    assert r.source == "rules"
    assert r.preferred_path == "documents/report.pdf"
    assert "no longer in this group" in r.caveats[0]


def test_choices_only_apply_to_their_own_group():
    files = [
        rec("documents/a.txt", sha=HASH_A),
        rec("downloads/a.txt", sha=HASH_A),
        rec("documents/b.txt", sha=HASH_B),
        rec("downloads/b.txt", sha=HASH_B),
    ]
    groups = find_duplicate_groups(files)
    recs = recommend_all(groups, files, DEFAULTS, {HASH_B: "downloads/b.txt"})
    by_hash = {r.sha256: r for r in recs}
    assert by_hash[HASH_A].source == "rules" and by_hash[HASH_A].preferred_path == "documents/a.txt"
    assert by_hash[HASH_B].source == "user" and by_hash[HASH_B].preferred_path == "downloads/b.txt"


def test_signals_describe_each_copy():
    files = [rec("downloads/IMG_0001.jpg", MAR), rec("documents/beach.jpg", JAN)]
    r = recommend_for(files)
    signals = {c.relative_path: [(s.text, s.tone) for s in c.signals] for c in r.copies}
    assert ("In preferred folder “documents”", "positive") in signals["documents/beach.jpg"]
    assert ("Oldest copy", "neutral") in signals["documents/beach.jpg"]
    assert ("In avoided folder “downloads”", "negative") in signals["downloads/IMG_0001.jpg"]
    assert ("Generic auto-generated name", "negative") in signals["downloads/IMG_0001.jpg"]


def test_recommend_refuses_a_single_file_group():
    from orbit.duplicates import DuplicateGroup

    group = DuplicateGroup(1, HASH_A, 100, 1, 0, ["a.txt"])
    with pytest.raises(ValueError):
        recommend(group, [rec("a.txt")], DEFAULTS)
