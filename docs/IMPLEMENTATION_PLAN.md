# PathTree Implementation Plan - Milestone 0.0.1 (Foundation)

This document outlines the detailed implementation plan and technical specifications for **Milestone 0.0.1 (Foundation)** of PathTree.

The primary goal of this milestone is to establish the core technical architecture—specifically, a solid SQLite database layout, a modular repository/service boundary, an interactive Textual terminal UI for tree navigation, and a reliable shell adapter allowing developers to change terminal directories through the UI.

---

## 1. Project Structure

The project follows a standard layout separating source code, tests, documentation, and shell adapter scripts.

```
.
├── pyproject.toml              # Poetry project configuration and dependencies
├── README.md                   # Project overview
├── AGENTS.md                   # LLM/Developer agent instructions and guidelines
├── LICENSE                     # MIT License
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
│   └── pathtree.sh             # Bash/Zsh wrapper function
├── src/                        # Python package source root
│   └── pathtree/
│       ├── __init__.py         # Package-level imports & metadata
│       ├── app.py              # CLI entrypoint & orchestrator
│       ├── core/
│       │   ├── __init__.py
│       │   ├── config.py       # Configuration parser (JSON loader/saver)
│       │   └── events.py       # Event bus system for decoupled communication
│       ├── database/
│       │   ├── __init__.py
│       │   ├── connection.py   # SQLAlchemy engine, session pool, & table init
│       │   └── repository.py   # Database persistence layer (CRUD logic)
│       ├── models/
│       │   ├── __init__.py
│       │   └── node.py         # SQLModel database schemas
│       ├── services/
│       │   ├── __init__.py
│       │   ├── node_service.py # Business rules & tree traversal logic
│       │   └── shell_service.py# Shell interaction payload formatting
│       └── ui/
│           ├── __init__.py
│           ├── app.py          # Main Textual App sub-class
│           ├── screens/
│           │   ├── __init__.py
│           │   └── main.py     # Main workspace TUI screen
│           └── widgets/
│               ├── __init__.py
│               ├── details.py  # Render pane displaying active node details
│               ├── search.py   # Text input widget for real-time node filtering
│               └── tree.py     # Custom tree widget wrapped around Textual's Tree
└── tests/                      # Package unit, integration, and UI tests
    ├── __init__.py
    ├── conftest.py             # Pytest fixtures (in-memory DB, async event loops)
    ├── test_database.py        # SQLite transactions & CRUD testing
    ├── test_services.py        # Business logic & node-filtering unit tests
    └── test_ui.py              # Textual screen layout & navigation tests
```

---

## 2. Python Package Layout

We utilize a modern **`src/` layout** pattern for the `pathtree` package.

- **Isolation**: Storing code under `src/` prevents Python from importing local dev modules accidentally and ensures that all imports occur relative to the installed package state during test execution.
- **Editable Install**: Developers run `pip install -e .` or `poetry install` to link the package in development mode, allowing instant hot-reloading.
- **Namespacing**: The root module name is `pathtree`, and sub-modules are structured based on logical layers to enforce clear architectural separation.

---

## 3. Recommended Libraries

To ensure simplicity, robustness, and performance, the following libraries are selected:

1. **SQLModel (version >= 0.0.22)**
   - *Why*: SQLModel is built directly on top of **SQLAlchemy** and **Pydantic**. It eliminates redundant model declarations by allowing a single Python class to act as both an ORM database table model and a schema validation model. This guarantees strong type-hinting, native JSON/Pydantic validation, and minimal boilerplate.
2. **Textual (version >= 1.0.0)**
   - *Why*: The premier terminal UI framework for Python. It provides async event loops, reactive properties, standard and flexible custom widgets, and a modern CSS-like styling engine.
3. **pytest & pytest-asyncio**
   - *Why*: Standard testing suite. `pytest-asyncio` is required to test Textual’s async UI components and async event handlers without blocking.
4. **ruff**
   - *Why*: Executes formatting and linting in milliseconds, enforcing PEP-8 compliance and preventing bugs through static analysis.
5. **click**
   - *Why*: A clean, modular CLI argument parser to manage sub-commands (e.g. starting the TUI, seeding initial workspace folders, resetting the database).

---

## 4. Responsibilities of Each Module

