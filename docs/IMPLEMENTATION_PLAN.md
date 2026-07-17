# PathTree Implementation Plan - Milestone 0.0.1 (Foundation)

This document outlines the revised, streamlined implementation plan and technical specifications for **Milestone 0.0.1 (Foundation)** of PathTree.

The primary goal of Milestone 0.0.1 is to establish the absolute minimum technical foundation required for tree-based directory navigation and directory-changing shell integration, strictly adhering to the roadmap and omitting any premature features or infrastructure.

---

## 1. Project Structure

The project structure is kept simple and free of premature infrastructure. Standard Python packaging is used, and files such as custom config parsers, event buses, search components, and other future subsystems are omitted.

```
.
├── pyproject.toml              # Standard Python packaging configuration
├── README.md                   # Project overview
├── AGENTS.md                   # Agent guidelines
├── LICENSE                     # License file
├── docs/                       # System documentation
│   ├── VISION.md
│   ├── ARCHITECTURE.md
│   ├── ROADMAP.md
│   ├── DATABASE.md
│   ├── NODE_TYPES.md
│   ├── ACTIONS.md
│   ├── UI.md
│   ├── SHELL.md
│   └── IMPLEMENTATION_PLAN.md  # [This File] Detailed blueprint for Milestone 0.0.1
├── shell/                      # Non-Python shell integration adapters
│   ├── pathtree.bash           # Bash adapter script
│   └── pathtree.zsh            # Zsh adapter script
├── src/                        # Python package source root
│   └── pathtree/
│       ├── __init__.py         # Package-level entry point
│       ├── app.py              # CLI entry point using standard argparse
│       ├── database/
│       │   ├── __init__.py
│       │   ├── connection.py   # SQLite connection & schema initialization
│       │   └── repository.py   # Minimal DB persistence operations
│       ├── models/
│       │   ├── __init__.py
│       │   └── node.py         # Node database and MVP domain model
│       ├── services/
│       │   ├── __init__.py
│       │   └── node_service.py # Tree traversal and directory resolution
│       └── ui/
│           ├── __init__.py
│           ├── app.py          # Main Textual App class
│           ├── screens/
│           │   ├── __init__.py
│           │   └── main.py     # Main user interface screen
│           └── widgets/
│               ├── __init__.py
│               ├── details.py  # Render pane displaying active node details
│               └── tree.py     # Custom tree widget wrapping Textual's Tree
└── tests/                      # Testing directory
    ├── __init__.py
    ├── conftest.py             # Pytest fixtures (in-memory DB)
    ├── test_database.py        # SQLite repository tests
    ├── test_services.py        # Node service logic tests
    └── test_ui.py              # Textual UI layout & navigation tests
```

---

## 2. Python Package Layout

We utilize a standard **`src/` layout** for the `pathtree` package.

- **Standard Packaging**: Uses a standard declarative `pyproject.toml` utilizing modern build backends (such as `hatchling` or `setuptools`). We avoid dependency on Poetry to minimize environment complexity, relying instead on standard packaging tools and basic `pip install -e .`.
- **Imports**: All submodules are imported cleanly using absolute imports from the `pathtree` namespace.

---

## 3. Recommended Libraries

We minimize third-party dependencies to ensure long-term maintainability:

1. **SQLModel (version >= 0.0.22)**
   - *Why*: Provides the easiest interface to SQLite by combining SQLAlchemy and Pydantic into a single declarative structure.
2. **Textual (version >= 1.0.0)**
   - *Why*: The standard framework for building terminal user interfaces in modern Python.
3. **pytest & pytest-asyncio**
   - *Why*: Unit testing suite with async testing capabilities for Textual widgets.
4. **ruff**
   - *Why*: Code linting and formatting.
5. **argparse (Standard Library)**
   - *Why*: Preferred over `Click` to avoid unnecessary dependencies and keep the CLI clean and standard.

---

## 4. Responsibilities of Each Module

