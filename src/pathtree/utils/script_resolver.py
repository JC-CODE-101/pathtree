"""Dedicated resolver for parsing script shebangs and resolving script interpreters."""

import os
import shutil
from pathlib import Path


class ScriptResolutionError(Exception):
    """Raised when script runner resolution fails."""


# Mapping of file extensions to their default interpreters
EXTENSION_MAP = {
    ".py": "python3",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "zsh",
    ".js": "node",
    ".mjs": "node",
    ".lua": "lua",
    ".rb": "ruby",
    ".pl": "perl",
    ".ps1": "pwsh",
}


def parse_shebang(script_path: Path) -> list[str] | None:
    """Parse shebang line safely from a script file.

    Returns the parsed interpreter argv list, or None if no shebang exists.
    """
    try:
        with open(script_path, "rb") as f:
            first_bytes = f.readline(512)
            if not first_bytes.startswith(b"#!"):
                return None
            try:
                line = first_bytes.decode("utf-8").strip()
            except UnicodeDecodeError:
                return None
    except OSError as e:
        raise ScriptResolutionError(f"Failed to read script file: {e}") from e

    # Remove the starting '#!'
    line = line[2:].strip()
    if not line:
        raise ScriptResolutionError("Empty shebang line.")

    tokens = line.split()
    if not tokens:
        return None

    first_token = tokens[0]
    # Check if we are using /usr/bin/env
    if first_token == "/usr/bin/env" or first_token.endswith("/env"):
        if len(tokens) < 2:
            raise ScriptResolutionError(
                "Invalid shebang: /usr/bin/env requires an interpreter name."
            )
        # If using '-S', e.g. '#!/usr/bin/env -S python3 -u', handle it safely
        if tokens[1] == "-S":
            if len(tokens) < 3:
                raise ScriptResolutionError(
                    "Invalid shebang: /usr/bin/env -S requires an interpreter name."
                )
            interpreter_argv = tokens[2:]
        else:
            interpreter_argv = tokens[1:]
    else:
        interpreter_argv = tokens

    return interpreter_argv


def resolve_script_argv(script_path: Path) -> list[str]:
    """Resolve the execution argv list for a given script path.

    Resolution order:
    1. Valid shebang
    2. Known file extension
    3. Direct execution when the file is executable
    4. Unsupported-script error

    Ensures that the resolved interpreter command is available on the system.
    """
    if not script_path.exists():
        raise ScriptResolutionError(f"Script file '{script_path}' does not exist.")
    if not script_path.is_file():
        raise ScriptResolutionError(f"Path '{script_path}' is not a regular file.")

    # 1. Check for a valid shebang
    shebang_argv = parse_shebang(script_path)
    if shebang_argv:
        interpreter = shebang_argv[0]
        # Verify the interpreter exists on the system
        if not shutil.which(interpreter):
            raise ScriptResolutionError(
                f"Interpreter '{interpreter}' from shebang "
                "is not installed or available in PATH."
            )
        return [*shebang_argv, str(script_path)]

    # 2. Check for a known file extension
    suffix = script_path.suffix.lower()
    if suffix == ".ts":
        # ts-node, bun, deno
        for runner in ["ts-node", "bun", "deno"]:
            if shutil.which(runner):
                if runner == "deno":
                    return ["deno", "run", str(script_path)]
                return [runner, str(script_path)]
        raise ScriptResolutionError(
            "TypeScript runner (ts-node, bun, or deno) "
            "is not installed or available in PATH."
        )

    if suffix in EXTENSION_MAP:
        interpreter = EXTENSION_MAP[suffix]
        if not shutil.which(interpreter):
            # Special fallback for Python on Windows/Mac
            # sometimes just "python" or "python3"
            if interpreter == "python3" and shutil.which("python"):
                interpreter = "python"
            else:
                raise ScriptResolutionError(
                    f"Interpreter '{interpreter}' for extension '{suffix}' "
                    "is not installed or available in PATH."
                )
        return [interpreter, str(script_path)]

    # 3. Direct execution when the file is executable
    if os.access(script_path, os.X_OK):
        return [str(script_path)]

    # 4. Return clear unsupported-script error
    raise ScriptResolutionError(
        f"Unsupported script file: '{script_path.name}'. "
        "No valid shebang found, the extension is not supported, "
        "and the file is not executable."
    )
