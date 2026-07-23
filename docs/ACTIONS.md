# PathTree Action System

Version: 0.1 (Draft)

---

# Overview

Actions define behavior.

Nodes describe objects.

Actions describe what can be done with those objects.

A node may have zero or more actions.

Actions are independent of node types.

---

# Design Goals

The Action system should be:

- modular
- extensible
- reusable
- platform independent

Actions should be attachable to any node.

---

# Core Concept

Nodes never execute anything directly.

Instead:

Node

↓

Action

↓

Execution

This separation keeps the architecture flexible.

---

# Common Properties

Every action contains:

- UUID
- Node UUID
- Name
- Description
- Enabled
- Sort Order
- Created
- Modified

---

# Execution

An action may execute:

- Open directory
- Open file
- Open URL
- Run command
- Start application

Future versions may support additional execution types.

---

# Working Directory

An action may define a working directory.

If omitted, the current shell directory is used.

---

# Arguments

Actions may define command-line arguments.

Arguments are stored separately from the executable.

Example

Executable

python

Arguments

script.py

--debug

This improves portability and security.

---

# Environment Variables

Future versions may allow actions to define environment variables.

These are intentionally postponed.

---

# Multiple Actions

A node may have multiple actions.

Example

Blender

Actions

- Open Folder
- Start Blender
- Factory Startup
- Open Documentation

---

# Confirmation

Actions may require user confirmation before execution.

Examples

Delete backup

Remove node

Shutdown server

---

# Execution Rules

Actions never execute automatically.

The user must explicitly choose an action.

---

# Security

Executable and arguments should remain separated.

Avoid shell execution whenever possible.

Validation belongs inside the service layer.

---

# Future Action Types

Future versions may introduce:

- Docker actions
- Git actions
- SSH actions
- Plugin actions
- User-defined actions

The Action architecture should support these additions without redesign.

---

# Summary

Nodes describe resources.

Actions describe behavior.

Keeping both concepts separated results in a flexible and maintainable architecture.

---

# Architecture (Initial Resource Action Framework)

This section describes the initial implementation of the resource-specific action framework introduced in PathTree.

## Provider Responsibilities
- Implement the `ResourceActionProvider` protocol.
- Declare the supported resource type (e.g., `'directory'`).
- Provide available actions for a resource context via `get_available_actions(context)`.
- Declare and return the default action for a resource context via `get_default_action(context)`.
- Execute a chosen action using `execute(action_id, context)` and return a `ResourceActionResult`.

## Registry Behavior
- Resolve the correct provider for a node kind and resource type using `get_provider(node_kind, resource_type)`.
- For Workspace and Folder nodes, the registry returns `None` as they are structural containers and not executable resources.
- For unsupported or unknown resource types, the registry returns `None` and clients should handle this fallback safely without crashing.
- No large resource-type-specific `if/elif` branching chains are allowed inside the registry. Registration is dynamic and dictionary-based.

## Default vs Additional Actions
- Each provider must declare one action as the default action (e.g., `change_directory` for directory resources).
- Additional actions (e.g., `copy_path` or `view_details` for directories) are declared as available actions so future menus (like the `O` context menu) can render them dynamically.

## Typed Result Handling
- Action execution returns a `ResourceActionResult` with the following attributes:
  - `success`: Whether the action completed successfully.
  - `exit_app`: Indicates if the application should terminate (e.g., after changing directory).
  - `output_value`: Return value or payload (e.g., absolute path string).
  - `message`: User-friendly completion message.
  - `error_message`: Error information if `success` is false.
- Validation failures and expected unsupported actions must not raise exceptions; they are returned safely as unsuccessful `ResourceActionResult` objects.

## Concrete Resource Types: File Resource Support

PathTree supports full-featured File resources with secure launching capabilities.

### Available Actions
1. **`open_file` (Default)**
   - Opens the file with the platform default application.
   - On Linux, this delegates to `xdg-open`. On macOS, to `open`. On Windows, to `os.startfile`.
   - Returns a notification target action result to keep the TUI open.

2. **`edit_file`**
   - Launches a configured text editor.
   - Leverages standard `EDITOR` or `VISUAL` environment variables (e.g., `export EDITOR='nano'`).
   - If no editor is configured, returns a clear, non-fatal error result to prevent crashing the TUI.

3. **`copy_path`**
   - Returns the absolute file path and presents it in the details panel using `ResourceActionResultTarget.DETAILS`.

4. **`view_details`**
   - Returns structured metadata about the file including Name, Path, File Size, Suffix/Extension, and Description if present, presented in the details panel using `ResourceActionResultTarget.DETAILS`.

