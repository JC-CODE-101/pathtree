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

    @classmethod
    def launch_in_terminal(cls, argv: list[str], cwd: Path) -> ProcessLaunchResult:
        """Launch command safely inside a new visible terminal window context."""
        import tempfile
        import uuid

        suffix = ".command" if sys.platform == "darwin" else ".py"
        temp_path = (
            Path(tempfile.gettempdir()) / f"pathtree_run_{uuid.uuid4().hex}{suffix}"
        )

        # Write self-contained python executor script
        content = (
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "import subprocess\n\n"
            "cwd = " + repr(str(cwd)) + "\n"
            "argv = " + repr(argv) + "\n\n"
            'print("=========================================")\n'
            'print("PathTree Script Executor")\n'
            'print("=========================================")\n'
            'print(f"Working Directory: {cwd}")\n'
            "print(f\"Command: {' '.join(argv)}\\n\")\n\n"
            "try:\n"
            "    p = subprocess.Popen(argv, cwd=cwd)\n"
            "    p.wait()\n"
            '    print(f"\\nScript finished with exit status: {p.returncode}.")\n'
            "except Exception as e:\n"
            '    print(f"\\nFailed to execute script: {e}")\n\n'
            'print("=========================================")\n'
            'input("Press Enter to close this window...")\n'
        )
        try:
            temp_path.write_text(content, encoding="utf-8")
            if sys.platform != "win32":
                os.chmod(temp_path, 0o755)
        except OSError as e:
            return ProcessLaunchResult(
                success=False,
                error_message=f"Failed to write execution wrapper: {e}",
            )

        # Resolve terminal emulator and command list
        if sys.platform == "darwin":
            term_argv = ["open", "-a", "Terminal.app", str(temp_path)]
        elif sys.platform == "win32":
            if shutil.which("wt"):
                term_argv = ["wt", "new-tab", sys.executable, str(temp_path)]
            else:
                term_argv = ["cmd.exe", "/c", "start", sys.executable, str(temp_path)]
        else:
            # Linux and other Unix-like OSes
            env_terminal = os.environ.get("TERMINAL")
            resolved_term = None
            if env_terminal:
                import shlex

                tokens = shlex.split(env_terminal)
                resolved_path = shutil.which(tokens[0]) if tokens else None
                if resolved_path:
                    resolved_term = resolved_path

            if not resolved_term:
                for term in [
                    "x-terminal-emulator",
                    "kitty",
                    "alacritty",
                    "wezterm",
                    "gnome-terminal",
                    "konsole",
                    "xfce4-terminal",
                    "xterm",
                ]:
                    resolved_path = shutil.which(term)
                    if resolved_path:
                        resolved_term = resolved_path
                        break

            if not resolved_term:
                return ProcessLaunchResult(
                    success=False,
                    error_message=(
                        "No supported terminal emulator found "
                        "(tried $TERMINAL, x-terminal-emulator, kitty, alacritty, "
                        "wezterm, gnome-terminal, konsole, xfce4-terminal, xterm)."
                    ),
                )

            base = os.path.basename(resolved_term)
            if base == "gnome-terminal":
                term_argv = [resolved_term, "--", sys.executable, str(temp_path)]
            elif base == "konsole":
                term_argv = [resolved_term, "-e", sys.executable, str(temp_path)]
            elif base == "xfce4-terminal":
                term_argv = [resolved_term, "-x", sys.executable, str(temp_path)]
            elif base == "kitty":
                term_argv = [resolved_term, "--", sys.executable, str(temp_path)]
            elif base == "alacritty":
                term_argv = [resolved_term, "-e", sys.executable, str(temp_path)]
            elif base == "wezterm":
                term_argv = [
                    resolved_term,
                    "start",
                    "--",
                    sys.executable,
                    str(temp_path),
                ]
            elif base == "xterm":
                term_argv = [resolved_term, "-e", sys.executable, str(temp_path)]
            else:
                term_argv = [resolved_term, "-e", sys.executable, str(temp_path)]

        # Launch the resolved terminal emulator in background
        try:
            proc = subprocess.Popen(term_argv)
            return ProcessLaunchResult(success=True, pid=proc.pid)
        except OSError as e:
            return ProcessLaunchResult(
                success=False,
                error_message=f"Failed to launch terminal emulator: {e}",
            )
