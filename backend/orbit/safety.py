"""Path safety: turn untrusted input into a path that is guaranteed to stay inside a sandbox.

Every path that comes from outside (for example an API query parameter) must pass
through `resolve_inside()` before it's used. That's the single gatekeeper.
"""

from pathlib import Path


class PathSafetyError(ValueError):
    """Raised when a requested path would escape the allowed sandbox."""


def resolve_inside(root: Path, relative: str = "") -> Path:
    """Return the absolute, symlink-free path of `root / relative`, or raise PathSafetyError.

    Blocks:
      * absolute paths ("/etc", "/Users/me/Downloads")
      * parent traversal ("../../secret")
      * home shortcuts ("~/Documents")
      * symlinks that point outside the root (resolve() follows them, then we check)
      * NUL bytes, which some OS calls treat as "end of string"
    """
    root = root.resolve(strict=True)

    if "\x00" in relative:
        raise PathSafetyError("Path contains a NUL byte")
    if relative.startswith("~"):
        raise PathSafetyError("Home-directory paths are not allowed")

    candidate = Path(relative)
    if candidate.is_absolute():
        raise PathSafetyError("Absolute paths are not allowed; use a path relative to the sandbox")

    # resolve() collapses "..", follows symlinks, and gives the real location on disk.
    target = (root / candidate).resolve()

    # The real location must be the root itself or something underneath it.
    if not target.is_relative_to(root):
        raise PathSafetyError("Path escapes the allowed sandbox")

    return target