| Module Name | High-Level Responsibility | Detail / Constraints |
| :--- | :--- | :--- |
| **`pathtree/app.py`** | Main entry point | Uses built-in `argparse`. Directs flow to either database actions (e.g. `--seed-dev` explicitly) or TUI initialization. |
| **`models/node.py`** | Schema representation | Declares the properties of `Node` (including local filesystem directory support). |
| **`database/connection.py`** | Database session setup | Manages engine pools, applies optimized SQLite pragmas (WAL mode, foreign keys), and implements basic database initialization. |
| **`database/repository.py`** | Persistent database storage | Contains read and write operations for nodes. Kept free of business logic. |
| **`services/node_service.py`** | Tree & validation logic | Constructs logical folder structures and validates node safety (no self-parenting loops). Resolves selected directories. |
| **`ui/app.py`** | Textual app controller | Sets up the stylesheet and mounts screens. |
| **`ui/screens/main.py`** | User Interface layout | Establishes screen layout (Horizontal container mapping NodeTreeView to details pane) and handles central keybindings. |
| **`ui/widgets/tree.py`** | Tree visualization | Populates branches from service-provided nodes. Supports standard expansion and collapse keys. |
| **`ui/widgets/details.py`** | Information display | Static, reactive panel displaying metadata of the highlighted node. |
| **`shell/pathtree.bash`** | Bash shell adapter | Integrates with Bash to handle the `cd` wrapper using the installed `pathtree` command. |
| **`shell/pathtree.zsh`** | Zsh shell adapter | Integrates with Zsh to handle the `cd` wrapper using the installed `pathtree` command. |

---

## 5. Database Implementation Strategy

SQLite is used for data storage. The implementation has been simplified and aligned with best practices:

### Model Coupling Compromise
*MVP Compromise*: In Milestone 0.0.1, we couple our business domain model directly with the `SQLModel` database persistence entity class `Node`. While strict layered architectures split database-entities and domain models, keeping them unified simplifies the MVP schema footprint. This coupling is explicitly documented here as a **temporary compromise for Milestone 0.0.1** and will be separated once multi-action mappings or plugin domains are introduced.

### Schema Mapping (Node Model)
The `Node` schema is adjusted to include an optional `path` field for local directory-navigation and excludes Milestone 0.0.2 features (like favorites or temporary flags):

```python
import uuid
from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel

class Node(SQLModel, table=True):
    __tablename__ = "nodes"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        nullable=False
    )
    parent_id: Optional[uuid.UUID] = Field(
        default=None,
        foreign_key="nodes.id",
        nullable=True,
        index=True
    )
    name: str = Field(index=True, nullable=False)
    node_type: str = Field(default="Folder", index=True, nullable=False)  # Workspace or Folder
    description: Optional[str] = Field(default=None, nullable=True)
    icon: Optional[str] = Field(default=None, nullable=True)
    path: Optional[str] = Field(default=None, nullable=True) # Optional filesystem directory path
    sort_order: int = Field(default=0, nullable=False)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
```

### Initial Schema-Version Strategy
To resolve future migration conflicts with `DATABASE.md` and manage updates smoothly, we will utilize the lightweight **SQLite `user_version` PRAGMA**.
- On startup, `database/connection.py` will query `PRAGMA user_version;`.
- For Milestone 0.0.1, the expected `user_version` is `1`.
- If the schema does not exist, the tables are generated, and we execute `PRAGMA user_version = 1;`.
- In subsequent milestones, when migrations are needed, the startup routine will check this integer version and run sequential Python migration scripts before running the app.

### Application Data Directory (Platform-Compliant)
User data must never clutter the configuration folder. We store application data files in the correct OS platform data directory:
- **Linux**: `~/.local/share/pathtree/pathtree.db`
- **macOS**: `~/Library/Application Support/pathtree/pathtree.db`
- **Windows**: `%USERPROFILE%\AppData\Local\pathtree\pathtree.db`
- *Override support*: The library supports setting the environment variable `PATHTREE_DB_PATH` to specify a custom file location (extremely helpful for sandbox testing and pytest isolation).

---

## 6. Textual UI Architecture

The interface is strictly designed around the **ROADMAP scope of Milestone 0.0.1**.

### Stripped Scope
The following features are **completely removed** from Milestone 0.0.1 and deferred to Milestone 0.0.2:
- Dynamic Search Input / `SearchInput` widget
- Real-time filtering / queries
- Favorite indicators and toggles (such as `f` shortcut or star icons)
- Temporary session bookmarks
- Category/Workspace management interfaces

### Layout
```
+-------------------------------------------------------------+
| Header (Built-in Title / Active Node Name)                  |
+-------------------------------------------------------------+
|                                                             |
|  NodeTreeView (65% width)        | NodeDetailsPanel (35%)   |
|  - Root Workspace                |                          |
|    - Src Folder [path: /src]     | - Name: Src Folder       |
|    - Tests Folder [path: /tests] | - Type: Folder           |
|                                  | - Path: /src             |
|                                  |                          |
+-------------------------------------------------------------+
| Footer (Keybindings Status Bar)                             |
+-------------------------------------------------------------+
```

