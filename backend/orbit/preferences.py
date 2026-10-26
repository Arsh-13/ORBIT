"""User preferences: which folders you like to keep files in, and which copy you picked by hand.

Everything here is stored in ORBIT's own small SQLite database (config.DB_PATH). Saving a
preference never touches the scanned files. It only records your choice.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

MAX_FOLDERS = 20
MAX_FOLDER_LENGTH = 100

DEFAULT_PREFERRED_FOLDERS = ["documents"]
DEFAULT_AVOID_FOLDERS = ["downloads"]


class PreferenceError(ValueError):
    """Raised when a preference value is invalid (bad folder name, conflicting rules...)."""


@dataclass
class KeepRules:
    """Where you'd rather keep files. Folder names are relative to the scanned workspace."""

    # Earlier in the list = more preferred.
    preferred_folders: list[str] = field(default_factory=lambda: list(DEFAULT_PREFERRED_FOLDERS))
    # Places that usually hold throwaway copies (e.g. downloads).
    avoid_folders: list[str] = field(default_factory=lambda: list(DEFAULT_AVOID_FOLDERS))


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def normalize_folder(raw: str) -> str:
    """Turn user input like ' Documents/School/ ' into 'documents/school', or raise PreferenceError.

    These names are only ever compared against scanned paths; they are never opened.
    We still reject anything that looks like an escape attempt, to keep the rules honest.
    """
    text = raw.strip()
    if not text:
        raise PreferenceError("Folder name is empty")
    if len(text) > MAX_FOLDER_LENGTH:
        raise PreferenceError("Folder name is too long")
    if text.startswith(("/", "~")) or "\x00" in text or "\\" in text:
        raise PreferenceError(f"“{text}” must be a folder inside the workspace, like “documents”")

    parts = PurePosixPath(text.strip("/")).parts
    if any(part in (".", "..") or part.startswith(".") for part in parts):
        raise PreferenceError(f"“{text}” may not contain '..' or hidden folders")
    return "/".join(parts).casefold()


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    return [x for x in items if not (x in seen or seen.add(x))]


def normalize_rules(preferred: list[str], avoid: list[str]) -> KeepRules:
    preferred_n = _dedupe([normalize_folder(x) for x in preferred])
    avoid_n = _dedupe([normalize_folder(x) for x in avoid])
    if len(preferred_n) > MAX_FOLDERS or len(avoid_n) > MAX_FOLDERS:
        raise PreferenceError(f"At most {MAX_FOLDERS} folders per list")
    both = sorted(set(preferred_n) & set(avoid_n))
    if both:
        raise PreferenceError(f"“{both[0]}” can't be both preferred and avoided")
    return KeepRules(preferred_folders=preferred_n, avoid_folders=avoid_n)


def folder_matches(relative_path: str, folder: str) -> bool:
    """True if the file is inside `folder` (or a subfolder of it). Case-insensitive, like macOS.

    'downloads' matches 'downloads/a.pdf' and 'downloads/x/b.pdf', but NOT 'downloads_old/a.pdf'.
    """
    return relative_path.casefold().startswith(folder + "/")


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL            -- JSON
);
CREATE TABLE IF NOT EXISTS preferred_copies (
    sha256        TEXT PRIMARY KEY, -- identifies a duplicate group by its content
    relative_path TEXT NOT NULL,    -- the copy you chose to keep
    chosen_at     TEXT NOT NULL
);
"""


class PreferenceStore:
    """Tiny wrapper around SQLite. Opens a fresh connection per call, which is simple and thread-safe."""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.executescript(_SCHEMA)
        return conn

    def _read(self, sql: str, params: tuple = ()) -> list[tuple]:
        # Reading never creates the database. No file means "nothing saved yet".
        if not self.db_path.exists():
            return []
        with closing(self._connect()) as conn:
            return conn.execute(sql, params).fetchall()

    def _write(self, sql: str, params: tuple = ()) -> int:
        with closing(self._connect()) as conn, conn:  # inner "with conn" commits or rolls back
            return conn.execute(sql, params).rowcount

    # --- keep rules ---

    def get_rules(self) -> KeepRules:
        rows = self._read("SELECT value FROM settings WHERE key = 'keep_rules'")
        if not rows:
            return KeepRules()
        try:
            data = json.loads(rows[0][0])
            return normalize_rules(data["preferred_folders"], data["avoid_folders"])
        except (ValueError, KeyError, TypeError, AttributeError):
            return KeepRules()  # damaged value: fall back to defaults instead of crashing

    def save_rules(self, rules: KeepRules) -> None:
        self._write(
            "INSERT INTO settings (key, value) VALUES ('keep_rules', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (json.dumps(asdict(rules)),),
        )

    # --- preferred copy choices ---

    def get_choices(self) -> dict[str, str]:
        return dict(self._read("SELECT sha256, relative_path FROM preferred_copies"))

    def set_choice(self, sha256: str, relative_path: str) -> None:
        self._write(
            "INSERT INTO preferred_copies (sha256, relative_path, chosen_at) VALUES (?, ?, ?) "
            "ON CONFLICT(sha256) DO UPDATE SET relative_path = excluded.relative_path, chosen_at = excluded.chosen_at",
            (sha256, relative_path, datetime.now(timezone.utc).isoformat()),
        )

    def clear_choice(self, sha256: str) -> bool:
        if not self.db_path.exists():
            return False
        return self._write("DELETE FROM preferred_copies WHERE sha256 = ?", (sha256,)) > 0
