# PathTree Shell Integration

This document describes how PathTree integrates with supported terminal shell sessions to perform automatic directory navigation (`cd`).

---

## Architecture & Responsibilities

The shell integration relies on a lightweight shell adapter mechanism.

1. **Python Application**: Responsible for user interfaces, node/tree navigation, and database management. It never calls `os.chdir()` or executes terminal change-directory actions directly. Instead, when a directory is selected, the application writes the absolute path to a temporary file specified by the `--output` CLI flag and terminates with exit code 0.
2. **Shell Adapter**: Responsible for running PathTree, reading the temporary file contents safely (without execution or evaluation), verifying that the target exists and is a directory, changing the current working directory, and ensuring clean, transient removal of the temporary file.

---

## Installation & Setup

To enable directory-changing functionality via PathTree, you must **source** the appropriate shell adapter rather than executing it.

### Bash Setup

Add the following line to your `~/.bashrc`:

```bash
source /path/to/pathtree/shell/pathtree.bash
```

### Zsh Setup

Add the following line to your `~/.zshrc`:

```zsh
source /path/to/pathtree/shell/pathtree.zsh
```

*(Replace `/path/to/pathtree` with the actual path to your PathTree installation directory).*

---

## Usage: The `pb` Command

Once sourced, the integration provides the `pb` shell function:

- **Command**: `pb [arguments]`
- **Action**: Launches PathTree, allowing keyboard-first tree navigation. Upon pressing `Enter` on a selected folder, the active terminal session automatically changes its directory to the target path.
- **Safety**:
  - If you cancel or quit PathTree (`q` key or interrupt), your current shell directory remains unchanged.
  - If a non-existent path or a non-directory file is written, the shell adapter safely warns and remains in the original directory.
  - Sourced scripts run with localized helper variables, ensuring zero pollution of your active shell scope or existing user traps.

### Global Pinned Resources CLI Syntax

The `pb` command also supports fast pinnings and pin activation directly from your terminal session:

#### List Pins
Lists all active pins globally in deterministic position order:
```bash
pb -p
# or
pb --pins
```
Example Output:
```
1  Downloads          System
2  Blender Output     Blender
3  MusicGen Project   Music
```

#### Activate Pin by Number
Select and trigger a pinned resource by its position:
```bash
pb -p 1
# or
pb --pins 1
```
- For a **Directory** resource, the shell automatically navigates (`cd`) to its path.
- For a **non-Directory** resource, its default action provider is executed (e.g. running scripts, launching executables, or opening URLs).

#### Pin Node (Management Command)
Pin an existing node globally by its stable UUID:
```bash
pb --pin <node-id>
```

#### Unpin Node (Management Command)
Unpin a node globally by its visible numeric position:
```bash
pb --unpin <number>
```
Positions are automatically compacted and kept contiguous starting at 1.