### Keybindings
- `j` / `Down`: Move selection down in the tree.
- `k` / `Up`: Move selection up in the tree.
- `h` / `Left`: Collapse active directory node. If already collapsed, move focus to its parent node.
- `l` / `Right`: Expand active directory node.
- `Enter`: Activate node. If the node possesses a directory path, write to the target file and shut down with exit code 0.
- `q`: Safely exit the application.

---

## 7. Shell Adapter Architecture

To support different environments, we replace the POSIX wrapper with separate, minimal, shell-specific scripts targeting **Bash** and **Zsh** respectively.

- **No Poetry Dependency**: These scripts invoke the globally/locally installed `pathtree` executable directly. They do not depend on Poetry or look for a local `pyproject.toml` file.
- **Strict Separation**: Clean scripts are placed under `shell/` to change terminal sessions safely.
- **Reliable Cleanup using Traps**: To avoid leaving behind orphaned files in the case of cancellations, shell exits, or signal interruptions (like `Ctrl+C` or termination signals), both adapters use robust shell-native `trap` command setups.

### Bash Adapter (`shell/pathtree.bash`)
```bash
# PathTree Bash Integration
# To use, add 'source /path/to/pathtree.bash' to your ~/.bashrc

pb() {
    local temp_file
    temp_file=$(mktemp 2>/dev/null || mktemp -t 'pathtree')

    # Register trap to clean up the temporary file on exit, cancellation, or interruption
    # SIGHUP(1), SIGINT(2), SIGQUIT(3), SIGTERM(15), and EXIT(0)
    trap 'rm -f "$temp_file"' EXIT INT TERM HUP

    # Invoke installed pathtree command directly
    pathtree --output "$temp_file" "$@"
    local exit_status=$?

    if [ $exit_status -eq 0 ] && [ -s "$temp_file" ]; then
        local target_path
        target_path=$(cat "$temp_file")
        if [ -d "$target_path" ]; then
            cd "$target_path" || echo "Error: Could not navigate to $target_path"
        else
            echo "Error: Target path is not a valid directory: $target_path"
        fi
    fi
}
```

### Zsh Adapter (`shell/pathtree.zsh`)
```zsh
# PathTree Zsh Integration
# To use, add 'source /path/to/pathtree.zsh' to your ~/.zshrc

pb() {
    local temp_file
    temp_file=$(mktemp 2>/dev/null || mktemp -t 'pathtree')

    # Register trap to clean up the temporary file on exit, cancellation, or interruption
    # SIGHUP(1), SIGINT(2), SIGQUIT(3), SIGTERM(15), and EXIT(0)
    trap 'rm -f "$temp_file"' EXIT INT TERM HUP

    # Invoke installed pathtree command directly
    pathtree --output "$temp_file" "$@"
    local exit_status=$?

    if [ $exit_status -eq 0 ] && [ -s "$temp_file" ]; then
        local target_path
        target_path=$(cat "$temp_file")
        if [ -d "$target_path" ]; then
            cd "$target_path"
        else
            echo "Error: Target path is not a valid directory: $target_path"
        fi
    fi
}
```

---

## 8. Dependency Graph

The simplified system topology for Milestone 0.0.1:

```
┌──────────────────────────────────────┐
│  shell/pathtree.bash / pathtree.zsh  │ (Active Terminal Session)
└──────────────────┬───────────────────┘
                   │ invokes
                   ▼
┌──────────────────────────────────────┐
│        src/pathtree/app.py           │ (argparse CLI Application)
└────────┬──────────────────────┬──────┘
         │                      │
         ▼ parses               ▼ mounts
┌──────────────────┐  ┌─────────────────┐
│ `--seed-dev` CLI │  │   ui/app.py     │ (Textual App Entry)
└──────────────────┘  └────────┬────────┘
                               │
                               ▼ renders
                      ┌─────────────────┐
                      │ui/screens/main.py│ (TUI Layout Grid)
                      └────┬───────┬────┘
                           │       │
                 draws     │       │     draws
         ┌─────────────────┘       └─────────────────┐
         ▼                                           ▼
┌──────────────────┐                       ┌──────────────────┐
│  widgets/tree.py │                       │widgets/details.py│
└────────┬─────────┘                       └──────────────────┘
         │
         ▼ queries
┌──────────────────────────────────────┐
│       services/node_service.py       │ (Tree Traversal Rules)
└────────────────┬─────────────────────┘
                 │ retrieves
                 ▼
┌──────────────────────────────────────┐
│      database/repository.py          │ (SQLite CRUD Actions)
└────────────────┬─────────────────────┘
                 │ opens engine session
                 ▼
┌──────────────────────────────────────┐
│      database/connection.py          │ (SQLite WAL & schema initialization)
└────────────────┬─────────────────────┘
                 │ schema
                 ▼
┌──────────────────────────────────────┐
│        models/node.py                │ (Combined Persistence & MVP Domain)
└──────────────────────────────────────┘
```

