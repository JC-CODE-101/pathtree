# PathTree Implementation Plan - Milestone 0.0.2 (Daily Navigation)

This document outlines the detailed implementation plan, technical specifications, and progressive pull request sequence for **Milestone 0.0.2 (Daily Navigation)** of PathTree.

The primary goal of Milestone 0.0.2 is to make PathTree indispensable for everyday developer directory navigation by introducing **Search**, **Favorites**, **Temporary Entries**, **Category/Workspace Nesting**, and **Interactive Node Management (CRUD)**, while strictly preserving core architectures and Bash/Zsh shell integrations from Milestone 0.0.1.

---

## 1. Architectural Guidelines & Strategy

To maintain scalability and enable smooth feature rollouts in subsequent versions, Milestone 0.0.2 implements a clean separation of concerns and documents future architectural placeholders.

### A. Conceptual Layers: Structural Nodes vs. Resource Types
Do not model every node as a plain directory. Instead, we introduce a clear architectural distinction between **structural kinds** and **resource types**.

1. **Structural Node Kinds**:
   - **Workspace**: Conceptual organizational groupings (no execution metadata, acts as a container).
   - **Folder**: Conceptual visual directory separator/container in the tree view.
   - **Resource**: An executable or interactive element in the tree which possesses an associated resource type and target action.

2. **Resource Types**:
   - **Directory** (*Implemented in Milestone 0.0.2*): Represents a filesystem folder.
   - **File** (*Placeholder only*): Represents a single local filesystem file.
   - **URL** (*Placeholder only*): Represents an external web address link.
   - **Application** (*Placeholder only*): Represents an executable system binary.
   - **Script** (*Placeholder only*): Represents a local script file with an interpreter.
   - **Shell Environment** (*Placeholder only*): Represents a shell configuration/sourcing environment.
   - **SSH** (*Placeholder only*): Represents a secure remote terminal bookmark.
   - *(Future: Command, Docker, Git, Variables...)*

> **Milestone 0.0.2 Scope Limit**: Only the **Directory** resource type is implemented in Milestone 0.0.2. The other resource types are defined and documented as architecture placeholders only; no execution or runtime support is added for them in this release.

### B. Action Resolver Architecture
Future execution will not depend directly on resource types. Instead, the application will follow a clean, extensible execution pipeline:

```
Node ──► Resource Type ──► Action Resolver ──► Action Handler ──► Shell Adapter OR Python Launcher
```

- **Directory** ──► Resolves to `cd` command.
- **Application** ──► Resolves to executing the system binary.
- **Script** ──► Resolves to executing script via localized interpreter.
- **Shell Environment** ──► Resolves to sourcing shell configs.
- **SSH** ──► Resolves to launching SSH sessions.

Designing Milestone 0.0.2 to support this pipeline ensures that we do not write custom hardcoded execution routines inside UI widgets.

### C. Resource-Specific Creation Dialogs
The "Add Node" workflow begins by prompting the user to select the conceptual **Resource Type** (or structural Workspace/Folder kind).
Depending on the selected type, only the relevant configuration fields are displayed:

1. **Directory**:
   - Name
   - Path (filesystem directory path)
   - Description
2. **URL**:
   - Name
   - URL string
   - Description
3. **Application**:
   - Name
   - Executable path
   - Arguments
   - Working directory
4. **Script**:
   - Name
   - Script path
   - Interpreter (e.g., python, bash)
   - Arguments
5. **Shell Environment**:
   - Name
   - Target Shell (bash/zsh)
   - Source file path
6. **SSH**:
   - Name
   - Host
   - User
   - Port
   - Identity file path

### D. Executable Resource Group
A conceptual group of "Executable Resources" is defined for filtering and execution. This group includes:
- **Application**
- **Script**
- **Shell Environment**
- **SSH**
- *(Future: Command)*

### E. Typed Search Filters & Shortcuts
The search behavior is expanded with typed filters enabling the user to search nodes matching specific criteria:
- `type:directory` - Filters to directory resources.
- `type:file` - Filters to file resources.
- `type:url` - Filters to URL resources.
- `type:application` - Filters to applications.
- `type:script` - Filters to scripts.
- `type:ssh` - Filters to SSH bookmarks.

#### Search Shortcuts Concept:
We define visual/keyboard query shortcuts that activate specific typed filters:
- `x` ──► Focuses/Filters to **all** executable resources.
- `xa` ──► Focuses/Filters to **applications**.
- `xs` ──► Focuses/Filters to **scripts**.
- `xe` ──► Focuses/Filters to **shell environments**.
- `xh` ──► Focuses/Filters to **SSH resources**.

