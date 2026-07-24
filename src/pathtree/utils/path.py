"""Path utilities for absolute normalization and tilde expansion."""

import os
import sys
from pathlib import Path

# Constant for Windows executable extensions
WINDOWS_EXEC_EXTENSIONS = (".exe", ".com")


def is_launchable_file(path_obj: Path) -> bool:
    """Check if a file path is launchable/executable on the current platform."""
    if sys.platform == "win32":
        ext = path_obj.suffix.lower()
        return ext in WINDOWS_EXEC_EXTENSIONS
    else:
        # On POSIX: check if the file has execute permission
        try:
            return os.access(path_obj, os.X_OK)
        except OSError:
            return False


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