---

## 9. Development Order

1. **Environment Initialization**: Define configuration files using standard declarative metadata in `pyproject.toml` and configure `pytest`.
2. **Model Formulation**: Implement the custom `Node` schema with the optional local `path` attribute under `models/node.py`.
3. **Database Layer & Pragma Logic**: Write session creators in `database/connection.py`, enforcing WAL-mode and recording schema `user_version = 1`. Implement database CRUD repositories in `database/repository.py`.
4. **Business Logic Integration**: Create `NodeService` to format database nodes into hierarchical trees and validate paths.
5. **CLI Parser Implementation**: Build standard `argparse` options in `app.py` including a `--seed-dev` option (dev seed data only exists here and in tests; never seeded on normal startup).
6. **Textual App Screens**: Build basic horizontal screen layout containers (Tree on left, details on right) using Textual.
7. **TUI Component Logic**: Build tree and details widgets. Coordinate event selection.
8. **Shell Adapters**: Implement separate Bash and Zsh integration scripts.
9. **Verification**: Run pytest-asyncio UI mocks and integration scripts.

---

## 10. Pull Request Breakdown

The development cycle of Milestone 0.0.1 is divided into five small, focused, reviewable pull requests matching the streamlined scope:

### PR 1: Project Foundation & CLI Structure
- **Objectives**: Setup basic files, layout, packaging configs, and linter settings.
- **Deliverables**:
  - `pyproject.toml` using standard declarative setup configuration.
  - Basic `src/pathtree/app.py` utilizing standard `argparse` to handle only the basic `--output <file-path>` CLI argument (excluding `--seed-dev` at this stage).
- **Testing**: Verify tests run with 0 tests.

### PR 2: Persistent Storage Layer & Schema
- **Objectives**: Set up SQLModel schemas and SQLite configurations.
- **Deliverables**:
  - `models/node.py` containing `Node` model with optional `path` property.
  - `database/connection.py` implementing WAL support and SQLite `user_version` tracking.
  - `database/repository.py` facilitating CRUD routines.
- **Testing**:
  - Verification that standard database actions and transactions commit properly.
  - Test of SQLite `user_version` database setup.

### PR 3: Service Layer & Dev Seeding
- **Objectives**: Build core business logic, node cycle validation, and seeding utility.
- **Deliverables**:
  - `services/node_service.py` to organize tree collections and prevent cycles.
  - Implement actual database seeding code, and introduce the `--seed-dev` command option inside `app.py` here alongside its actual service implementation. Dev seed data is strictly isolated to this option and is never populated on standard startup.
- **Testing**: Test suite asserting node validation constraints and service functions.

### PR 4: Textual UI & Keybindings
- **Objectives**: Build the stripped, keyboard-first visual workspace browser.
- **Deliverables**:
  - `ui/app.py`, `ui/screens/main.py` layout.
  - `widgets/tree.py` populating nested tree lists.
  - `widgets/details.py` rendering reactive selection changes.
- **Testing**: Textual async UI test cases mimicking focus and node selection, verifying details panel state.

### PR 5: Shell Adapters & CLI Integration
- **Objectives**: Deliver robust, cleanup-safe integration wrappers for Bash and Zsh.
- **Deliverables**:
  - `shell/pathtree.bash` and `shell/pathtree.zsh` featuring shell-appropriate `trap` cleanups for all cancellation, signal disruption, and normal exit states.
  - Integration mapping to serialize target paths to file paths specified by the `--output` CLI argument.
- **Testing**: Integration checks testing the wrapper script behaviors with mock temporary files.