| Module Name | High-Level Responsibility | Detail / Constraints |
| :--- | :--- | :--- |
| **`pathtree/app.py`** | Main application orchestrator. | Parses CLI arguments. Coordinates database initialization and launches the Textual TUI. Handles shell export handoffs. |
| **`models/node.py`** | Database schema. | Defines the SQLModel definition for the `Node` entity, ensuring perfect alignment with `ARCHITECTURE.md` Section 8 properties. |
| **`database/connection.py`** | SQLite DB configuration. | Instantiates SQLAlchemy database engines. Enforces SQLite foreign key constraints and optimizes performance via WAL mode. |
| **`database/repository.py`** | CRUD database interface. | Conducts raw database queries. Inserts, updates, and deletes node rows. Does *not* contain business rules. |
| **`services/node_service.py`** | Core business logic layer. | Validates node parent-child sanity (e.g., preventing cycles). Formulates hierarchical trees. Performs search filtering on nodes. |
| **`services/shell_service.py`** | Export & Shell formatting. | Checks directory existence on disk. Safe-formats directory strings. Writes the chosen directory path to the target temporary path. |
| **`ui/app.py`** | Textual framework controller. | Establishes CSS definitions, acts as the primary TUI driver, handles overall app life cycle events, and mounts the `MainScreen`. |
| **`ui/screens/main.py`** | Interactive layout manager. | Dictates visual placement of widgets (Search, Tree, Details, Footer) and maps central keyboard short-cuts. |
| **`ui/widgets/search.py`** | Real-time query field. | Inherits from Textual `Input`. Sends dynamic event signals to parent screen whenever keystrokes alter the search string. |
| **`ui/widgets/tree.py`** | Workspace & folder tree display. | Inherits from Textual `Tree`. Dynamically maps flat DB nodes into nesting branch nodes. Dispatches node activation events. |
| **`ui/widgets/details.py`** | Detail preview pane. | Renders properties of the active node (UUID, path, type, creation dates, description) inside a clean, scrollable layout. |
| **`shell/pathtree.sh`** | POSIX Shell directory changer. | Minimal POSIX-compliant shell function. Creates a temp file, runs `pathtree`, reads the selected target path, executes `cd`, and cleans up. |

---

## 5. Database Implementation Strategy

SQLite is the storage backend. To satisfy the requirements outlined in `docs/DATABASE.md` and `docs/ARCHITECTURE.md`, the implementation adopts the following strategy:

### Schema Mapping (Node Model)
The SQLModel class `Node` will be defined as follows:

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
    node_type: str = Field(default="Folder", index=True, nullable=False)  # Workspace, Folder, etc.
    description: Optional[str] = Field(default=None, nullable=True)
    icon: Optional[str] = Field(default=None, nullable=True)
    is_favorite: bool = Field(default=False, nullable=False)
    is_temporary: bool = Field(default=False, nullable=False)
    sort_order: int = Field(default=0, nullable=False)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