> **Note**: Suffix/shortcut query filtering logic is documented in Milestone 0.0.2 to guide design, but actual implementation of these advanced filters is postponed to Milestone 0.0.3.

### F. Future Interactive Resource Browser
To avoid forcing the user to manually type out full paths, future versions will offer interactive file and directory pickers inside form dialogs:
- **Browse Directory...**
- **Browse File...**

Implementation of this file-system navigation picker is intentionally postponed beyond Milestone 0.0.2.

### G. Shell Adapter Responsibilities
The separate Bash/Zsh shell adapters have minimized responsibilities. They are strictly restricted to operations that **must** happen inside the active shell context:
- Changing directories (`cd`)
- Sourcing environment configurations (`source`)
- Exporting environment variables (`export`)
- Establishing shell aliases

All other metadata validations, filesystem checks, and UI rendering are handled strictly inside the Python application.

---

## 2. Technical Specifications & Core Definitions

### A. Permanent vs. Temporary Entries
- **Permanent Entries (Bookmarks)**: Standard nodes persisted long-term in the database (`is_temporary = False`). They can be created, edited, moved, nested, and favorited.
- **Temporary Entries**: Lightweight session bookmarks created dynamically (`is_temporary = True`).
  - **Lifecycle**: Temporary nodes are session-specific. They are automatically cleared (purged from the database) during application startup or exit (inside the `NodeService` start/stop hooks) to prevent cluttering the database with ephemeral workspaces or paths.
  - **Promotion**: Users can "promote" a temporary node to a permanent node by setting its `is_temporary` field to `False` (via the editing dialog or an interactive shortcut).
  - **Keybinding**: Pressing `t` on a node toggles/creates a temporary bookmark, or marks/unmarks a node as temporary.

### B. Category Management
- Categories represent logical groupings of projects. Following `docs/ROADMAP.md` and `docs/NODE_TYPES.md`, categories are modeled as container nodes of type `"Workspace"` (or `"Folder"`).
- **Relocation and Nesting**: Users can create, edit, rename, and delete container nodes (Workspaces/Folders). Nodes can be nested to an arbitrary depth (supporting unlimited hierarchy). Move dialogs allow selecting a new parent node.
- **Validation Rules**:
  - Prevent cyclic parenting (e.g., moving parent node inside its own child) via standard three-color DFS or recursive checks in `NodeService.validate_parent`.
  - Enforce name uniqueness among sibling nodes under the same parent to maintain tree clarity.

### C. Search Behavior & Keyboard Interaction
- **UI State**: A `SearchInput` (Textual `Input` widget) is positioned at the top of the main layout, above the workspace tree.
- **Real-time Filtering**: As the user types, the `NodeTreeView` is updated instantly.
- **Filtering Logic**: Only nodes matching the query (case-insensitive substring/fuzzy match on `name`, `path`, or `description`) AND their complete parent ancestor chains are rendered. This preserves tree structural context. Sibling nodes that do not match and are not ancestors of matches are hidden.
- **Focus Switching & Keybindings**:
  - `/` or `s`: From the Tree View, focuses the Search Input.
  - `Escape`: From the Search Input, clears the query and returns focus to the Tree View.
  - `Down` or `Enter` (when search is focused): Moves focus down to the first matched node in the Tree View.

### D. Favorites
- Any node can be marked as a favorite (`is_favorite = True`).
- **Visual Indicator**: Favorites display a special visual indicator (e.g., a star `★` icon) next to their name in the tree.
- **Quick-Access View**: A virtual, expandable workspace folder named `★ Favorites` is pinned at the absolute top of the tree view, listing all favorited nodes regardless of their actual database parent.
- **Keybinding**: Pressing `f` on any node in the Tree View toggles its `is_favorite` attribute in the database and refreshes the UI.

---

## 3. Database Schema Migration (user_version 2)

### A. SQLite Evolution
We evolve the database schema from `user_version 1` to `user_version 2` using lightweight, automated startup DDL scripts within `database/connection.py`.

```python
# database/connection.py migration logic draft
def run_migrations(connection):
    version = connection.execute(text("PRAGMA user_version;")).scalar()
    if version == 1:
        # Add is_favorite column (indexed)
        connection.execute(text("ALTER TABLE nodes ADD COLUMN is_favorite BOOLEAN NOT NULL DEFAULT 0;"))
        connection.execute(text("CREATE INDEX ix_nodes_is_favorite ON nodes (is_favorite);"))

        # Add is_temporary column (indexed)
        connection.execute(text("ALTER TABLE nodes ADD COLUMN is_temporary BOOLEAN NOT NULL DEFAULT 0;"))
        connection.execute(text("CREATE INDEX ix_nodes_is_temporary ON nodes (is_temporary);"))

        # Bump version to 2
        connection.execute(text("PRAGMA user_version = 2;"))
```

