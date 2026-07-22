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

## Future Resource Types
- The architecture is designed to accommodate additional resource types such as:
  - `script` / `run`
  - `url` / `open_url`
  - `file` / `edit` / `view`
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
