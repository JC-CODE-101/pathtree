# PathTree Architecture

Version: 0.1 (Draft)

---

# 1. Introduction

PathTree is a keyboard-first developer workspace platform.

Its purpose is to organize development environments, projects, resources, commands, documentation, and workflows inside one unified tree.

Unlike traditional bookmark managers or launchers, PathTree represents the user's mental workspace rather than the underlying filesystem.

The filesystem is only one possible resource inside the tree.

---

# 2. Design Goals

The architecture is designed around the following goals:

- modularity
- maintainability
- extensibility
- simplicity
- performance
- cross-platform compatibility

Every design decision should support these goals.

---

# 3. Core Principles

## Keyboard First

The entire application must be usable without a mouse.

Mouse support is optional.

---

## Tree Based

Everything inside PathTree is organized as a tree.

There is no limit to tree depth.

Users should organize data naturally instead of adapting to software limitations.

---

## Modular

Every subsystem should remain independent.

Examples:

- UI
- Database
- Search
- Plugins
- Shell integration

should communicate through well-defined interfaces.

---

## Extensible

Future features should not require redesigning the existing architecture.

Adding a new node type should require minimal changes.

---

## Platform Independent

The Python application must remain platform independent.

Platform-specific functionality belongs inside adapters.

---

# 4. High-Level Architecture

```

```
                Textual UI
                     │
                     ▼
             Application Layer
                     │
     ┌───────────────┼───────────────┐
     ▼               ▼               ▼
 Node Service   Action Service   Search Service
     │               │               │
     └───────────────┼───────────────┘
                     ▼
               Repository Layer
                     │
                     ▼
                  SQLite
```

```markdown

---

# 5. Layer Responsibilities

## User Interface

Responsible for:

- rendering
- navigation
- dialogs
- keyboard handling

The UI must never contain business logic.

---

## Services

Responsible for:

- tree operations
- searching
- launching actions
- validation
- business rules

---

## Repository

Responsible only for persistence.

The repository never contains business logic.

---

## Database

Responsible only for storing data.

---

# 6. Shell Integration

Python MUST NEVER execute

cd

inside the user's shell.

Instead:

Python returns

- selected path
- selected action

The shell adapter performs:

cd

or executes commands.

Supported adapters:

- Bash
- Zsh
- Fish
- PowerShell

---

# 7. Core Concepts

Everything inside PathTree is represented by a Node.

Nodes form the tree.

Actions define behavior.

Workspaces organize nodes.

---

# 8. Node Model

Every node contains:

- UUID
- parent UUID
- name
- node type
- description
- icon
- favorite flag
- temporary flag
- sort order
- created timestamp
- modified timestamp

Nodes do not contain executable logic.

---

# 9. Node Types

Initial node types:

- Workspace
- Folder
- File
- URL
- Documentation
- Command
- Launcher
- SSH
- Docker
- Git
- Note

Future node types should require only minimal implementation effort.

---

# 10. Action Model

Nodes do not execute anything.

Instead they own Actions.

Examples:

Blender

Actions

- Open Folder
- Start Blender
- Factory Startup
- Open Documentation
- Open GitHub

Actions contain:

- UUID
- node UUID
- name
- executable
- arguments
- working directory
- environment variables
- execution mode
- confirmation required

---

# 11. Workspace Model

A workspace groups related resources.

Example

Python

contains

- projects
- documentation
- virtual environments
- repositories
- commands

A workspace is not tied to a filesystem directory.

---

# 12. Data Storage

SQLite will be used.

Reasons:

- lightweight
- portable
- reliable
- fast
- zero configuration

The database schema should remain migration friendly.

---

# 13. Configuration

Configuration should be stored separately from user data.

Configuration examples:

- theme
- shell
- startup behavior
- keyboard shortcuts

Configuration should use JSON.

---

# 14. Search

Search must support:

- node names
- descriptions
- tags
- paths
- commands

Search should remain responsive even with thousands of nodes.

---

# 15. Plugin Architecture

Plugins should extend functionality.

Plugins must never modify the core.

Plugins communicate through stable interfaces.

Possible future plugins:

- Git
- Docker
- VSCode
- SSH
- Python
- Ollama

---

# 16. Event System

The application should internally communicate using events.

Examples:

NodeCreated

NodeDeleted

NodeMoved

ActionExecuted

WorkspaceChanged

This reduces coupling between modules.

---

# 17. Security

Commands are never executed automatically.

Actions must always be explicitly selected by the user.

Executable and arguments should be stored separately.

Avoid shell=True whenever possible.

---

# 18. Performance

The application should remain responsive with:

- thousands of nodes
- hundreds of workspaces
- thousands of actions

Use lazy loading where appropriate.

Avoid unnecessary database queries.

---

# 19. Project Structure

```

```
src/pathtree/

app.py

core/

database/

models/

services/

ui/

plugins/

shell/

actions/

utils/

config/
```

```markdown

The project structure should reflect architectural boundaries.

---

# 20. Long-Term Vision

PathTree should become the central entry point for development work.

Rather than replacing existing tools, it connects them.

Examples:

- projects
- documentation
- commands
- launchers
- repositories
- servers
- notes

Everything is organized inside one consistent tree.

---

# 21. Architectural Rule

The most important rule of the project:

> PathTree models the developer's mental workspace rather than the underlying filesystem.

Every future implementation should follow this principle.

If a proposed feature violates this rule, the architecture should be reconsidered before implementation.