### B. Python Model Mapping
`src/pathtree/models/node.py` is updated to include the two new fields:

```python
is_favorite: bool = Field(default=False, index=True, nullable=False)
is_temporary: bool = Field(default=False, index=True, nullable=False)
```

---

## 4. UI Layout Hierarchy (Milestone 0.0.2)

```
+--------------------------------------------------------------+
| Search: [ Type here to filter...                           ] |
+--------------------------------------------------------------+
|                                                              |
|  NodeTreeView (65% width)        | NodeDetailsPanel (35%)    |
|  - ★ Favorites                   |                           |
|    - ★ Src Folder                | - Name: Src Folder        |
|  - Root Workspace                | - Type: Folder            |
|    - ★ Src Folder [path: /src]   | - Path: /src              |
|    - Tests Folder [path: /tests] | - Favorite: Yes [★]       |
|                                  | - Temporary: No           |
+--------------------------------------------------------------+
| Footer (Keybindings Status Bar)                              |
| a: Add  e: Edit  d: Del  m: Move  f: Favorite  t: Temp  q: Quit|
+--------------------------------------------------------------+
```

---

## 5. Service Boundaries & Key Validations

### A. `NodeService` Responsibilities
The `NodeService` remains the sole communications gateway between the UI and the database repository.
- **CRUD Operations**: Coordinate node creation, updates, and deletion.
- **Relocation Validation**:
  - Enforce cyclic movement check: `NodeService.validate_parent` rejects operations where parent is placed inside descendant.
  - Enforce self-parenting prevention.
  - Verify that local directory path fields point to actual, valid filesystem folders before saving, or raise user-friendly validation errors.
- **Search Filtering**: Execute case-insensitive text matches.
- **Temporary Node Lifecycle**: Methods to purge all nodes marked `is_temporary = True` on start or exit, and promote a node by setting `is_temporary = False`.

---

## 6. Incremental Pull Request Sequence

Milestone 0.0.2 is structured into five sequential, highly focused, and reviewable pull requests.

```
       ┌─────────────────────────────────────────────────────┐
       │ PR 1: Schema Migration & Persistent Model Evolution │
       └──────────────────────────┬──────────────────────────┘
                                  │
                                  ▼
       ┌─────────────────────────────────────────────────────┐
       │ PR 2: Service Layer CRUD Logic & Lifecycle Hooks    │
       └──────────────────────────┬──────────────────────────┘
                                  │
                                  ▼
       ┌─────────────────────────────────────────────────────┐
       │ PR 3: Search Input Widget & Real-time Tree Filter   │
       └──────────────────────────┬──────────────────────────┘
                                  │
                                  ▼
       ┌─────────────────────────────────────────────────────┐
       │ PR 4: Node Management Interactive UI Dialogs        │
       └──────────────────────────┬──────────────────────────┘
                                  │
                                  ▼
       ┌─────────────────────────────────────────────────────┐
       │ PR 5: Favorites Quick-Access & Temporary Session    │
       └─────────────────────────────────────────────────────┘
```

---

### PR 1: Schema Migration & Persistent Model Evolution

- **Dependency Order**: First PR (No dependencies).
- **Scope**: Database schema evolution to `user_version 2`.
- **Deliverables**:
  - Update `Node` model in `models/node.py` with `is_favorite` and `is_temporary`.
  - Add migration script running on SQLite startup in `database/connection.py` upgrading schemas from version 1 to 2.
  - Update `NodeRepository` in `database/repository.py` to handle the new fields in CRUD query parameters.
- **Verification & Tests**:
  - Add database unit tests in `tests/test_database.py` verifying that migrating a version 1 schema adds the columns and sets defaults cleanly.
  - Test that CRUD operations on `NodeRepository` successfully read and write `is_favorite` and `is_temporary` flags.
- **Definition of Done**:
  - Python tests pass with 100% success.
  - Migration script is idempotent and handles consecutive boots correctly.
  - No model coupling issues with existing SQLite records.

---

### PR 2: Service Layer CRUD Logic & Lifecycle Hooks

- **Dependency Order**: Depends on PR 1.
- **Scope**: Business logic layer of node management, validation rules, search queries, and session lifecycles.
- **Deliverables**:
  - Expand `NodeService` with `create_node()`, `update_node()`, `delete_node()`, and `move_node()` methods.
  - Implement parenting check constraints in `validate_parent()`.
  - Write temporary node management hooks (`purge_temporary_nodes()`, `promote_to_permanent()`).
  - Implement helper for fetching search-filtered node hierarchies.