```

### Key Strategies:
- **Automatic Initialization**: On startup, the application checks if the SQLite file exists. If it does not, it creates the file and calls `SQLModel.metadata.create_all(engine)`. No complex migration scripts are needed for Milestone 0.0.1.
- **SQLite Performance & Reliability**:
  - Foreign key checks are explicitly enabled per connection: `PRAGMA foreign_keys = ON;`.
  - Write-Ahead Logging (WAL) is enabled: `PRAGMA journal_mode = WAL;` to prevent lockups during simultaneous UI read queries and file system tracking updates.
- **XDG Compliance**: Database files are stored under standard OS user directory paths:
  - Linux/macOS: `~/.config/pathtree/pathtree.db`
  - Windows: `%APPDATA%\pathtree\pathtree.db`
  - *Override support*: Support setting an environment variable `PATHTREE_DB_PATH` to specify custom file locations (highly useful for automated testing).

---

## 6. Textual UI Architecture

The interface utilizes Textual's modern grid-and-container system, layout styles, and reactive programming paradigms to establish a highly responsive, keyboard-driven UI.

### Component Structure

```
+-------------------------------------------------------------+
| Header (Built-in Title / Workspace Name)                    |
+-------------------------------------------------------------+
| SearchInput (Textual Input - placeholder: "Type to filter") |
+-------------------------------------------------------------+
|                                                             |
|  NodeTreeView (65% width)        | NodeDetailsPanel (35%)   |
|  - Workspace Python              | - Name: python-project   |
|    - docs/                       | - Type: Folder           |
|    - src/                        | - Path: /dev/python-proj |
|    - tests/                      | - Created: 2024-02-15    |
|                                  |                          |
+-------------------------------------------------------------+
| Footer (Keybindings Status Bar)                             |
+-------------------------------------------------------------+
```

### Reactive Properties
- **Filtering**: `SearchInput` watches for changes. Upon typing, it updates a `reactive` query string on the `MainScreen`. The screen triggers a service-level search and re-populates the `NodeTreeView` instantly without losing focus.
- **Active Node Detail Rendering**: The screen monitors node selection events in `NodeTreeView`. When the highlighted node changes, it updates the `reactive` node attribute inside `NodeDetailsPanel`, forcing a redraw of metadata fields.

### Keyboard Mappings & Shortcuts
Navigation leverages standard, ergonomic keys:

- `j` / `Down`: Move selection down in the tree.
- `k` / `Up`: Move selection up in the tree.
- `h` / `Left`: Collapse active directory node. If already collapsed, move focus to its parent node.
- `l` / `Right`: Expand active directory node.
- `Enter`: Activate node. If the node possesses a directory path, write to the target file and shut down with exit code 0.
- `f`: Toggle `is_favorite` flag for the selected node (saves state to database instantly and redraws node indicators).
- `/`: Set focus immediately to the `SearchInput` widget.
- `Escape`: Clear search filter and focus on `NodeTreeView`.
- `q`: Safely terminate the application.

---

## 7. Shell Adapter Architecture

To avoid modifying active shells directly within the Python runtime, PathTree delegates environment navigation to a lightweight POSIX-compliant shell wrapper function.

### Python UI Hand-off Protocol
1. The Python program accepts an optional command-line argument: `--output <file-path>`.
2. When the user highlights a workspace/folder node and presses `Enter`, the UI calls `ShellService.export_path(node_path, output_file)`.
3. The absolute path of the chosen node is written safely to the file specified in `<file-path>`.
4. The Python application terminates gracefully with exit code `0`.
5. If the user cancels or quits manually via `q`, the application exits with a non-zero exit code (e.g. `1`), and nothing is written to the output file.

### Shell Wrapper Function
The wrapper script `shell/pathtree.sh` defines a shell function (`pt` or `pb`) that intercepts execution:

```bash
# pathtree shell adapter function
pt() {
    # Establish a reliable, secure temporary file path
    local temp_file
    temp_file=$(mktemp 2>/dev/null || mktemp -t 'pathtree')

    # Run the Python executable, passing the output file target
    # Adjust python path if using poetry or global install
    if command -v poetry &>/dev/null && [ -f "pyproject.toml" ]; then
        poetry run pathtree --output "$temp_file" "$@"
    else
        python3 -m pathtree.app --output "$temp_file" "$@"
    fi

    local exit_status=$?

    # Check if the UI terminated with exit status 0 and wrote data
    if [ $exit_status -eq 0 ] && [ -s "$temp_file" ]; then
        local target_path
        target_path=$(cat "$temp_file")

        # Perform the actual directory change
        if [ -d "$target_path" ]; then
            cd "$target_path" || echo "Error: Could not navigate to $target_path"
        else
            echo "Error: Target path does not exist: $target_path"
        fi
    fi

    # Ensure cleanup of transient files
    rm -f "$temp_file"
}
```

---

## 8. Dependency Graph

The block diagram below illustrates the hierarchical flow of imports, data requests, and control dependencies:

```
┌─────────────────────────────────┐
│        shell/pathtree.sh        │ (Interactive Shell Session)
└────────────────┬────────────────┘
                 │ spawns subprocess
                 ▼
┌─────────────────────────────────┐
│       src/pathtree/app.py       │ (CLI Entry Point & Runner)
└────────┬───────────────┬────────┘
         │               │
         ▼ imports       ▼ mounts
┌────────────────┐ ┌────────────────────────┐
│  core/config   │ │     ui/app.py          │ (Textual App Container)
└────────────────┘ └───────────┬────────────┘
                               │
                               ▼ displays
                   ┌────────────────────────┐
                   │    ui/screens/main.py  │ (TUI Layout Screen)
                   └─────┬──────┬──────┬────┘
                         │      │      │
       ┌─────────────────┘      │      └─────────────────┐
       ▼ renders                ▼ renders                ▼ renders
┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│  widgets/    │         │  widgets/    │         │  widgets/    │
│  search.py   │         │  tree.py     │         │  details.py  │
└──────────────┘         └──────┬───────┘         └──────────────┘
                                │
                                ▼ requests data
                   ┌────────────────────────┐
                   │ services/node_service  │ (Core Business Rules)
                   └────────────┬───────────┘
                                │
                                ▼ queries
                   ┌────────────────────────┐
                   │ database/repository    │ (Data Persistence Mapper)
                   └────────────┬───────────┘
                                │
                                ▼ persists
                   ┌────────────────────────┐
                   │   database/connection  │ (SQLite Driver & Engine)
                   └────────────┬───────────┘
                                │
                                ▼ reads/writes
                   ┌────────────────────────┐
                   │   models/node.py       │ (SQLModel Schemas)
                   └────────────────────────┘
