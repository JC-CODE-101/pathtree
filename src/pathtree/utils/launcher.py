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
                term_argv = [sys.executable, str(temp_path)]
        else:
            # Linux and other Unix-like OSes
            env_terminal = os.environ.get("TERMINAL")
            resolved_term_argv = None
            if env_terminal:
                unsafe_operators = [";", "&&", "||", "|", ">", "<", "$(", "`"]
                if any(op in env_terminal for op in unsafe_operators):
                    return ProcessLaunchResult(
                        success=False,
                        error_message="Unsafe shell syntax detected in $TERMINAL.",
                    )

                import shlex

                tokens = shlex.split(env_terminal)
                resolved_path = shutil.which(tokens[0]) if tokens else None
                if resolved_path:
                    resolved_term_argv = [resolved_path, *tokens[1:]]

            if not resolved_term_argv:
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
                        resolved_term_argv = [resolved_path]
                        break

            if not resolved_term_argv:
                return ProcessLaunchResult(
                    success=False,
                    error_message=(
                        "No supported terminal emulator found "
                        "(tried $TERMINAL, x-terminal-emulator, kitty, alacritty, "
                        "wezterm, gnome-terminal, konsole, xfce4-terminal, xterm)."
                    ),
                )

            base = os.path.basename(resolved_term_argv[0])
            if base == "gnome-terminal":
                term_argv = [*resolved_term_argv, "--", sys.executable, str(temp_path)]
            elif base == "konsole":
                term_argv = [*resolved_term_argv, "-e", sys.executable, str(temp_path)]
            elif base == "xfce4-terminal":
                term_argv = [*resolved_term_argv, "-x", sys.executable, str(temp_path)]
            elif base == "kitty":
                term_argv = [*resolved_term_argv, "--", sys.executable, str(temp_path)]
            elif base == "alacritty":
                term_argv = [*resolved_term_argv, "-e", sys.executable, str(temp_path)]
            elif base == "wezterm":
                term_argv = [
                    *resolved_term_argv,
                    "start",
                    "--",
                    sys.executable,
                    str(temp_path),
                ]
            elif base == "xterm":
                term_argv = [*resolved_term_argv, "-e", sys.executable, str(temp_path)]
            else:
                term_argv = [*resolved_term_argv, "-e", sys.executable, str(temp_path)]

        # Launch resolved emulator (using CREATE_NEW_CONSOLE on Windows)
        extra_kwargs = {}
        if sys.platform == "win32" and "wt" not in term_argv[0]:
            # CREATE_NEW_CONSOLE is 0x00000010
            extra_kwargs["creationflags"] = 0x00000010

        try:
            proc = subprocess.Popen(term_argv, **extra_kwargs)
            return ProcessLaunchResult(success=True, pid=proc.pid)
        except OSError as e:
            return ProcessLaunchResult(
                success=False,
                error_message=f"Failed to launch terminal emulator: {e}",
            )

    @classmethod
    def copy_to_clipboard(cls, text: str) -> None:
        """Write the exact text to the system clipboard securely without shell=True."""
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes

                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32

                user32.OpenClipboard.argtypes = [wintypes.HWND]
                user32.OpenClipboard.restype = wintypes.BOOL
                user32.EmptyClipboard.argtypes = []
                user32.EmptyClipboard.restype = wintypes.BOOL
                user32.CloseClipboard.argtypes = []
                user32.CloseClipboard.restype = wintypes.BOOL
                user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
                user32.SetClipboardData.restype = wintypes.HANDLE

                kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
                kernel32.GlobalAlloc.restype = wintypes.HANDLE
                kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
                kernel32.GlobalLock.restype = ctypes.c_void_p
                kernel32.GlobalUnlock.argtypes = [wintypes.HANDLE]
                kernel32.GlobalUnlock.restype = wintypes.BOOL

                gmem_moveable = 0x0002
                cf_unicodetext = 13

                text_bytes = (text + "\x00").encode("utf-16le")

                if not user32.OpenClipboard(None):
                    raise OSError("Failed to open clipboard.")

                try:
                    user32.EmptyClipboard()
                    h_mem = kernel32.GlobalAlloc(gmem_moveable, len(text_bytes))
                    if not h_mem:
                        raise OSError("GlobalAlloc failed.")

                    p_mem = kernel32.GlobalLock(h_mem)
                    if not p_mem:
                        raise OSError("GlobalLock failed.")

                    try:
                        ctypes.memmove(p_mem, text_bytes, len(text_bytes))
                    finally:
                        kernel32.GlobalUnlock(h_mem)

                    if not user32.SetClipboardData(cf_unicodetext, h_mem):
                        raise OSError("SetClipboardData failed.")
                finally:
                    user32.CloseClipboard()
            except Exception as e:
                # Fallback to clip.exe
                if shutil.which("clip"):
                    try:
                        subprocess.run(
                            ["clip"], input=text, text=True, check=True, shell=False
                        )
                    except (OSError, subprocess.SubprocessError) as clip_err:
                        raise LaunchError(
                            f"Windows clip.exe failed: {clip_err}"
                        ) from clip_err
                else:
                    raise LaunchError(
                        "No supported Windows clipboard mechanism available. "
                        f"Details: {e}"
                    ) from e

        elif sys.platform == "darwin":
            if not shutil.which("pbcopy"):
                raise LaunchError("pbcopy executable not found in PATH.")
            try:
                subprocess.run(
                    ["pbcopy"], input=text, text=True, check=True, shell=False
                )
            except (OSError, subprocess.SubprocessError) as e:
                raise LaunchError(f"macOS pbcopy failed: {e}") from e

        else:
            # Linux and other Unix-like OSes
            # Select candidates based on session type
            session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
            if session_type == "wayland":
                candidates = ["wl-copy", "xclip", "xsel"]
            elif session_type == "x11":
                candidates = ["xclip", "xsel"]
            else:
                candidates = ["wl-copy", "xclip", "xsel"]

            # Map tools to argv
            tool_args = {
                "wl-copy": ["wl-copy"],
                "xclip": ["xclip", "-selection", "clipboard"],
                "xsel": ["xsel", "--clipboard", "--input"],
            }

            installed_backends = []
            backend_errors = []

            for tool in candidates:
                if shutil.which(tool):
                    installed_backends.append(tool)
                    args = tool_args[tool]
                    try:
                        subprocess.run(
                            args, input=text, text=True, check=True, shell=False
                        )
                        return
                    except (OSError, subprocess.SubprocessError) as e:
                        backend_errors.append(f"{tool} failed: {e}")

            if not installed_backends:
                raise LaunchError(
                    "No supported clipboard mechanism is available on this system. "
                    "Please install wl-clipboard, xclip, or xsel."
                )

            # All installed backends failed
            errors_str = "; ".join(backend_errors)
            raise LaunchError(
                f"All available clipboard backends failed to copy: {errors_str}"
            )