- **Verification & Tests**:
  - Write extensive unit tests in `tests/test_services.py` for cycle prevention during relocate, sibling name clashes, and invalid paths.
  - Write unit tests proving automatic temporary node purge and manual promotion.
  - Test service-level search text matched hierarchical extraction.
- **Definition of Done**:
  - All validation boundaries are structurally protected and return clear, exception-based domain responses.
  - Service methods are completely decoupled from UI states.

---

### PR 3: Search Input Widget & Real-time Tree Filter

- **Dependency Order**: Depends on PR 2.
- **Scope**: UI Search Input addition and tree filtering binding.
- **Deliverables**:
  - Create a custom `SearchInput` widget in `ui/widgets/search.py` wrapping Textual's standard `Input`.
  - Embed the search bar at the top of the layout in `ui/screens/main.py`.
  - Mount listeners that trigger live-filtering updates on the `NodeTreeView` whenever the search query is modified.
  - Implement search-specific keyboard shortcuts (`/` or `s` key to focus search, `Escape` to clear search and focus the tree, `Down`/`Enter` to navigate to the filtered tree).
- **Verification & Tests**:
  - Create async UI test cases in `tests/test_ui.py` testing typing in the Search Input and checking that the Tree View dynamically hides non-matching nodes.
  - Validate search focus transitions (`/`, `Escape`, `Down`) using Textual's `pilot` keyboard simulation.
- **Definition of Done**:
  - Interactive search operates in real-time under 50ms without lagging the main UI loop.
  - Structural context (ancestor folders) remains visible when children match search queries.

---

### PR 4: Node Management Interactive UI Dialogs

- **Dependency Order**: Depends on PR 3.
- **Scope**: Core UI operations for node addition, edits, and deletions via clean modals.
- **Deliverables**:
  - Create reusable, keyboard-first modal/dialog screens in `ui/screens/dialogs.py` for:
    - **Add Node**:
      - Step 1: Resource Type select menu (Workspace, Folder, Directory, File, URL, Application, Script, Shell Environment, SSH).
      - Step 2: Display input form corresponding strictly to selected resource configuration metadata. For Directory, fields are name, path, and description. Other resource types render placeholders/instructions for future releases.
    - **Edit Node**: Modify metadata, change parent category, toggle favorite/temporary status.
    - **Delete Node**: Standard confirmation prompt preventing accidental loss of bookmarks.
  - Bind key shortcuts (`a`, `e`, `d`, `m`) to pop up corresponding modals in `ui/screens/main.py`.
  - Implement form validations (e.g., path correctness, circular loop detection, empty fields) showing descriptive inline error labels instead of raising raw exceptions.
- **Verification & Tests**:
  - Write async UI test cases checking modal composition, input simulation, saving successful nodes, and error reporting.
  - Confirm the tree is updated dynamically immediately upon saving a dialog.
- **Definition of Done**:
  - Dialogs are fully keyboard accessible (Tab to focus next input, Enter to submit, Escape to close/cancel).
  - Destructive delete operations are securely guarded by the confirmation modal.

---

### PR 5: Favorites Quick-Access & Temporary Session

- **Dependency Order**: Depends on PR 4.
- **Scope**: Final visual polishes, Quick-access Favorites folder, and Temporary node interactions.
- **Deliverables**:
  - Insert a virtual workspace folder titled `★ Favorites` pinned at the top of the tree, dynamically populated with nodes having `is_favorite = True`.
  - Add visual `★` prefix or bracket highlights for all favorites inside the normal workspace groups.
  - Add immediate database toggle support bound to the `f` shortcut inside the main tree view.
  - Bind the `t` key to instantly register the selected node as temporary (or create a quick temporary workspace).
  - Mount hook inside `PathTreeApp.on_mount()` or `on_unmount()` executing `NodeService.purge_temporary_nodes()`.
- **Verification & Tests**:
  - Unit and UI test cases validating `★ Favorites` rendering.
  - Verify that exiting the application cleans up temporary bookmarks and relaunching does not display them.
  - Ensure Bash/Zsh shell adapters remain completely intact and functional, with integration tests running and asserting clean exit codes (`0`) and correct directory changes.
- **Definition of Done**:
  - Entire 0.0.2 test suite is robust, healthy, and passes 100% green.
  - No regressions are introduced to the core `pb` shell directory navigation mechanics.
