"""Path utilities for absolute normalization and tilde expansion."""

from pathlib import Path


def normalize_path(path_str: str | None) -> str | None:
    """Normalize a filesystem path: expand tildes (~), resolve, and make absolute.

    Does not require the path to exist on the filesystem during normalization.
    """
    if path_str is None:
        return None
    trimmed = path_str.strip()
    if not trimmed:
        return ""
    expanded = Path(trimmed).expanduser()
    absolute_path = expanded.absolute()
    return str(absolute_path.resolve())