```

---

## 9. Development Order

To guarantee an incremental, test-driven integration cycle, components should be built in the following sequence:

1. **Environment Setup**: Define configuration rules in `pyproject.toml`, establish a testing pipeline using `pytest`, and set up formatting checks with `ruff`.
2. **Model Formulation**: Implement the Python `Node` database table declaration under `models/node.py` using `SQLModel`.
3. **Database Connection & Seeding**: Configure session generation, WAL mode enforcement, and write seed logic to pre-populate mock workspaces on application launch (useful for development navigation).
4. **Repository Implementation**: Create persistence methods in `database/repository.py` to retrieve all nodes, get roots, update nodes, and filter entries.
5. **Business Logic Integration**: Implement `NodeService` to manage tree structure conversions, handle cycle validation, and carry out text matching.
6. **CLI Parser**: Implement arguments in `app.py` enabling directory seeding, resets, and destination outputs.
7. **TUI Framework & Screens**: Program basic visual rendering using Textual (layout setup, color formatting).
8. **Widget Development**: Code the interactive search widget, the dynamic multi-depth node tree loader, and the detail preview pane.
9. **UI Event Binding**: Bind navigation keys, tie typing hooks to instant filtering updates, and set selection changes to refresh details.
10. **Shell Adapter**: Construct `shell/pathtree.sh` and perform manual/automated shell test drives.

---

## 10. Pull Request Breakdown

Milestone 0.0.1 is divided into five small, self-contained, reviewable pull requests. Each PR builds sequentially on top of the previous one.

### PR 1: Python Project Foundation
- **Objectives**: Initialize configuration structures, linter controls, and package directories.
- **Deliverables**:
  - `pyproject.toml` containing dependencies (`sqlmodel`, `textual`, `click` or `argparse`, `pytest`, `pytest-asyncio`, `ruff`).
  - `.gitignore` (filtering out `.pytest_cache`, `__pycache__`, local `.db` files, etc.).
  - Configured formatting rules for `ruff`.
  - Empty package folders with `.gitkeep` structures.
- **Testing Strategy**: Verify poetry builds successfully. Execute a blank run of `pytest` confirming 0 failures.

### PR 2: Persistence Layer (Models & Database Connection)
- **Objectives**: Construct the database layer, establish standard schemas, and handle setup.
- **Deliverables**:
  - `models/node.py`: `Node` table definition matching Section 8 requirements.
  - `database/connection.py`: Engine pool generation, SQLite WAL configuration, and automatic database initialization routines.
  - `database/repository.py`: CRUD interfaces for inserting, querying, updates, and removals.
- **Testing Strategy**:
  - Pytest unit tests using a temporary, isolated sqlite database on-disk or in-memory (`sqlite:///:memory:`).
  - Verify node insertions populate correct properties (UUID creation, default timestamps, parent associations).

### PR 3: Core Service Layer
- **Objectives**: Develop the business logic boundary.
- **Deliverables**:
  - `services/node_service.py`: High-level business validation, search filter string matches, and hierarchy parsers.
  - Seeding helper utility to fill dummy workspaces and paths (e.g., `/home/user/projects`, `/etc/nginx`, `Python Workspace`) into the database for debugging.
- **Testing Strategy**:
  - Create pytest suites to verify search accuracy (case-insensitivity, substring matches).
  - Test constraints (preventing a node from setting itself or its descendants as its parent).

### PR 4: Interactive Terminal User Interface
- **Objectives**: Construct the keyboard-first Textual UI app.
- **Deliverables**:
  - `ui/app.py`: CSS layout setups and core event bindings.
  - `ui/screens/main.py`: Horizontal container layout.
  - `ui/widgets/search.py`: Reactive filter search input.
  - `ui/widgets/tree.py`: Self-populating, nested TUI node tree.
  - `ui/widgets/details.py`: Real-time active selection display.
- **Testing Strategy**:
  - Utilize Textual’s `App.run_test()` async test runner.
  - Simulate keypresses (`j`, `k`, `/`, letters) and verify that search queries successfully filter tree item counts and highlight selections update details.

### PR 5: CLI & Shell Adapter Integration
- **Objectives**: Formulate shell adapter logic and expose standard CLI switches.
- **Deliverables**:
  - `pathtree/app.py` integration: Parse `--output` files and exit with success or cancellation codes.
  - `services/shell_service.py`: Safe-formatting export outputs and checking local folder integrity.
  - `shell/pathtree.sh`: Minimal POSIX wrapper function to run python and execute `cd`.
- **Testing Strategy**:
  - CLI integration tests ensuring the application exits with non-zero on cancel, and exit status 0 when exporting a path.
  - Integration script verification executing `pt` and asserting that the terminal directory updates successfully.