### Security Requirements and Launcher Architecture
- **Prohibition of `shell=True`**: All subprocess operations strictly avoid `shell=True` to prevent shell injection vulnerabilities.
- **Explicit Argument Sequences**: Command and arguments are parsed using `shlex.split` and passed directly as list sequences (`argv: list[str]`).
- **No Implicit Execution**: Opening or selecting a File resource will never execute the file itself. It is only opened via standard default application launchers.
- **NUL Byte Rejections**: Paths and executable arguments containing NUL bytes (`\x00`) are rejected proactively to avoid subprocess vulnerability/hijacking.

## Concrete Resource Types: Script Resource Support

PathTree supports full-featured, secure Script resource execution.

### Available Actions
1. **`run_script` (Default)**
   - Executes the selected script safely.
   - Leverages a secure subprocess runner.
   - Runs using the parent directory of the script file as its process working directory (`cwd = script_path.parent`). This behavior is documented as part of the current MVP.

2. **`edit_script`**
   - Opens the script file in your configured text editor.
   - Reuses standard `EDITOR` or `VISUAL` editor parsing and launching logic safely.

3. **`copy_path`**
   - Copies script path to details panel.

4. **`view_details`**
   - Shows script metadata, including detected interpreter, working directory, whether path exists, and whether file is executable, without executing the script.

### Interpreter Resolution Order
The runner is resolved in this order:
1. **Valid shebang**: Parsed securely from the first line (e.g. `#!/usr/bin/python3` or `#!/usr/bin/env python3`).
2. **Known file extension**: Default interpreter mapped to extension:
   - `.py` -> `python3` (or `python` fallback)
   - `.sh`, `.bash` -> `bash`
   - `.zsh` -> `zsh`
   - `.js`, `.mjs` -> `node`
   - `.ts` -> TypeScript runners (`ts-node`, `bun`, `deno` if installed)
   - `.lua` -> `lua`
   - `.rb` -> `ruby`
   - `.pl` -> `perl`
   - `.ps1` -> `pwsh`
3. **Direct execution**: Supported if the file itself has its executable bit set (`X_OK`).
4. **Unsupported error**: Returns a clear non-fatal error to prevent TUI crashes.

Before launching, interpreters are verified using `shutil.which()`. If unavailable, a clear error is returned to the user safely.

### Security Guarantees
- **No `shell=True` or Shell Wrappers**: Never uses `shell=True`, `sh -c`, `bash -c`, `cmd /c`, or string command lines.
- **Explicit Argument List**: Construct commands using parsed, sequential token arrays (`argv`).
- **No Arbitrary Shell Syntax**: Does not execute arbitrary shell syntax after a shebang.

### MVP Limitations & Deferred Features
The following features are intentionally deferred from this MVP:
- Custom interpreter profiles
- Persisted command-line arguments
- Custom environment variables
- Configurable working directories
- Output capturing and logging
- Terminal-attached execution (interactive prompts)
- Long-running process management (stop/restart controls)

## Future Resource Types
- The architecture is designed to accommodate additional resource types such as:
  - `url` / `open_url`
  - `executable` / `run`
  - `ssh` / `command`

## Safety Rules for Command Execution
- Command execution on any resource type will **never** use `shell=True`.
- Environment and subprocess invocations will be kept minimal, verified against explicit security allowlists, and separated from arguments to prevent command injection.

## Resource Action Menu UI Flow

Pressing `O` on a supported resource opens a context-sensitive, keyboard-friendly Action Menu containing available actions returned by the Action Framework.

### Availability
- Only opens when the selected node is a Resource.
- Only opens when `ResourceActionRegistry` resolves a provider.
- Only opens when the provider returns at least one available action.
- For Workspace, Folder, or unsupported resources, a clear non-fatal message is shown in the details/error panel and the menu is not displayed.

### Default vs Explicit Menu Actions
- **Default Action**: Executed directly on double-click or Enter inside the main Tree (e.g., `change_directory` for directories).
- **Explicit Menu Actions**: Displayed in the Resource Action Menu when pressing `O`. Items display the action label, optional description, a marker indicating which is the default action (`*`), and a disabled status if `is_enabled` is False.

### Keyboard Controls
- `j` / Down / `Ctrl+J`: Highlight next action (with wrapping).
- `k` / Up / `Ctrl+K`: Highlight previous action (with wrapping).
- `Enter`: Execute highlighted action.
- `Escape`: Close menu without execution.
- Highlighting does not execute actions. Tree selection and expansion states remain untouched.

### Typed Result Handling
The menu callback executes the selected action via the provider, yielding a `ResourceActionResult`:
- `change_directory`: Preserves current output-file behavior, saves tree state, and exits app when `result.exit_app` is true.
- `copy_path`: Keeps the app open and displays the returned path clearly in the details panel or a temporary message.
- `view_details`: Keeps the app open and updates the details panel with the returned metadata.
- If execution fails, `result.error_message` is displayed centrally in the details/error area.
