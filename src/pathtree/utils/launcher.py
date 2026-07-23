"""A platform-safe, secure launcher abstraction for launching files and editors."""

import os
import shutil
import subprocess
import sys
from pathlib import Path


class LaunchError(Exception):
    """Exception raised for launcher validation/execution failures."""


class PlatformLauncher:
    """A platform-safe and secure launcher abstraction.

    Ensures that subprocesses are invoked without shell=True, passing argv as lists,
    and validating paths and binaries before execution.
    """

    @staticmethod
    def validate_path(path_str: str) -> None:
        """Reject invalid paths, such as containing NUL bytes."""
        if "\x00" in path_str:
            raise LaunchError("Path contains NUL bytes.")

    @classmethod
    def open_path(cls, path: str) -> None:
        """Open a path with the system's default application securely."""
        cls.validate_path(path)
        path_obj = Path(path)
        if not path_obj.exists():
            raise LaunchError(f"Path '{path}' does not exist.")

        # Determine platform launcher
        if sys.platform.startswith("linux"):
            launcher = "xdg-open"
        elif sys.platform == "darwin":
            launcher = "open"
        elif sys.platform == "win32":
            try:
                os.startfile(path)
                return
            except AttributeError:
                # Fallback if os.startfile is not available (e.g. non-Windows test env)
                launcher = "start"
        else:
            raise LaunchError(f"Unsupported platform: {sys.platform}")

        # Check launcher availability
        if launcher != "start":
            if not shutil.which(launcher):
                raise LaunchError(f"System default launcher '{launcher}' not found.")

        try:
            if launcher == "start":
                # For Windows testing/fallback if startfile is missing
                # We use cmd /c start which is standard but we pass argv safely
                subprocess.Popen(["cmd", "/c", "start", "", path])
            else:
                subprocess.Popen([launcher, path])
        except Exception as e:
            raise LaunchError(f"Failed to open path: {e}") from e

    @classmethod
    def launch_editor(cls, editor_cmd: list[str] | str, path: str) -> None:
        """Launch an editor with a file path."""
        cls.validate_path(path)
        if isinstance(editor_cmd, str):
            cls.validate_path(editor_cmd)
            argv = [editor_cmd]
        else:
            for arg in editor_cmd:
                cls.validate_path(arg)
            argv = list(editor_cmd)

        # Check executable availability
        if not argv:
            raise LaunchError("No editor command configured.")

        executable = argv[0]
        if not shutil.which(executable):
            raise LaunchError(f"Editor executable '{executable}' not found in PATH.")

        argv.append(path)

        try:
            subprocess.Popen(argv)
        except Exception as e:
            raise LaunchError(f"Failed to launch editor: {e}") from e
