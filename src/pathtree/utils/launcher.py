"""A platform-safe, secure launcher abstraction for launching files and editors."""

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


class LaunchError(Exception):
    """Exception raised for launcher validation/execution failures."""


@dataclass(frozen=True)
class ProcessLaunchResult:
    """The result of launching a process securely."""

    success: bool
    pid: int | None = None
    error_message: str | None = None


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
        if sys.platform == "win32":
            try:
                os.startfile(path)
                return
            except AttributeError as e:
                raise LaunchError(f"System default launcher is unavailable: {e}") from e
            except OSError as e:
                raise LaunchError(f"Failed to open path: {e}") from e

        if sys.platform.startswith("linux"):
            launcher = "xdg-open"
        elif sys.platform == "darwin":
            launcher = "open"
        else:
            raise LaunchError(f"Unsupported platform: {sys.platform}")

        # Check launcher availability
        if not shutil.which(launcher):
            raise LaunchError(f"System default launcher '{launcher}' not found.")

        try:
            subprocess.Popen([launcher, path])
        except (OSError, ValueError) as e:
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
        except (OSError, ValueError) as e:
            raise LaunchError(f"Failed to launch editor: {e}") from e

    @classmethod
    def launch_process(
        cls, argv: list[str], cwd: Path | None = None
    ) -> ProcessLaunchResult:
        """Launch an external process securely without blocking the TUI."""
        if not argv:
            return ProcessLaunchResult(
                success=False, error_message="No execution arguments provided."
            )

        try:
            executable = argv[0]
            cls.validate_path(executable)
            for arg in argv[1:]:
                cls.validate_path(arg)

            if not shutil.which(executable):
                return ProcessLaunchResult(
                    success=False,
                    error_message=f"Executable '{executable}' not found in PATH.",
                )

            # Use subprocess.Popen with explicit argv, shell=False is default
            proc = subprocess.Popen(argv, cwd=cwd)
            return ProcessLaunchResult(success=True, pid=proc.pid)
        except (OSError, ValueError, LaunchError) as e:
            return ProcessLaunchResult(
                success=False, error_message=f"Failed to launch process: {e!s}"
            )
