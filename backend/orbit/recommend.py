"""Recommend which copy to keep in each exact-duplicate group, and explain why.

How it works:
  Rules are applied in a fixed priority order. Each rule keeps only the copies that score
  best on it and drops the rest. As soon as one copy remains, it's the recommendation.
  This is easier to explain than adding up points: "Rule 1 dropped B, rule 3 dropped C."

    1. Preferred folder  - in a folder you said you like (earlier in your list wins)   [strong]
    2. Avoided folder    - NOT in a folder you said holds throwaway copies (downloads)  [strong]
    3. Filename          - no copy markers like "(1)", "copy", "scan0001", "IMG_1234"  [medium]
    4. Oldest copy       - earliest modification time (2 s tolerance)                   [weak]
    5. Tie-break         - alphabetical, so the result is always the same               [weak]

  If you've picked a copy yourself, your choice wins. ORBIT still shows what its rules
  would have picked.

This module is "pure". It only looks at data it's given (no disk, no network), which
makes it easy to test and easy to reuse later, e.g. from a phone command.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Callable, Literal

from .duplicates import DuplicateGroup
from .preferences import KeepRules, folder_matches
from .scanner import FileRecord

Tone = Literal["positive", "negative", "neutral"]
Strength = Literal["high", "medium", "low"]
Confidence = Literal["user", "high", "medium", "low"]


# ---------------------------------------------------------------------------
# Output shapes
# ---------------------------------------------------------------------------


@dataclass
class Signal:
    text: str
    tone: Tone


@dataclass
class CopyAssessment:
    relative_path: str
    absolute_path: str
    modified_at: str
    is_preferred: bool  # the copy to keep (your choice, or ORBIT's)
    is_suggested: bool  # the copy ORBIT's rules pick on their own
    signals: list[Signal]


@dataclass
class Recommendation:
    group_id: int
    sha256: str
    preferred_path: str
    suggested_path: str
    source: Literal["rules", "user"]
    confidence: Confidence
    decided_by: list[str]  # labels of the rules that narrowed the choice, in order
    reasons: list[str]  # why the preferred copy was chosen
    caveats: list[str]  # conflicting signals or ambiguity worth knowing about
    reclaimable_bytes: int
    copies: list[CopyAssessment]  # preferred copy first


# ---------------------------------------------------------------------------
# Filename quality
# ---------------------------------------------------------------------------

_NAME_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\s\(\d+\)$"), "Name ends with a copy number like “(1)”"),
    (re.compile(r"^copy of\s|[\s_-]copy(\s?\d+)?$"), "Name marks it as a copy"),
    (
        re.compile(r"^(?:(?:scan|img|dsc|dscn|pxl|image|photo|untitled|document|download|file)[\s_-]?\d*|screenshot\b.*)$"),
        "Generic auto-generated name",
    ),
]


def name_issues(name: str) -> list[str]:
    """List the reasons a filename looks like a copy or an auto-generated name."""
    stem = PurePosixPath(name).stem.casefold().strip()  # "Copy of Notes.txt" -> "copy of notes"
    return [message for pattern, message in _NAME_PATTERNS if pattern.search(stem)]


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rule:
    id: str
    label: str
    strength: Strength
    score: Callable[[FileRecord, KeepRules], float]  # lower is better
    tolerance: float = 0.0  # scores this close to the best count as a tie


def _preferred_rank(f: FileRecord, rules: KeepRules) -> float:
    for index, folder in enumerate(rules.preferred_folders):
        if folder_matches(f.relative_path, folder):
            return index
    return len(rules.preferred_folders)


def _avoided_folder(f: FileRecord, rules: KeepRules) -> str | None:
    return next((folder for folder in rules.avoid_folders if folder_matches(f.relative_path, folder)), None)


def _timestamp(f: FileRecord) -> float:
    return datetime.fromisoformat(f.modified_at).timestamp()


# Modification times this close together count as "the same time" (copies made in one go).
OLDEST_TOLERANCE_SECONDS = 2.0

RULES: tuple[Rule, ...] = (
    Rule("preferred_folder", "Preferred folder", "high", _preferred_rank),
    Rule("avoid_folder", "Avoided folder", "high", lambda f, r: 1.0 if _avoided_folder(f, r) else 0.0),
    Rule("filename", "Filename", "medium", lambda f, r: float(len(name_issues(f.name)))),
    Rule("oldest", "Oldest copy", "low", lambda f, r: _timestamp(f), tolerance=OLDEST_TOLERANCE_SECONDS),
)
TIEBREAK_LABEL = "Alphabetical tie-break"
_TIEBREAK = Rule("tiebreak", TIEBREAK_LABEL, "low", lambda f, r: 0.0)


# ---------------------------------------------------------------------------
# Explanations
# ---------------------------------------------------------------------------


def _quote_paths(files: list[FileRecord]) -> str:
    return ", ".join(f"“{f.relative_path}”" for f in files)


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def _reason(rule: Rule, winner: FileRecord, dropped: list[FileRecord], rules: KeepRules, sole: bool) -> str:
    """Explain one step. `sole` is True when this rule narrowed the choice down to one copy."""
    n = len(dropped)
    others = _plural(n, "the other copy", f"{n} other copies")
    if rule.id == "preferred_folder":
        folder = rules.preferred_folders[int(_preferred_rank(winner, rules))]
        if all(_preferred_rank(f, rules) == len(rules.preferred_folders) for f in dropped):
            return f"It's in your preferred folder “{folder}”; {others} {_plural(n, 'is', 'are')} not."
        return f"It's in “{folder}”, which is higher on your preferred-folders list than where {others} {_plural(n, 'is', 'are')}."
    if rule.id == "avoid_folder":
        places = sorted({_avoided_folder(f, rules) or "" for f in dropped})
        where = ", ".join(f"“{p}”" for p in places)
        return f"It's outside your avoided folders; {others} {_plural(n, 'is', 'are')} in {where}."
    if rule.id == "filename":
        if not name_issues(winner.name):
            return f"Its name looks original; {_quote_paths(dropped)} {_plural(n, 'looks', 'look')} like a copy or an auto-generated name."
        return f"Its name has fewer copy-like markers than {_quote_paths(dropped)}."
    if rule.id == "oldest":
        weak = "Timestamps are a weak signal, because copying or syncing can change them."
        if sole:
            return f"It's the oldest copy (modified {winner.modified_at[:10]}), so it's probably the original. {weak}"
        return (
            f"It's one of the oldest copies; {others} {_plural(n, 'is', 'are')} newer. Copies modified within "
            f"{OLDEST_TOLERANCE_SECONDS:g} seconds of each other count as the same age. {weak}"
        )
    return "All copies look equally good, so ORBIT picked the first one alphabetically."


_BETTER_PHRASES = {
    "preferred_folder": "is in a folder higher on your preferred list",
    "avoid_folder": "is outside your avoided folders",
    "filename": "has a cleaner name",
    "oldest": "is older",
}


def _signals(f: FileRecord, rules: KeepRules, oldest_path: str | None) -> list[Signal]:
    signals: list[Signal] = []
    rank = int(_preferred_rank(f, rules))
    if rank < len(rules.preferred_folders):
        position = f" (#{rank + 1} on your list)" if len(rules.preferred_folders) > 1 else ""
        signals.append(Signal(f"In preferred folder “{rules.preferred_folders[rank]}”{position}", "positive"))
    avoided = _avoided_folder(f, rules)
    if avoided:
        signals.append(Signal(f"In avoided folder “{avoided}”", "negative"))
    signals.extend(Signal(issue, "negative") for issue in name_issues(f.name))
    if f.relative_path == oldest_path:
        signals.append(Signal("Oldest copy", "neutral"))
    return signals


def _strictly_oldest(files: list[FileRecord], tolerance: float) -> str | None:
    """Path of the copy that is older than every other copy by more than `tolerance` seconds."""
    ordered = sorted(files, key=_timestamp)
    if len(ordered) > 1 and _timestamp(ordered[1]) - _timestamp(ordered[0]) > tolerance:
        return ordered[0].relative_path
    return None


# ---------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------


@dataclass
class _RuleOutcome:
    winner: FileRecord
    decided_by: list[Rule | None]  # None = tie-break
    reasons: list[str]
    dropped_by: dict[str, Rule | None]  # path -> rule that eliminated it


def _apply_rules(files: list[FileRecord], rules: KeepRules) -> _RuleOutcome:
    remaining = sorted(files, key=lambda f: f.relative_path)  # sorted = deterministic
    decided_by: list[Rule | None] = []
    left_after: list[int] = []  # how many copies were still in the running after each deciding step
    dropped_by: dict[str, Rule | None] = {}

    for rule in RULES:
        if len(remaining) == 1:
            break
        scores = {f.relative_path: rule.score(f, rules) for f in remaining}
        best = min(scores.values())
        keep = [f for f in remaining if scores[f.relative_path] <= best + rule.tolerance]
        if len(keep) < len(remaining):
            decided_by.append(rule)
            left_after.append(len(keep))
            for f in remaining:
                if f not in keep:
                    dropped_by[f.relative_path] = rule
        remaining = keep

    if len(remaining) > 1:
        decided_by.append(None)
        left_after.append(1)
        for f in remaining[1:]:
            dropped_by[f.relative_path] = None

    # Explain each step only now, once the final winner is known.
    winner = remaining[0]
    reasons = []
    for rule, left in zip(decided_by, left_after):
        dropped = [f for f in files if f.relative_path in dropped_by and dropped_by[f.relative_path] is rule]
        reasons.append(_reason(rule or _TIEBREAK, winner, dropped, rules, sole=left == 1))
    return _RuleOutcome(winner, decided_by, reasons, dropped_by)


def _caveats(files: list[FileRecord], outcome: _RuleOutcome, rules: KeepRules) -> list[str]:
    caveats: list[str] = []
    winner = outcome.winner
    for other in sorted(files, key=lambda f: f.relative_path):
        if other is winner:
            continue
        beaten_by = outcome.dropped_by.get(other.relative_path)
        priority = RULES.index(beaten_by) if beaten_by in RULES else len(RULES)
        # A rule with LOWER priority than the one that dropped `other` favoured `other`: that's a conflict.
        for rule in RULES[priority + 1 :]:
            if rule.score(other, rules) < rule.score(winner, rules) - rule.tolerance:
                deciding = beaten_by.label.lower() if beaten_by else "tie-break"
                caveats.append(
                    f"“{other.relative_path}” {_BETTER_PHRASES[rule.id]}, but the {deciding} rule takes priority."
                )
                break

    last = outcome.decided_by[-1] if outcome.decided_by else None
    if last is None or last.strength == "low":
        caveats.append("No strong signal separates these copies. Choose the one you want to keep yourself.")
    return caveats


def recommend(group: DuplicateGroup, files: list[FileRecord], rules: KeepRules, user_choice: str | None = None) -> Recommendation:
    """Recommend the copy to keep for one duplicate group. `files` may be all files or just the group's."""
    paths_in_group = set(group.relative_paths)
    members = sorted(
        (f for f in files if f.sha256 == group.sha256 and f.relative_path in paths_in_group),
        key=lambda f: f.relative_path,
    )
    if len(members) < 2:
        raise ValueError("A duplicate group needs at least two files")

    outcome = _apply_rules(members, rules)
    suggested = outcome.winner
    confidence: Confidence = "low"
    last = outcome.decided_by[-1] if outcome.decided_by else None
    if last is not None:
        confidence = last.strength

    reasons = outcome.reasons
    caveats = _caveats(members, outcome, rules)
    decided_by = [r.label if r else TIEBREAK_LABEL for r in outcome.decided_by]
    source: Literal["rules", "user"] = "rules"
    preferred = suggested

    paths = {f.relative_path: f for f in members}
    if user_choice is not None:
        if user_choice in paths:
            preferred = paths[user_choice]
            source, confidence, decided_by = "user", "user", ["Your choice"]
            agree = preferred is suggested
            reasons = ["You marked this as the copy to keep."] + (
                ["ORBIT's rules agree with your choice."]
                if agree
                else [f"ORBIT's rules would have suggested “{suggested.relative_path}”."]
            )
            caveats = []
        else:
            caveats.insert(0, f"Your earlier choice “{user_choice}” is no longer in this group, so ORBIT's rules apply again.")

    oldest = _strictly_oldest(members, tolerance=OLDEST_TOLERANCE_SECONDS)
    copies = [
        CopyAssessment(
            relative_path=f.relative_path,
            absolute_path=f.absolute_path,
            modified_at=f.modified_at,
            is_preferred=f is preferred,
            is_suggested=f is suggested,
            signals=_signals(f, rules, oldest),
        )
        for f in [preferred] + [m for m in members if m is not preferred]
    ]

    return Recommendation(
        group_id=group.group_id,
        sha256=group.sha256,
        preferred_path=preferred.relative_path,
        suggested_path=suggested.relative_path,
        source=source,
        confidence=confidence,
        decided_by=decided_by,
        reasons=reasons,
        caveats=caveats,
        reclaimable_bytes=group.wasted_bytes,
        copies=copies,
    )


def recommend_all(
    groups: list[DuplicateGroup], files: list[FileRecord], rules: KeepRules, choices: dict[str, str] | None = None
) -> list[Recommendation]:
    choices = choices or {}
    # Index files by hash once, so each group only looks at its own files (fast with many files).
    by_hash: dict[str, list[FileRecord]] = defaultdict(list)
    for f in files:
        by_hash[f.sha256].append(f)
    return [recommend(group, by_hash[group.sha256], rules, choices.get(group.sha256)) for group in groups]
